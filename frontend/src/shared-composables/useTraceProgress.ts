import { reactive, ref } from 'vue';
import type { Ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../core/api.js';
import { pollJobUntilComplete } from './useAsyncJobPolling.js';

ensureMesApiAvailable();

const DEFAULT_STAGE_TIMEOUT_MS = 360000;

type ProfileKey = 'query_tool' | 'mid_section_defect' | 'mid_section_defect_forward';

const PROFILE_DOMAINS: Record<ProfileKey, string[]> = Object.freeze({
  query_tool: ['history', 'materials', 'rejects', 'holds', 'jobs'],
  mid_section_defect: ['upstream_history', 'materials'],
  mid_section_defect_forward: ['upstream_history', 'downstream_rejects'],
});

export type TraceProfile = 'query_tool' | 'mid_section_defect';
export type TraceDirection = 'forward' | 'backward';

export interface TraceProgressOptions {
  profile?: TraceProfile;
}

export interface StageError {
  code: string | null;
  message: string;
}

export interface StageErrors {
  seed: StageError | null;
  lineage: StageError | null;
  events: StageError | null;
}

export interface StageResults {
  seed: unknown | null;
  lineage: unknown | null;
  events: unknown | null;
}

export interface JobProgress {
  active: boolean;
  job_id: string | null;
  status: string | null;
  elapsed_seconds: number;
  progress: string;
}

export interface TraceProgressComposable {
  current_stage: Ref<string | null>;
  completed_stages: Ref<string[]>;
  stage_results: StageResults;
  stage_errors: StageErrors;
  job_progress: JobProgress;
  is_running: Ref<boolean>;
  execute: (params?: Record<string, unknown>) => Promise<StageResults>;
  reset: () => void;
  abort: () => void;
}

function unwrapEnvelope(result: unknown): unknown {
  if (result && (result as { success?: boolean; data?: unknown }).success === true && 'data' in (result as object)) {
    return (result as { data: unknown }).data;
  }
  return result;
}

function stageKey(stageName: string | null): keyof StageErrors {
  if (stageName === 'seed-resolve') return 'seed';
  if (stageName === 'lineage') return 'lineage';
  return 'events';
}

function normalizeSeedContainerIds(seedPayload: unknown): string[] {
  const payload = seedPayload as {
    seed_container_ids?: unknown[];
    seeds?: { container_id?: unknown }[];
  } | null;
  const directIds = Array.isArray(payload?.seed_container_ids) ? payload.seed_container_ids : [];
  if (directIds.length > 0) {
    const seen = new Set<string>();
    const containerIds: string[] = [];
    directIds.forEach((value) => {
      const id = String(value || '').trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      containerIds.push(id);
    });
    return containerIds;
  }
  const rows = Array.isArray(payload?.seeds) ? payload.seeds : [];
  const seen = new Set<string>();
  const containerIds: string[] = [];
  rows.forEach((row) => {
    const id = String(row?.container_id || '').trim();
    if (!id || seen.has(id)) {
      return;
    }
    seen.add(id);
    containerIds.push(id);
  });
  return containerIds;
}

function collectAllContainerIds(
  seedContainerIds: string[],
  lineagePayload: unknown,
  direction: TraceDirection,
): string[] {
  const payload = lineagePayload as {
    children_map?: Record<string, string[]>;
    ancestors?: Record<string, string[]>;
  } | null;
  const seen = new Set<string>(seedContainerIds);
  const merged: string[] = [...seedContainerIds];

  if (direction === 'forward') {
    const childrenMap = payload?.children_map || {};
    const queue: string[] = [...seedContainerIds];
    while (queue.length > 0) {
      const current = queue.shift()!;
      const children = childrenMap[current];
      if (!Array.isArray(children)) continue;
      for (const child of children) {
        const id = String(child || '').trim();
        if (!id || seen.has(id)) continue;
        seen.add(id);
        merged.push(id);
        queue.push(id);
      }
    }
  } else {
    const ancestors = payload?.ancestors || {};
    Object.values(ancestors).forEach((values) => {
      if (!Array.isArray(values)) {
        return;
      }
      values.forEach((value) => {
        const id = String(value || '').trim();
        if (!id || seen.has(id)) {
          return;
        }
        seen.add(id);
        merged.push(id);
      });
    });
  }

  return merged;
}

// pollJobUntilComplete is imported from useAsyncJobPolling.ts

/**
 * Consume an NDJSON stream from the server, calling onChunk for each line.
 */
async function consumeNDJSONStream(
  url: string,
  { signal, onChunk }: { signal?: AbortSignal; onChunk?: (chunk: Record<string, unknown>) => void } = {},
): Promise<void> {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    const error = Object.assign(
      new Error(`Stream request failed: HTTP ${response.status} ${text}`),
      { errorCode: 'STREAM_FAILED' },
    );
    throw error;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop()!; // keep incomplete last line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const chunk = JSON.parse(trimmed) as Record<string, unknown>;
          if (typeof onChunk === 'function') onChunk(chunk);
        } catch {
          // skip malformed NDJSON lines
        }
      }
    }

    // process remaining buffer
    if (buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer.trim()) as Record<string, unknown>;
        if (typeof onChunk === 'function') onChunk(chunk);
      } catch {
        // skip malformed final line
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function useTraceProgress({ profile }: TraceProgressOptions = {}): TraceProgressComposable {
  const current_stage: Ref<string | null> = ref(null);
  const completed_stages: Ref<string[]> = ref([]);
  const is_running: Ref<boolean> = ref(false);

  const stage_results: StageResults = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  const stage_errors: StageErrors = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  // Async job progress (populated when events stage uses async path)
  const job_progress: JobProgress = reactive({
    active: false,
    job_id: null,
    status: null,
    elapsed_seconds: 0,
    progress: '',
  });

  let activeController: AbortController | null = null;

  function reset(): void {
    completed_stages.value = [];
    current_stage.value = null;
    stage_results.seed = null;
    stage_results.lineage = null;
    stage_results.events = null;
    stage_errors.seed = null;
    stage_errors.lineage = null;
    stage_errors.events = null;
    job_progress.active = false;
    job_progress.job_id = null;
    job_progress.status = null;
    job_progress.elapsed_seconds = 0;
    job_progress.progress = '';
  }

  function abort(): void {
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
  }

  async function execute(params: Record<string, unknown> = {}): Promise<StageResults> {
    const direction = (params.direction as TraceDirection) || 'backward';
    const domainKey: ProfileKey = profile === 'mid_section_defect' && direction === 'forward'
      ? 'mid_section_defect_forward'
      : (profile as ProfileKey);
    const domains = PROFILE_DOMAINS[domainKey];
    if (!domains) {
      throw new Error(`Unsupported trace profile: ${profile}`);
    }

    abort();
    reset();
    is_running.value = true;

    const controller = new AbortController();
    activeController = controller;

    try {
      current_stage.value = 'seed-resolve';
      const seedRaw = await apiPost(
        '/api/trace/seed-resolve',
        { profile, params },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      const seedPayload = unwrapEnvelope(seedRaw);
      stage_results.seed = seedPayload;
      completed_stages.value = [...completed_stages.value, 'seed-resolve'];

      const seedContainerIds = normalizeSeedContainerIds(seedPayload);
      if (seedContainerIds.length === 0) {
        return stage_results;
      }

      current_stage.value = 'lineage';
      const seedPayloadTyped = seedPayload as { cache_key?: string | null } | null;
      const lineageRaw = await apiPost(
        '/api/trace/lineage',
        {
          profile,
          container_ids: seedContainerIds,
          cache_key: seedPayloadTyped?.cache_key || null,
          params,
        },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      const lineageEnvelope = unwrapEnvelope(lineageRaw) as {
        async?: boolean;
        status_url?: string;
        job_id?: string | null;
        query_id?: string;
        ancestors?: Record<string, string[]>;
        children_map?: Record<string, string[]>;
        seed_roots?: Record<string, string[]>;
      } | null;

      // Async lineage path: server returned 202 with job_id
      let lineagePayload: typeof lineageEnvelope;
      if (lineageEnvelope?.async === true && lineageEnvelope?.status_url) {
        job_progress.active = true;
        job_progress.job_id = lineageEnvelope.job_id ?? null;
        job_progress.status = 'queued';

        await pollJobUntilComplete(lineageEnvelope.status_url, {
          signal: controller.signal,
          onProgress: (statusResp) => {
            job_progress.status = statusResp.status;
            job_progress.elapsed_seconds = statusResp.elapsed_seconds || 0;
            job_progress.progress = statusResp.progress || '';
          },
        });

        const lineageResultUrl = `${lineageEnvelope.status_url}/result`;
        const lineageResultRaw = await apiGet(lineageResultUrl, {
          timeout: DEFAULT_STAGE_TIMEOUT_MS,
          signal: controller.signal,
        });
        lineagePayload = unwrapEnvelope(lineageResultRaw) as typeof lineageEnvelope;
        job_progress.active = false;
      } else {
        lineagePayload = lineageEnvelope;
      }

      stage_results.lineage = lineagePayload;
      completed_stages.value = [...completed_stages.value, 'lineage'];

      const lineageQueryId = String(
        (lineagePayload as { query_id?: string } | null)?.query_id ||
        lineageEnvelope?.query_id || '',
      ).trim() || null;
      const eventContainerIds = profile === 'mid_section_defect'
        ? seedContainerIds
        : collectAllContainerIds(seedContainerIds, lineagePayload, direction);
      current_stage.value = 'events';
      const eventRequest: Record<string, unknown> = {
        profile,
        container_ids: eventContainerIds,
        domains,
        cache_key: seedPayloadTyped?.cache_key || null,
        params,
        seed_container_ids: seedContainerIds,
      };
      if (profile === 'mid_section_defect') {
        if (lineageQueryId) {
          eventRequest.lineage_query_id = lineageQueryId;
        }
      } else {
        eventRequest.lineage = {
          ancestors: lineagePayload?.ancestors || {},
          children_map: lineagePayload?.children_map || {},
          seed_roots: lineagePayload?.seed_roots || {},
        };
      }
      const eventsRaw = await apiPost(
        '/api/trace/events',
        eventRequest,
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      const eventsPayload = unwrapEnvelope(eventsRaw) as {
        async?: boolean;
        status_url?: string;
        stream_url?: string;
        job_id?: string | null;
        [key: string]: unknown;
      } | null;

      // Async path: server returned 202 with job_id
      if (eventsPayload?.async === true && eventsPayload?.status_url) {
        job_progress.active = true;
        job_progress.job_id = eventsPayload.job_id ?? null;
        job_progress.status = 'queued';

        // Phase 1: poll until job finishes
        await pollJobUntilComplete(eventsPayload.status_url, {
          signal: controller.signal,
          onProgress: (statusResp) => {
            job_progress.status = statusResp.status;
            job_progress.elapsed_seconds = statusResp.elapsed_seconds || 0;
            job_progress.progress = statusResp.progress || '';
          },
        });

        // Phase 2: stream result via NDJSON (or fall back to full result)
        const streamUrl = eventsPayload.stream_url;
        if (streamUrl) {
          job_progress.progress = 'streaming';

          const streamedResult: {
            stage: string;
            results: Record<string, {
              data: unknown[];
              count: number;
              total: unknown;
              quality_meta: unknown | null;
            }>;
            aggregation: unknown | null;
            quality_meta: unknown | null;
            domain_quality_meta: Record<string, unknown>;
            query_id?: string;
            trace_query_id?: string;
            error?: string;
            failed_domains?: string[];
            [key: string]: unknown;
          } = {
            stage: 'events',
            results: {},
            aggregation: null,
            quality_meta: null,
            domain_quality_meta: {},
          };
          let totalRecords = 0;

          await consumeNDJSONStream(streamUrl, {
            signal: controller.signal,
            onChunk: (chunk) => {
              if (chunk.type === 'meta') {
                if (chunk.query_id) {
                  streamedResult.query_id = chunk.query_id as string;
                }
                if (chunk.trace_query_id) {
                  streamedResult.trace_query_id = chunk.trace_query_id as string;
                }
              } else if (chunk.type === 'domain_start') {
                const domain = chunk.domain as string;
                const domainQualityMeta = (chunk.quality_meta as unknown) || null;
                streamedResult.results[domain] = {
                  data: [],
                  count: 0,
                  total: chunk.total,
                  quality_meta: domainQualityMeta,
                };
                if (domainQualityMeta) {
                  streamedResult.domain_quality_meta[domain] = domainQualityMeta;
                }
              } else if (chunk.type === 'records' && streamedResult.results[chunk.domain as string]) {
                const domain = chunk.domain as string;
                const domainResult = streamedResult.results[domain];
                domainResult.data.push(...(chunk.data as unknown[]));
                domainResult.count = domainResult.data.length;
                totalRecords += (chunk.data as unknown[]).length;
                job_progress.progress = `streaming: ${totalRecords} records`;
              } else if (chunk.type === 'aggregation') {
                streamedResult.aggregation = chunk.data;
              } else if (chunk.type === 'quality_meta') {
                streamedResult.quality_meta = (chunk.quality_meta as unknown) || null;
                if (chunk.domain_quality_meta && typeof chunk.domain_quality_meta === 'object') {
                  streamedResult.domain_quality_meta = chunk.domain_quality_meta as Record<string, unknown>;
                }
              } else if (chunk.type === 'warning') {
                streamedResult.error = chunk.code as string;
                streamedResult.failed_domains = chunk.failed_domains as string[];
              } else if (chunk.type === 'full_result') {
                // Legacy fallback: server sent full result as single chunk
                Object.assign(streamedResult, chunk.data);
              }
            },
          });

          stage_results.events = streamedResult;
        } else {
          // No stream_url: fall back to fetching full result
          const resultUrl = `${eventsPayload.status_url}/result`;
          const jobResultRaw = await apiGet(resultUrl, {
            timeout: DEFAULT_STAGE_TIMEOUT_MS,
            signal: controller.signal,
          });
          stage_results.events = unwrapEnvelope(jobResultRaw);
        }

        job_progress.active = false;
      } else {
        // Sync path
        stage_results.events = eventsPayload;
      }

      completed_stages.value = [...completed_stages.value, 'events'];
      return stage_results;
    } catch (error: unknown) {
      if ((error as Error)?.name === 'AbortError') {
        return stage_results;
      }
      const key = stageKey(current_stage.value);
      stage_errors[key] = {
        code: (error as { errorCode?: string })?.errorCode || null,
        message: (error as Error)?.message || '追溯查詢失敗',
      };
      return stage_results;
    } finally {
      if (activeController === controller) {
        activeController = null;
      }
      current_stage.value = null;
      is_running.value = false;
      job_progress.active = false;
    }
  }

  return {
    current_stage,
    completed_stages,
    stage_results,
    stage_errors,
    job_progress,
    is_running,
    execute,
    reset,
    abort,
  };
}
