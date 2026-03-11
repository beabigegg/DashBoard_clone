import { reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../core/api.js';
import { pollJobUntilComplete } from './useAsyncJobPolling.js';

ensureMesApiAvailable();

const DEFAULT_STAGE_TIMEOUT_MS = 360000;
const PROFILE_DOMAINS = Object.freeze({
  query_tool: ['history', 'materials', 'rejects', 'holds', 'jobs'],
  mid_section_defect: ['upstream_history', 'materials'],
  mid_section_defect_forward: ['upstream_history', 'downstream_rejects'],
});

function stageKey(stageName) {
  if (stageName === 'seed-resolve') return 'seed';
  if (stageName === 'lineage') return 'lineage';
  return 'events';
}

function normalizeSeedContainerIds(seedPayload) {
  const rows = Array.isArray(seedPayload?.seeds) ? seedPayload.seeds : [];
  const seen = new Set();
  const containerIds = [];
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

function collectAllContainerIds(seedContainerIds, lineagePayload, direction) {
  const seen = new Set(seedContainerIds);
  const merged = [...seedContainerIds];

  if (direction === 'forward') {
    const childrenMap = lineagePayload?.children_map || {};
    const queue = [...seedContainerIds];
    while (queue.length > 0) {
      const current = queue.shift();
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
    const ancestors = lineagePayload?.ancestors || {};
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

// pollJobUntilComplete is imported from useAsyncJobPolling.js

/**
 * Consume an NDJSON stream from the server, calling onChunk for each line.
 *
 * @param {string} url - The stream endpoint URL
 * @param {object} options - { signal, onChunk }
 * @returns {Promise<void>}
 */
async function consumeNDJSONStream(url, { signal, onChunk } = {}) {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    const error = new Error(`Stream request failed: HTTP ${response.status} ${text}`);
    error.errorCode = 'STREAM_FAILED';
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete last line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const chunk = JSON.parse(trimmed);
          if (typeof onChunk === 'function') onChunk(chunk);
        } catch {
          // skip malformed NDJSON lines
        }
      }
    }

    // process remaining buffer
    if (buffer.trim()) {
      try {
        const chunk = JSON.parse(buffer.trim());
        if (typeof onChunk === 'function') onChunk(chunk);
      } catch {
        // skip malformed final line
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function useTraceProgress({ profile } = {}) {
  const current_stage = ref(null);
  const completed_stages = ref([]);
  const is_running = ref(false);

  const stage_results = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  const stage_errors = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  // Async job progress (populated when events stage uses async path)
  const job_progress = reactive({
    active: false,
    job_id: null,
    status: null,
    elapsed_seconds: 0,
    progress: '',
  });

  let activeController = null;

  function reset() {
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

  function abort() {
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
  }

  async function execute(params = {}) {
    const direction = params.direction || 'backward';
    const domainKey = profile === 'mid_section_defect' && direction === 'forward'
      ? 'mid_section_defect_forward'
      : profile;
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
      const seedPayload = await apiPost(
        '/api/trace/seed-resolve',
        { profile, params },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      stage_results.seed = seedPayload;
      completed_stages.value = [...completed_stages.value, 'seed-resolve'];

      const seedContainerIds = normalizeSeedContainerIds(seedPayload);
      if (seedContainerIds.length === 0) {
        return stage_results;
      }

      current_stage.value = 'lineage';
      const lineagePayload = await apiPost(
        '/api/trace/lineage',
        {
          profile,
          container_ids: seedContainerIds,
          cache_key: seedPayload?.cache_key || null,
          params,
        },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      stage_results.lineage = lineagePayload;
      completed_stages.value = [...completed_stages.value, 'lineage'];

      const allContainerIds = collectAllContainerIds(seedContainerIds, lineagePayload, direction);
      current_stage.value = 'events';
      const eventsPayload = await apiPost(
        '/api/trace/events',
        {
          profile,
          container_ids: allContainerIds,
          domains,
          cache_key: seedPayload?.cache_key || null,
          params,
          seed_container_ids: seedContainerIds,
          lineage: {
            ancestors: lineagePayload?.ancestors || {},
            children_map: lineagePayload?.children_map || {},
            seed_roots: lineagePayload?.seed_roots || {},
          },
        },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );

      // Async path: server returned 202 with job_id
      if (eventsPayload?.async === true && eventsPayload?.status_url) {
        job_progress.active = true;
        job_progress.job_id = eventsPayload.job_id;
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

          const streamedResult = {
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
              if (chunk.type === 'domain_start') {
                const domainQualityMeta = chunk.quality_meta || null;
                streamedResult.results[chunk.domain] = {
                  data: [],
                  count: 0,
                  total: chunk.total,
                  quality_meta: domainQualityMeta,
                };
                if (domainQualityMeta) {
                  streamedResult.domain_quality_meta[chunk.domain] = domainQualityMeta;
                }
              } else if (chunk.type === 'records' && streamedResult.results[chunk.domain]) {
                const domainResult = streamedResult.results[chunk.domain];
                domainResult.data.push(...chunk.data);
                domainResult.count = domainResult.data.length;
                totalRecords += chunk.data.length;
                job_progress.progress = `streaming: ${totalRecords} records`;
              } else if (chunk.type === 'aggregation') {
                streamedResult.aggregation = chunk.data;
              } else if (chunk.type === 'quality_meta') {
                streamedResult.quality_meta = chunk.quality_meta || null;
                if (chunk.domain_quality_meta && typeof chunk.domain_quality_meta === 'object') {
                  streamedResult.domain_quality_meta = chunk.domain_quality_meta;
                }
              } else if (chunk.type === 'warning') {
                streamedResult.error = chunk.code;
                streamedResult.failed_domains = chunk.failed_domains;
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
          stage_results.events = await apiGet(resultUrl, {
            timeout: DEFAULT_STAGE_TIMEOUT_MS,
            signal: controller.signal,
          });
        }

        job_progress.active = false;
      } else {
        // Sync path
        stage_results.events = eventsPayload;
      }

      completed_stages.value = [...completed_stages.value, 'events'];
      return stage_results;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return stage_results;
      }
      const key = stageKey(current_stage.value);
      stage_errors[key] = {
        code: error?.errorCode || null,
        message: error?.message || '追溯查詢失敗',
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
