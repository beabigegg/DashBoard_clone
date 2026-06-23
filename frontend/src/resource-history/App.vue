<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../core/api';
import { unwrapApiResult } from '../core/unwrap-api-result';
import { buildResourceKpiFromHours } from '../core/compute';
import { checkLocalComputeEligibility } from '../core/duckdb-activation-policy';
import {
  buildResourceHistoryQueryParams,
  deriveWorkcenterGroupOptions,
  deriveLocationOptions,
  deriveResourceFamilyOptions,
  deriveResourceMachineOptions,
  derivePackageGroupOptions,
  pruneResourceFilterSelections,
  toResourceFilterSnapshot,
} from '../core/resource-history-filters';
import type { ResourceFilterSnapshot, ResourceItem } from '../core/resource-history-filters';
import { replaceRuntimeHistory } from '../core/shell-navigation';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useRequestGuard } from '../shared-composables/useRequestGuard';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';
import { useResourceHistoryDuckDB } from './useResourceHistoryDuckDB';

import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';

import ComparisonChart from './components/ComparisonChart.vue';
import DetailSection from './components/DetailSection.vue';
import FilterBar from './components/FilterBar.vue';
import HeatmapChart from './components/HeatmapChart.vue';
import KpiCards from './components/KpiCards.vue';
import StackedChart from './components/StackedChart.vue';
import TrendChart from './components/TrendChart.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 360000;
const MAX_QUERY_DAYS = 730;

function createDefaultFilters() {
  return toResourceFilterSnapshot({
    granularity: 'day',
    workcenterGroups: [],
    locations: [],
    families: [],
    machines: [],
    isProduction: false,
    isKey: false,
    isMonitor: false,
    packageGroups: [],
  });
}

const {
  committed: committedFilters,
  draft: draftFilters,
  updateField: updateOrchestratorField,
} = useFilterOrchestrator({
  fields: {
    startDate:       { trigger: 'immediate', initial: '' },
    endDate:         { trigger: 'immediate', initial: '' },
    granularity:     { trigger: 'immediate', initial: 'day' },
    workcenterGroups:{ trigger: 'immediate', initial: [] },
    locations:       { trigger: 'immediate', initial: [] },
    families:        { trigger: 'immediate', initial: [] },
    machines:        { trigger: 'immediate', initial: [] },
    isProduction:    { trigger: 'immediate', initial: false },
    isKey:           { trigger: 'immediate', initial: false },
    isMonitor:       { trigger: 'immediate', initial: false },
    packageGroups:   { trigger: 'immediate', initial: [] },
  },
  dependencies: [],
});

const options = reactive<{
  workcenterGroups: (string | number | Record<string, unknown>)[];
  locations: (string | number | Record<string, unknown>)[];
  families: (string | number | Record<string, unknown>)[];
  resources: ResourceItem[];
  packageGroups: (string | number | Record<string, unknown>)[];
}>({
  workcenterGroups: [],
  locations: [],
  families: [],
  resources: [],
  packageGroups: [],
});

const summaryData = ref<{
  kpi: Record<string, unknown>;
  trend: Record<string, unknown>[];
  heatmap: Record<string, unknown>[];
  workcenter_comparison: Record<string, unknown>[];
}>({
  kpi: {},
  trend: [],
  heatmap: [],
  workcenter_comparison: [],
});
const detailData = ref<unknown[]>([]);
const detailByDateData = ref<unknown[]>([]);
const hierarchyState = reactive<Record<string, boolean>>({});

const loading = reactive({
  initial: true,
  querying: false,
  primaryQuery: false,
  options: false,
});

const queryError = ref('');
const detailWarning = ref('');
const exportMessage = ref('');
const autoPruneHint = ref('');

const queryId = ref('');
const lastPrimarySnapshot = ref('');

// ── Batch query progress polling (AC-6, AC-7) ────────────────────────────────

const PROGRESS_POLL_INTERVAL_MS = 1500;

interface ProgressData {
  query_id: string;
  total_chunks: number;
  completed_chunks: number;
  percent: number;
  status: 'running' | 'done' | 'error';
}

const isPolling = ref(false);
const progressPercent = ref(0);
let pollTimerId: ReturnType<typeof setInterval> | null = null;

function stopPolling(): void {
  if (pollTimerId !== null) {
    clearInterval(pollTimerId);
    pollTimerId = null;
  }
  isPolling.value = false;
}

async function fetchProgress(qid: string): Promise<void> {
  try {
    const response = await apiGet('/api/resource/history/query/progress', {
      timeout: 10000,
      silent: true,
      params: { query_id: qid },
    });
    const raw = response as { data?: ProgressData } | null;
    const data = raw?.data;
    if (!data) {
      return;
    }

    progressPercent.value = Math.min(100, Math.max(0, data.percent));

    if (data.status === 'done' || data.status === 'error') {
      stopPolling();

      if (data.status === 'error') {
        queryError.value = '批次查詢發生錯誤，請重試';
        loading.querying = false;
        loading.primaryQuery = false;
        loading.initial = false;
      }
      // On 'done', the calling executePrimaryQuery() flow already handles applyViewResult;
      // progress bar simply disappears via isPolling === false.
    }
  } catch {
    // Network error mid-poll — stop polling to avoid zombie timer (AC-7)
    stopPolling();
  }
}

function startPolling(qid: string): void {
  stopPolling();
  isPolling.value = true;
  progressPercent.value = 0;
  pollTimerId = setInterval(() => {
    void fetchProgress(qid);
  }, PROGRESS_POLL_INTERVAL_MS);
}

onUnmounted(() => {
  stopPolling();
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  _stopElapsedTimer();
});

// ── RQ async job progress (202 path) ─────────────────────────────────────────
const asyncJobProgress = reactive({
  active: false,
  jobId: null as string | null,
  status: null as string | null,
  progress: '',
  pct: 0,
  elapsedSeconds: 0,
});

let _jobAbortController: AbortController | null = null;
let _jobStartedAt: number | null = null;
let _elapsedTimer: ReturnType<typeof setInterval> | null = null;

function _startElapsedTimer(): void {
  _jobStartedAt = Date.now();
  _elapsedTimer = setInterval(() => {
    if (_jobStartedAt !== null) {
      asyncJobProgress.elapsedSeconds = Math.floor((Date.now() - _jobStartedAt) / 1000);
    }
  }, 1000);
}

function _stopElapsedTimer(): void {
  if (_elapsedTimer !== null) {
    clearInterval(_elapsedTimer);
    _elapsedTimer = null;
  }
  _jobStartedAt = null;
}

async function cancelAsyncJob(): Promise<void> {
  const jobId = asyncJobProgress.jobId;
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  _stopElapsedTimer();
  asyncJobProgress.active = false;
  asyncJobProgress.jobId = null;

  if (jobId) {
    try {
      await apiPost(`/api/job/${jobId}/abandon`, {}, { silent: true, timeout: 10000 });
    } catch {
      // Non-fatal: abandon is best-effort
    }
  }
}

const { nextRequestId, isStaleRequest } = useRequestGuard();

// ── DuckDB local compute (Tasks 3.2–3.4) ─────────────────────────────────────
const duckdb = useResourceHistoryDuckDB();

const draftWatchReady = ref(false);
let suppressDraftPrune = false;

function runWithDraftPruneSuppressed(callback: () => void): void {
  suppressDraftPrune = true;
  try {
    callback();
  } finally {
    suppressDraftPrune = false;
  }
}

function resetHierarchyState() {
  Object.keys(hierarchyState).forEach((key) => {
    delete hierarchyState[key];
  });
}

function toDateString(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function setDefaultDates(target: Record<string, unknown> | ResourceFilterSnapshot): void {
  const today = new Date();
  const endDate = new Date(today);
  endDate.setDate(endDate.getDate() - 1);

  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 6);

  (target as Record<string, unknown>).startDate = toDateString(startDate);
  (target as Record<string, unknown>).endDate = toDateString(endDate);
}

function assignFilterState(target: Record<string, unknown>, source: Record<string, unknown> | ResourceFilterSnapshot): void {
  const snapshot = toResourceFilterSnapshot(source as Record<string, unknown>);
  target.startDate = snapshot.startDate;
  target.endDate = snapshot.endDate;
  target.granularity = snapshot.granularity;
  target.workcenterGroups = [...snapshot.workcenterGroups];
  target.locations = [...snapshot.locations];
  target.families = [...snapshot.families];
  target.machines = [...snapshot.machines];
  target.isProduction = snapshot.isProduction;
  target.isKey = snapshot.isKey;
  target.isMonitor = snapshot.isMonitor;
  target.packageGroups = [...snapshot.packageGroups];
}

function resetToDefaultFilters(target: Record<string, unknown>): void {
  const defaults = createDefaultFilters();
  setDefaultDates(defaults);
  assignFilterState(target, defaults);
}

function mergeComputedKpi(source: Record<string, unknown>): Record<string, unknown> {
  return {
    ...source,
    ...buildResourceKpiFromHours(source),
  };
}

function appendArrayParams(params: URLSearchParams, key: string, values: string[]): void {
  for (const value of values || []) {
    params.append(key, value);
  }
}

function buildQueryStringFromFilters(filters: Record<string, unknown>): string {
  const queryParams = buildResourceHistoryQueryParams(filters);
  const params = new URLSearchParams();

  params.append('start_date', queryParams.start_date);
  params.append('end_date', queryParams.end_date);
  params.append('granularity', queryParams.granularity);
  appendArrayParams(params, 'workcenter_groups', queryParams.workcenter_groups || []);
  appendArrayParams(params, 'locations', queryParams.locations || []);
  appendArrayParams(params, 'families', queryParams.families || []);
  appendArrayParams(params, 'resource_ids', queryParams.resource_ids || []);
  appendArrayParams(params, 'package_groups', queryParams.package_groups || []);

  if (queryParams.is_production) {
    params.append('is_production', queryParams.is_production);
  }
  if (queryParams.is_key) {
    params.append('is_key', queryParams.is_key);
  }
  if (queryParams.is_monitor) {
    params.append('is_monitor', queryParams.is_monitor);
  }

  return params.toString();
}

function readArrayParam(params: URLSearchParams, key: string): string[] {
  const repeated = params.getAll(key).map((value) => String(value || '').trim()).filter(Boolean);
  if (repeated.length > 0) {
    return repeated;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function readBooleanParam(params: URLSearchParams, key: string): boolean {
  const value = String(params.get(key) || '').trim().toLowerCase();
  return value === '1' || value === 'true' || value === 'yes';
}

function restoreCommittedFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const next = {
    startDate: String(params.get('start_date') || '').trim(),
    endDate: String(params.get('end_date') || '').trim(),
    granularity: String(params.get('granularity') || '').trim(),
    workcenterGroups: readArrayParam(params, 'workcenter_groups'),
    locations: readArrayParam(params, 'locations'),
    families: readArrayParam(params, 'families'),
    machines: readArrayParam(params, 'resource_ids'),
    isProduction: readBooleanParam(params, 'is_production'),
    isKey: readBooleanParam(params, 'is_key'),
    isMonitor: readBooleanParam(params, 'is_monitor'),
    packageGroups: readArrayParam(params, 'package_groups'),
  };

  if (next.startDate) {
    committedFilters.startDate = next.startDate;
  }
  if (next.endDate) {
    committedFilters.endDate = next.endDate;
  }
  if (next.granularity) {
    committedFilters.granularity = next.granularity;
  }
  if (next.workcenterGroups.length > 0) {
    committedFilters.workcenterGroups = next.workcenterGroups;
  }
  if (next.locations.length > 0) {
    committedFilters.locations = next.locations;
  }
  if (next.families.length > 0) {
    committedFilters.families = next.families;
  }
  if (next.machines.length > 0) {
    committedFilters.machines = next.machines;
  }
  if (next.packageGroups.length > 0) {
    committedFilters.packageGroups = next.packageGroups;
  }
  committedFilters.isProduction = next.isProduction;
  committedFilters.isKey = next.isKey;
  committedFilters.isMonitor = next.isMonitor;
}

function updateUrlState() {
  const queryString = buildQueryStringFromFilters(committedFilters);
  const nextUrl = queryString ? `/resource-history?${queryString}` : '/resource-history';
  replaceRuntimeHistory(nextUrl);
}

function validateDateRange(filters: Record<string, unknown>): string {
  if (!filters.startDate || !filters.endDate) {
    return '請先設定開始與結束日期';
  }

  const start = new Date(String(filters.startDate));
  const end = new Date(String(filters.endDate));
  const diffDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);

  if (diffDays < 0) {
    return '結束日期必須大於起始日期';
  }
  if (diffDays > MAX_QUERY_DAYS) {
    return '查詢範圍不可超過兩年';
  }

  return '';
}

async function loadOptions() {
  loading.options = true;

  try {
    const response = await apiGet('/api/resource/history/options', {
      timeout: API_TIMEOUT,
      silent: true,
    });

    const payload = unwrapApiResult(response, '載入篩選選項失敗') as Record<string, unknown>;
    const data = (payload?.data || {}) as Record<string, unknown>;

    options.workcenterGroups = Array.isArray(data.workcenter_groups) ? (data.workcenter_groups as (string | number | Record<string, unknown>)[]) : [];
    options.locations = Array.isArray(data.locations) ? (data.locations as (string | number | Record<string, unknown>)[]) : [];
    options.families = Array.isArray(data.families) ? (data.families as (string | number | Record<string, unknown>)[]) : [];
    options.resources = Array.isArray(data.resources) ? (data.resources as ResourceItem[]) : [];
    options.packageGroups = Array.isArray(data.package_groups) ? (data.package_groups as (string | number | Record<string, unknown>)[]) : [];
  } finally {
    loading.options = false;
  }
}

const familyOptions = computed(() => {
  return deriveResourceFamilyOptions(options.resources, draftFilters);
});

const machineOptions = computed(() => {
  return deriveResourceMachineOptions(options.resources, draftFilters);
});

const workcenterGroupOptions = computed(() => deriveWorkcenterGroupOptions(options.resources, draftFilters));
const locationOptions = computed(() => deriveLocationOptions(options.resources, draftFilters));
const packageGroupOptions = computed(() => derivePackageGroupOptions(options.resources, draftFilters));

const filterBarOptions = computed(() => {
  return {
    workcenterGroups: workcenterGroupOptions.value,
    locations: locationOptions.value,
    families: familyOptions.value,
    packageGroups: packageGroupOptions.value,
  };
});

function formatPruneHint(removed: { families: string[]; machines: string[] }): string {
  const parts: string[] = [];
  if (removed.families.length > 0) {
    parts.push(`型號: ${removed.families.join(', ')}`);
  }
  if (removed.machines.length > 0) {
    parts.push(`機台: ${removed.machines.join(', ')}`);
  }
  if (parts.length === 0) {
    return '';
  }
  return `已自動清除失效篩選：${parts.join('；')}`;
}

function pruneDraftSelections({ showHint = true }: { showHint?: boolean } = {}): ReturnType<typeof pruneResourceFilterSelections> {
  const result = pruneResourceFilterSelections(draftFilters, {
    familyOptions: familyOptions.value,
    machineOptions: machineOptions.value,
  });
  if (result.removedCount > 0) {
    runWithDraftPruneSuppressed(() => {
      draftFilters.families = [...result.filters.families];
      draftFilters.machines = [...result.filters.machines];
    });
    if (showHint) {
      autoPruneHint.value = formatPruneHint(result.removed);
    }
  }
  return result;
}

const pruneSignature = computed(() => {
  return JSON.stringify({
    workcenterGroups: draftFilters.workcenterGroups,
    families: draftFilters.families,
    machines: draftFilters.machines,
    isProduction: draftFilters.isProduction,
    isKey: draftFilters.isKey,
    isMonitor: draftFilters.isMonitor,
    familyOptions: familyOptions.value,
    machineOptions: machineOptions.value.map((item) => item.value),
  });
});

watch(pruneSignature, () => {
  if (!draftWatchReady.value || suppressDraftPrune) {
    return;
  }
  pruneDraftSelections({ showHint: true });
});

// ─── Two-phase helpers ──────────────────────────────────────

/**
 * Build a snapshot string of "primary" params (those that require a new Oracle query).
 * Granularity is NOT primary — it can be re-derived from cache.
 */
function buildPrimarySnapshot(filters: Record<string, unknown>): string {
  const p = buildResourceHistoryQueryParams(filters);
  return JSON.stringify({
    start_date: p.start_date,
    end_date: p.end_date,
    workcenter_groups: p.workcenter_groups || [],
    locations: p.locations || [],
    families: p.families || [],
    resource_ids: p.resource_ids || [],
    is_production: p.is_production || '',
    is_key: p.is_key || '',
    is_monitor: p.is_monitor || '',
    package_groups: p.package_groups || [],
  });
}

function applyViewResult(result: Record<string, unknown>): void {
  const summary = (result.summary || {}) as Record<string, unknown>;
  summaryData.value = {
    kpi: mergeComputedKpi((summary.kpi || {}) as Record<string, unknown>),
    trend: ((summary.trend || []) as Record<string, unknown>[]).map((item) => mergeComputedKpi(item || {})),
    heatmap: (summary.heatmap || []) as Record<string, unknown>[],
    workcenter_comparison: (summary.workcenter_comparison || []) as Record<string, unknown>[],
  };

  const detail = (result.detail || {}) as Record<string, unknown>;
  detailData.value = Array.isArray(detail.data) ? detail.data : [];
  const detailByDate = (result.detail_by_date || {}) as Record<string, unknown>;
  detailByDateData.value = Array.isArray(detailByDate.data) ? detailByDate.data : [];
  resetHierarchyState();

  if (detail.truncated) {
    detailWarning.value = `明細資料超過 ${detail.max_records} 筆，僅顯示前 ${detail.max_records} 筆。`;
  } else {
    detailWarning.value = '';
  }
}

async function executePrimaryQuery() {
  const requestId = nextRequestId();

  // Cancel any in-progress async RQ job before starting a new query
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  asyncJobProgress.active = false;
  asyncJobProgress.jobId = null;
  asyncJobProgress.pct = 0;
  asyncJobProgress.progress = '';
  asyncJobProgress.status = null;
  asyncJobProgress.elapsedSeconds = 0;
  _stopElapsedTimer();

  const validationError = validateDateRange(committedFilters);
  if (validationError) {
    queryError.value = validationError;
    loading.initial = false;
    return;
  }

  loading.querying = true;
  loading.primaryQuery = true;
  queryError.value = '';
  detailWarning.value = '';
  exportMessage.value = '';

  // Discard any previous local-compute state before evaluating new response (Task 3.4)
  duckdb.deactivate();

  try {
    updateUrlState();

    const queryParams = buildResourceHistoryQueryParams(committedFilters);
    const body = {
      start_date: queryParams.start_date,
      end_date: queryParams.end_date,
      granularity: queryParams.granularity,
      workcenter_groups: queryParams.workcenter_groups || [],
      locations: queryParams.locations || [],
      families: queryParams.families || [],
      resource_ids: queryParams.resource_ids || [],
      is_production: !!queryParams.is_production,
      is_key: !!queryParams.is_key,
      is_monitor: !!queryParams.is_monitor,
      package_groups: queryParams.package_groups || [],
    };

    const response = await apiPost('/api/resource/history/query', body, {
      timeout: API_TIMEOUT,
      silent: true,
    });

    if (isStaleRequest(requestId)) return;

    const payload = unwrapApiResult(response, '查詢失敗') as Record<string, unknown>;
    const responseData = (payload?.data || {}) as Record<string, unknown>;

    // ── RQ async 202 path ─────────────────────────────────────────────────────
    // Backend returned {async: true, job_id, status_url} — long-range RQ job.
    // Short-circuit before the isBatch heuristic so the two polling mechanisms
    // do not collide (IP-6 constraint).
    if (responseData.async === true && responseData.job_id) {
      const jobId = String(responseData.job_id);
      const statusUrl = String(responseData.status_url || `/api/job/${jobId}?prefix=resource-history`);

      asyncJobProgress.active = true;
      asyncJobProgress.jobId = jobId;
      asyncJobProgress.status = 'queued';
      asyncJobProgress.progress = '';
      asyncJobProgress.pct = 0;
      asyncJobProgress.elapsedSeconds = 0;
      _startElapsedTimer();

      // Suspend loading indicators while polling (progress bar replaces generic loading state)
      loading.primaryQuery = false;
      loading.querying = false;
      loading.initial = false;

      const controller = new AbortController();
      _jobAbortController = controller;

      try {
        const finalStatus = await pollJobUntilComplete(statusUrl, {
          signal: controller.signal,
          onProgress: (statusResp) => {
            asyncJobProgress.status = statusResp.status;
            asyncJobProgress.progress = (statusResp.progress as string) || (statusResp.stage as string) || '';
            asyncJobProgress.pct = typeof statusResp.pct === 'number' ? statusResp.pct : 0;
          },
        });

        if (isStaleRequest(requestId)) return;

        // Job finished: query_id is at the top level of the job status response (NOT result?.query_id)
        const resultQueryId = String((finalStatus as Record<string, unknown>).query_id || '');
        if (!resultQueryId) {
          queryError.value = '查詢完成但未返回 query_id';
          return;
        }

        queryId.value = resultQueryId;
        lastPrimarySnapshot.value = buildPrimarySnapshot(committedFilters);
        updateUrlState();
        // refreshView handles spool/DuckDB eligibility — do NOT parse from job metadata
        await refreshView();
      } catch (err) {
        if (isStaleRequest(requestId)) return;
        const e = err as Error & { errorCode?: string };
        if (e?.name === 'AbortError') {
          // User cancelled — leave error blank; UI resets via asyncJobProgress.active = false
        } else if (e?.errorCode === 'JOB_FAILED') {
          queryError.value = e?.message || '查詢執行失敗';
        } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
          queryError.value = '查詢執行超時，請縮小日期範圍後重試';
        } else {
          queryError.value = (e as Error)?.message || '查詢執行發生錯誤';
        }
      } finally {
        if (_jobAbortController === controller) _jobAbortController = null;
        _stopElapsedTimer();
        asyncJobProgress.active = false;
      }
      return;
    }

    // ── Sync 200 path (unchanged from pre-change behavior) ────────────────────
    queryId.value = String(responseData.query_id || '');
    lastPrimarySnapshot.value = buildPrimarySnapshot(committedFilters);

    // Start progress polling if this is a batch query (total_chunks > 1) or
    // if the backend signals a deferred result via a batch flag.
    // We detect batch by checking the POST response for total_chunks; if absent,
    // we use the date-range heuristic (> 10 days triggers polling).
    const totalChunks = Number(responseData.total_chunks ?? 0);
    const startDate = new Date(String(committedFilters.startDate));
    const endDate = new Date(String(committedFilters.endDate));
    const diffDays = (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24);
    const isBatch = totalChunks > 1 || diffDays > 10;
    if (queryId.value && isBatch) {
      startPolling(queryId.value);
    }

    applyViewResult(responseData);

    // Attempt to activate local compute (Task 3.2). Deactivate any previous session first.
    duckdb.deactivate();
    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: (responseData.spool_download_url as string | undefined) ?? undefined,
      totalRowCount: Number(responseData.total_row_count || 0),
    });
    if (eligible) {
      try {
        await duckdb.activate(
          responseData.spool_download_url as string,
          (responseData.resource_metadata || {}) as Record<string, unknown>,
        );
      } catch (_) {
        // Activation failed — remain in server-view mode (Task 3.3)
      }
    }
  } catch (err) {
    const error = err as Error & { name?: string; status?: number };
    if (error?.name === 'AbortError') {
      queryError.value = '查詢逾時，請縮小日期範圍或資源篩選後重試';
    } else {
      queryError.value = error?.message || '查詢失敗';
    }
    summaryData.value = { kpi: {}, trend: [], heatmap: [], workcenter_comparison: [] };
    detailData.value = [];
    resetHierarchyState();
  } finally {
    stopPolling();
    loading.querying = false;
    loading.primaryQuery = false;
    loading.initial = false;
  }
}

async function refreshView() {
  if (!queryId.value) {
    await executePrimaryQuery();
    return;
  }

  loading.querying = true;
  queryError.value = '';

  try {
    updateUrlState();

    // Task 3.2: Use local compute when active; skip /view request
    if (duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          granularity: String(committedFilters.granularity || 'day'),
        });
        if (Array.isArray(result.detailByDate)) {
          detailByDateData.value = result.detailByDate;
        }
        applyViewResult(result as unknown as Record<string, unknown>);
        return;
      } catch (localErr) {
        // Task 3.3: Local compute failed — fall through to server /view
        console.warn('[resource-history] Local compute error, falling back to server:', localErr);
        duckdb.deactivate();
      }
    }

    // Server-side /view fallback (Task 3.3)
    const response = await apiGet('/api/resource/history/view', {
      timeout: API_TIMEOUT,
      silent: true,
      params: {
        query_id: queryId.value,
        granularity: String(committedFilters.granularity || 'day'),
      },
    });

    if ((response as Record<string, unknown>)?.success === false && String((response as Record<string, unknown>)?.error || '') === 'cache_expired') {
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }

    const payload = unwrapApiResult(response, '查詢失敗') as Record<string, unknown>;
    applyViewResult(payload.data as Record<string, unknown>);
  } catch (err) {
    const error = err as Error & { status?: number };
    if (error?.message === 'cache_expired' || error?.status === 410) {
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }
    queryError.value = error?.message || '查詢失敗';
  } finally {
    loading.querying = false;
  }
}

// ─── Filter actions ─────────────────────────────────────────

async function applyFilters() {
  const validationError = validateDateRange(draftFilters);
  if (validationError) {
    queryError.value = validationError;
    return;
  }
  pruneDraftSelections({ showHint: true });
  assignFilterState(committedFilters, draftFilters);

  const currentPrimary = buildPrimarySnapshot(committedFilters);
  if (queryId.value && currentPrimary === lastPrimarySnapshot.value) {
    await refreshView();
  } else {
    await executePrimaryQuery();
  }
}

async function clearFilters() {
  runWithDraftPruneSuppressed(() => {
    resetToDefaultFilters(draftFilters);
  });
  autoPruneHint.value = '';
  assignFilterState(committedFilters, draftFilters);
  await executePrimaryQuery();
}

function updateFilters(nextFilters: Record<string, unknown>): void {
  runWithDraftPruneSuppressed(() => {
    assignFilterState(draftFilters, nextFilters);
  });
  pruneDraftSelections({ showHint: true });
}

function handleToggleRow(rowId: string): void {
  hierarchyState[rowId] = !hierarchyState[rowId];
}

function handleToggleAllRows({ expand, rowIds }: { expand: boolean; rowIds?: string[] }): void {
  (rowIds || []).forEach((rowId) => {
    hierarchyState[rowId] = Boolean(expand);
  });
}

function exportCsv(): void {
  const rows = detailByDateData.value as Record<string, unknown>[];
  if (!rows.length) {
    queryError.value = '無資料可匯出，請先執行查詢';
    return;
  }

  const headers = ['工站', '型號', '設備', '日期', 'OU%', 'AVAIL%', 'PRD(h)', 'PRD%', 'SBY(h)', 'SBY%', 'UDT(h)', 'UDT%', 'SDT(h)', 'SDT%', 'EGT(h)', 'EGT%', 'NST(h)', 'NST%'];
  const lines: string[] = [headers.join(',')];

  for (const row of rows) {
    const cells = [
      row.workcenter,
      row.family,
      row.resource,
      row.date,
      row.ou_pct,
      row.availability_pct,
      row.prd_hours,
      row.prd_pct,
      row.sby_hours,
      row.sby_pct,
      row.udt_hours,
      row.udt_pct,
      row.sdt_hours,
      row.sdt_pct,
      row.egt_hours,
      row.egt_pct,
      row.nst_hours,
      row.nst_pct,
    ].map((v) => {
      const s = String(v ?? '');
      return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
    });
    lines.push(cells.join(','));
  }

  const bom = '﻿';
  const blob = new Blob([bom + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const filename = `resource_history_${committedFilters.startDate}_to_${committedFilters.endDate}.csv`;
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function initPage(): Promise<void> {
  resetToDefaultFilters(committedFilters);
  restoreCommittedFiltersFromUrl();
  runWithDraftPruneSuppressed(() => {
    assignFilterState(draftFilters, committedFilters);
  });

  try {
    await loadOptions();
    pruneDraftSelections({ showHint: true });
    assignFilterState(committedFilters, draftFilters);
  } catch (err) {
    queryError.value = (err as Error)?.message || '載入篩選選項失敗';
  }

  draftWatchReady.value = true;
  await executePrimaryQuery();
}

onMounted(() => {
  void initPage();
});
</script>

<template>
  <div class="resource-page theme-resource-history">
    <div class="dashboard">
      <FilterBar
        :filters="draftFilters"
        :options="filterBarOptions"
        :machine-options="machineOptions"
        :loading="loading.options || loading.querying"
        @update-filters="updateFilters"
        @query="applyFilters"
        @clear="clearFilters"
      />

      <ErrorBanner :message="queryError" :dismissible="false" />
      <p v-if="autoPruneHint" class="filter-indicator">{{ autoPruneHint }}</p>
      <p v-if="detailWarning" class="filter-indicator active">{{ detailWarning }}</p>
      <p v-if="exportMessage" class="filter-indicator active">{{ exportMessage }}</p>

      <!-- RQ async job progress (202 path) — replaces generic loading while polling -->
      <AsyncQueryProgress
        :active="asyncJobProgress.active"
        :progress="asyncJobProgress.progress"
        :pct="asyncJobProgress.pct"
        :elapsed-seconds="asyncJobProgress.elapsedSeconds"
        :status="asyncJobProgress.status"
        @cancel="cancelAsyncJob"
      />

      <div v-if="isPolling" class="mx-4 mb-4 rounded-lg bg-white p-4 shadow-sm" role="status" aria-live="polite">
        <div class="mb-2 flex items-center justify-between text-sm text-gray-600">
          <span>查詢中...</span>
          <span class="font-medium text-blue-600">{{ Math.round(progressPercent) }}%</span>
        </div>
        <div class="h-2 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            class="h-2 rounded-full bg-blue-500 transition-all duration-300"
            :style="{ width: progressPercent + '%' }"
            role="progressbar"
            :aria-valuenow="Math.round(progressPercent)"
            aria-valuemin="0"
            aria-valuemax="100"
          ></div>
        </div>
      </div>

      <KpiCards :kpi="summaryData.kpi" />

      <section class="section-card charts-section">
        <div class="section-inner">
          <div class="chart-grid">
            <TrendChart :trend="summaryData.trend || []" />
            <StackedChart :trend="summaryData.trend || []" />
            <ComparisonChart :comparison="summaryData.workcenter_comparison || []" />
            <HeatmapChart :heatmap="summaryData.heatmap || []" />
          </div>
        </div>
      </section>

      <div class="ui-table-wrap" :class="{ 'is-loading': loading.querying }">
        <DetailSection
          :detail-data="detailData"
          :detail-by-date="detailByDateData"
          :expanded-state="hierarchyState"
          :loading="loading.querying"
          @toggle-row="handleToggleRow"
          @toggle-all="handleToggleAllRows"
          @export-csv="exportCsv"
        />
      </div>
    </div>

    <LoadingOverlay v-if="loading.initial || loading.primaryQuery" tier="page" />
  </div>
</template>
