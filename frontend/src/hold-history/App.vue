<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import { apiGet, apiPost } from '../core/api';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result';
import { checkLocalComputeEligibility } from '../core/duckdb-activation-policy';
import { replaceRuntimeHistory } from '../core/shell-navigation';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useRequestGuard } from '../shared-composables/useRequestGuard';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';
import { useHoldHistoryDuckDB } from './useHoldHistoryDuckDB';
import { useAutoRefresh } from './useAutoRefresh';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';

import DailyTrend from './components/DailyTrend.vue';
import DetailTable from './components/DetailTable.vue';
import DurationChart from './components/DurationChart.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import RecordTypeFilter from './components/RecordTypeFilter.vue';
import ReasonPareto from './components/ReasonPareto.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 20;

// TODO: type — snapshot data shape from server API not yet formally typed; use Record for now
type SnapshotData = Record<string, unknown> | null;

// ── Feature flags (loaded from /api/hold-history/config) ─────────────────────
const todayModeEnabled = ref(true);
const autoRefreshSeconds = ref(60);

// ── Mode ──────────────────────────────────────────────────────────────────────
const mode = ref<'range' | 'today' | 'current'>('range');

// ── Today-mode state ──────────────────────────────────────────────────────────
const todaySnapshotData = ref<SnapshotData>(null);
const todayRecordType = ref('on_hold');
const todayLoading = ref(false);
const todayError = ref('');

// ── Current-mode state ────────────────────────────────────────────────────────
const currentSnapshotData = ref<SnapshotData>(null);
const currentRecordType = ref('on_hold');
const currentLoading = ref(false);
const currentError = ref('');

// ── Range-mode state ──────────────────────────────────────────────────────────
const queryId = ref('');
const duckdb = useHoldHistoryDuckDB();

// TODO: type — server and DuckDB trend data have same shape but server response not formally typed
type TrendDayRow = Record<string, unknown>;
const trendData = ref<{ days: TrendDayRow[] }>({ days: [] });
const reasonParetoData = ref<{ items: Record<string, unknown>[] }>({ items: [] });
const durationData = ref<{ items: Record<string, unknown>[] } & Record<string, unknown>>({ items: [] });
const detailData = ref({
  items: [] as unknown[],
  pagination: {
    page: 1,
    perPage: DEFAULT_PER_PAGE,
    total: 0,
    totalPages: 1,
  },
});

const page = ref(1);
const sortCol = ref('holdDate');
const sortDir = ref<'asc' | 'desc'>('desc');
const initialLoading = ref(true);
const paginationLoading = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const loading = reactive({
  global: false,
  primaryQuery: false,
  list: false,
});

const errorMessage = ref('');
const { nextRequestId, isStaleRequest } = useRequestGuard();

// ── Async job progress (202 path) ─────────────────────────────────────────────
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

/**
 * Cancel the currently running async job.
 * Aborts the polling loop and calls the abandon endpoint (best-effort).
 */
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

// ── Auto-refresh (today / current mode) ───────────────────────────────────────
const autoRefresh = useAutoRefresh({
  get intervalMs() { return autoRefreshSeconds.value * 1000; },
  fetchFn: () => {
    if (mode.value === 'current') return executeCurrentSnapshot({ silent: true });
    if (mode.value === 'today') return executeTodaySnapshot({ silent: true });
    return Promise.resolve();
  },
});

// ── Filter orchestrator (range mode) ─────────────────────────────────────────
const orchestrator = useFilterOrchestrator({
  fields: {
    startDate: { trigger: 'draft-apply', initial: '' },
    endDate: { trigger: 'draft-apply', initial: '' },
    holdType: { trigger: 'immediate', initial: 'quality' },
    recordType: { trigger: 'immediate', initial: ['new'] },
    reasonFilter: { trigger: 'immediate', initial: '' },
    durationFilter: { trigger: 'immediate', initial: '' },
  },
  dependencies: [
    { when: 'holdType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
    { when: 'holdType', then: ['recordType'], action: 'reset', value: ['new'] },
    { when: 'recordType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
  ],
  pagination: { resetOn: ['*'] },
  urlSync: { enabled: false },
  onFetch: (_committed) => {
    page.value = 1;
    updateUrlState();
    void refreshView();
  },
  onPrimaryQuery: (_committed) => {
    page.value = 1;
    updateUrlState();
    void executePrimaryQuery();
  },
});

// Convenience typed accessor — orchestrator.committed is Record<string, unknown>
// Fields are set from the fields config above (all strings or string[])
const committed = orchestrator.committed as {
  startDate: string;
  endDate: string;
  holdType: string;
  recordType: string | string[];
  reasonFilter: string;
  durationFilter: string;
};
const draft = orchestrator.draft as typeof committed;

// ── Helpers ───────────────────────────────────────────────────────────────────

function toDateString(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function getUrlParam(name: string): string {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function normalizeHoldType(value: unknown): string {
  const holdType = String(value || '').trim();
  if (holdType === 'quality' || holdType === 'non-quality' || holdType === 'all') {
    return holdType;
  }
  return 'quality';
}

function parseRecordTypeCsv(value: unknown): string[] {
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length > 0 ? [...new Set(parsed)] : ['new'];
}

function parseTodayRecordTypeCsv(value: unknown): string[] {
  const valid = new Set(['on_hold', 'new', 'release']);
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => valid.has(item));
  return parsed.length > 0 ? [...new Set(parsed)] : ['on_hold'];
}

function setDefaultDateRange() {
  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth();

  if (now.getDate() === 1) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
  }

  const start = new Date(year, month, 1);
  const end = new Date(year, month + 1, 0);
  committed.startDate = toDateString(start);
  draft.startDate = toDateString(start);
  committed.endDate = toDateString(end);
  draft.endDate = toDateString(end);
}

function normalizeListPayload(payload: Record<string, unknown> | null | undefined) {
  // TODO: type — list payload shape from server API not yet formally typed
  const pagination = (payload?.pagination || {}) as Record<string, unknown>;
  return {
    items: Array.isArray(payload?.items) ? (payload.items as unknown[]) : [],
    pagination: {
      page: Number(pagination.page || page.value || 1),
      perPage: Number(pagination.perPage || DEFAULT_PER_PAGE),
      total: Number(pagination.total || 0),
      totalPages: Number(pagination.totalPages || 1),
    },
  };
}

function updateUrlState() {
  const params = new URLSearchParams();

  params.set('mode', mode.value);

  if (mode.value === 'range') {
    if (committed.startDate) params.set('start_date', committed.startDate);
    if (committed.endDate) params.set('end_date', committed.endDate);
    if (committed.holdType) params.set('hold_type', committed.holdType);
    if (committed.reasonFilter) params.set('reason', committed.reasonFilter);
    if (committed.durationFilter) params.set('duration_range', committed.durationFilter);
    if (page.value > 1) params.set('page', String(page.value));
  } else {
    if (committed.holdType) params.set('hold_type', committed.holdType);
    const rt = mode.value === 'current' ? currentRecordType.value : todayRecordType.value;
    if (rt) params.set('record_type', rt);
    if (committed.reasonFilter) params.set('reason', committed.reasonFilter);
    if (committed.durationFilter) params.set('duration_range', committed.durationFilter);
    if (page.value > 1) params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/hold-history?${params.toString()}`);
}

function recordTypeCsv() {
  const rt = Array.isArray(committed.recordType) ? committed.recordType : [committed.recordType];
  return rt.join(',');
}

function applyViewResult(result: Record<string, unknown>, { listOnly = false } = {}): void {
  if (!listOnly) {
    // TODO: type — server view result shape not yet formally typed; cast to match ref type
    trendData.value = (result.trend as { days: TrendDayRow[] }) || trendData.value;
    reasonParetoData.value = (result.reason_pareto as { items: Record<string, unknown>[] }) || reasonParetoData.value;
    durationData.value = (result.duration as { items: Record<string, unknown>[] } & Record<string, unknown>) || durationData.value;
  }
  detailData.value = normalizeListPayload(result.list as Record<string, unknown>);
}

// ── Today mode API ────────────────────────────────────────────────────────────

async function executeTodaySnapshot({ silent = false } = {}): Promise<void> {
  if (!silent) {
    todayLoading.value = true;
    todayError.value = '';
  }

  try {
    const body: Record<string, unknown> = {
      snapshot_mode: 'today',
      hold_type: committed.holdType,
      record_type: todayRecordType.value,
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
      sort_col: sortCol.value,
      sort_dir: sortDir.value,
    };
    if (committed.reasonFilter) body.reason = committed.reasonFilter;
    if (committed.durationFilter) body.duration_range = committed.durationFilter;

    const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
    const result = unwrapApiResult(resp, '當日快照取得失敗') as SnapshotData;
    todaySnapshotData.value = result;
  } catch (err) {
    if (!silent) {
      todayError.value = (err as Error)?.message || '當日快照取得失敗';
    }
    throw err;
  } finally {
    if (!silent) {
      todayLoading.value = false;
    }
  }
}

// ── Current mode API ──────────────────────────────────────────────────────────

async function executeCurrentSnapshot({ silent = false } = {}): Promise<void> {
  if (!silent) {
    currentLoading.value = true;
    currentError.value = '';
  }

  try {
    const body: Record<string, unknown> = {
      snapshot_mode: 'current',
      hold_type: committed.holdType || 'quality',
      record_type: currentRecordType.value,
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
      sort_col: sortCol.value,
      sort_dir: sortDir.value,
    };
    if (committed.reasonFilter) body.reason = committed.reasonFilter;
    if (committed.durationFilter) body.duration_range = committed.durationFilter;

    const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
    const result = unwrapApiResult(resp, '現況快照取得失敗') as SnapshotData;
    currentSnapshotData.value = result;
  } catch (err) {
    if (!silent) {
      currentError.value = (err as Error)?.message || '現況快照取得失敗';
    }
    throw err;
  } finally {
    if (!silent) {
      currentLoading.value = false;
    }
  }
}

// ── Range mode API ────────────────────────────────────────────────────────────

async function executePrimaryQuery({ showOverlay = false } = {}): Promise<void> {
  const requestId = nextRequestId();

  // Cancel any in-progress async job before starting a new query
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

  if (showOverlay) {
    initialLoading.value = true;
  }

  loading.global = true;
  loading.primaryQuery = true;
  loading.list = true;
  errorMessage.value = '';
  refreshError.value = false;

  duckdb.deactivate();

  try {
    const body = {
      start_date: committed.startDate,
      end_date: committed.endDate,
      hold_type: committed.holdType,
      record_type: recordTypeCsv(),
    };

    const resp = await apiPost('/api/hold-history/query', body, { timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    // TODO: type — primary query response shape not yet formally typed
    const rawData = (resp as Record<string, unknown>)?.data as Record<string, unknown> | undefined;

    // ── Async 202 path ─────────────────────────────────────────────────────
    // Route returned {async: true, job_id, status_url} — long-range RQ job.
    if (rawData?.async === true && rawData.job_id) {
      const jobId = String(rawData.job_id);
      const statusUrl = String(rawData.status_url || `/api/job/${jobId}?prefix=hold-history`);

      asyncJobProgress.active = true;
      asyncJobProgress.jobId = jobId;
      asyncJobProgress.status = 'queued';
      asyncJobProgress.progress = '';
      asyncJobProgress.pct = 0;
      asyncJobProgress.elapsedSeconds = 0;
      _startElapsedTimer();

      // Suspend loading.primaryQuery while polling (progress bar replaces generic loading state)
      loading.primaryQuery = false;
      loading.global = false;
      loading.list = false;
      initialLoading.value = false;

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

        // Job finished: query_id is stored at the top level of the job status response.
        const resultQueryId = String((finalStatus as Record<string, unknown>).query_id || '');
        if (!resultQueryId) {
          errorMessage.value = '查詢完成但未返回 query_id';
          refreshError.value = true;
          return;
        }

        queryId.value = resultQueryId;
        updateUrlState();
        // Fetch full view data from server (spool info, DuckDB eligibility handled inside refreshView)
        await refreshView();

        refreshSuccess.value = true;
        setTimeout(() => { refreshSuccess.value = false; }, 1500);
      } catch (err) {
        if (isStaleRequest(requestId)) return;
        const e = err as Error & { errorCode?: string };
        if (e?.name === 'AbortError') {
          // User cancelled — leave error blank; UI resets via asyncJobProgress.active = false
        } else if (e?.errorCode === 'JOB_FAILED') {
          errorMessage.value = e?.message || '查詢執行失敗';
          refreshError.value = true;
        } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
          errorMessage.value = '查詢執行超時，請縮小日期範圍後重試';
          refreshError.value = true;
        } else {
          errorMessage.value = (e as Error)?.message || '查詢執行發生錯誤';
          refreshError.value = true;
        }
      } finally {
        if (_jobAbortController === controller) _jobAbortController = null;
        _stopElapsedTimer();
        asyncJobProgress.active = false;
      }
      return;
    }

    // ── Sync 200 path (unchanged from pre-change behavior) ────────────────
    const result = unwrapApiResult(resp, '主查詢執行失敗') as Record<string, unknown>;

    queryId.value = String(result.query_id || '');
    applyViewResult(result);
    updateUrlState();

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: result.spool_download_url as string | null | undefined,
      totalRowCount: Number(result.total_row_count || 0),
    });
    if (eligible) {
      try {
        await duckdb.activate(
          String(result.spool_download_url),
          (result.workcenter_mapping || {}) as Record<string, string>,
        );
      } catch (_) {
        // Activation failed — remain in server-view mode
      }
    }

    refreshSuccess.value = true;
    setTimeout(() => { refreshSuccess.value = false; }, 1500);
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    const e = err as Error & { name?: string };
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = e?.message || '主查詢執行失敗';
    }
    refreshError.value = true;
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.global = false;
    loading.primaryQuery = false;
    loading.list = false;
    initialLoading.value = false;
  }
}

async function refreshView({ listOnly = false } = {}): Promise<void> {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  if (!listOnly) {
    loading.global = true;
  }
  loading.list = true;
  errorMessage.value = '';

  try {
    if (duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          startDate: committed.startDate,
          endDate: committed.endDate,
          holdType: committed.holdType,
          recordTypes: Array.isArray(committed.recordType)
            ? committed.recordType
            : [committed.recordType || 'new'],
          reason: committed.reasonFilter || null,
          durationRange: committed.durationFilter || null,
          page: page.value,
          perPage: DEFAULT_PER_PAGE,
          sortCol: sortCol.value,
          sortDir: sortDir.value,
        });
        applyViewResult(result as unknown as Record<string, unknown>, { listOnly });
        return;
      } catch (localErr) {
        console.warn('[hold-history] Local compute error, falling back to server:', localErr);
        duckdb.deactivate();
      }
    }

    const params: Record<string, unknown> = {
      query_id: queryId.value,
      hold_type: committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
      sort_col: sortCol.value,
      sort_dir: sortDir.value,
    };

    if (committed.reasonFilter) params.reason = committed.reasonFilter;
    if (committed.durationFilter) params.duration_range = committed.durationFilter;

    const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT }) as Record<string, unknown>;
    if (isStaleRequest(requestId)) return;

    if (resp?.success === false && resp?.error === 'cache_expired') {
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '視圖查詢失敗') as Record<string, unknown>;
    applyViewResult(result, { listOnly });
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    errorMessage.value = (err as Error)?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.global = false;
    loading.list = false;
  }
}

async function refreshViewPage(): Promise<void> {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  paginationLoading.value = true;
  errorMessage.value = '';

  try {
    if (duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          startDate: committed.startDate,
          endDate: committed.endDate,
          holdType: committed.holdType,
          recordTypes: Array.isArray(committed.recordType)
            ? committed.recordType
            : [committed.recordType || 'new'],
          reason: committed.reasonFilter || null,
          durationRange: committed.durationFilter || null,
          page: page.value,
          perPage: DEFAULT_PER_PAGE,
          sortCol: sortCol.value,
          sortDir: sortDir.value,
        });
        detailData.value = normalizeListPayload(result.list as unknown as Record<string, unknown>);
        return;
      } catch (localErr) {
        console.warn('[hold-history] Local compute pagination error, falling back:', localErr);
        duckdb.deactivate();
      }
    }

    const params: Record<string, unknown> = {
      query_id: queryId.value,
      hold_type: committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
      sort_col: sortCol.value,
      sort_dir: sortDir.value,
    };

    if (committed.reasonFilter) params.reason = committed.reasonFilter;
    if (committed.durationFilter) params.duration_range = committed.durationFilter;

    const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    const result = unwrapApiResult(resp, '視圖查詢失敗') as Record<string, unknown>;
    detailData.value = normalizeListPayload(result.list as Record<string, unknown>);
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    const e = err as Error & { errorCode?: string; status?: number };
    if (e?.errorCode === 'CACHE_EXPIRED' || e?.status === 410) {
      paginationLoading.value = false;
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }
    errorMessage.value = e?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) return;
    paginationLoading.value = false;
  }
}

// ── Mode switch ───────────────────────────────────────────────────────────────

function handleModeChange(newMode: string): void {
  if (newMode === mode.value) return;

  autoRefresh.stop();

  if (newMode === 'today') {
    // Switch to today: clear date params, reset todayRecordType
    todayRecordType.value = 'on_hold';
    committed.reasonFilter = '';
    draft.reasonFilter = '';
    committed.durationFilter = '';
    draft.durationFilter = '';
    page.value = 1;
    mode.value = 'today';
    todaySnapshotData.value = null;
    updateUrlState();
    void executeTodaySnapshot().then(() => {
      autoRefresh.start();
    });
  } else if (newMode === 'current') {
    // Switch to current: reset currentRecordType, clear filters
    currentRecordType.value = 'on_hold';
    committed.reasonFilter = '';
    draft.reasonFilter = '';
    committed.durationFilter = '';
    draft.durationFilter = '';
    page.value = 1;
    mode.value = 'current';
    currentSnapshotData.value = null;
    updateUrlState();
    void executeCurrentSnapshot().then(() => {
      autoRefresh.start();
    });
  } else {
    // Switch to range: restore default date range, clear record_type from URL
    mode.value = 'range';
    committed.recordType = ['new'];
    draft.recordType = ['new'];
    committed.reasonFilter = '';
    draft.reasonFilter = '';
    committed.durationFilter = '';
    draft.durationFilter = '';
    page.value = 1;
    if (!committed.startDate || !committed.endDate) {
      setDefaultDateRange();
    }
    updateUrlState();
    void executePrimaryQuery({ showOverlay: true });
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────

const trendTypeKey = computed(() => (committed.holdType === 'non-quality' ? 'non_quality' : committed.holdType));

const selectedTrendDays = computed(() => {
  const days = Array.isArray(trendData.value?.days) ? trendData.value.days : [];
  return days.map((day) => {
    const key = trendTypeKey.value as string;
    const section = (day?.[key] || {}) as Record<string, unknown>;
    return {
      date: String(day?.date || ''),
      holdQty: Number(section.holdQty || 0),
      newHoldQty: Number(section.newHoldQty || 0),
      releaseQty: Number(section.releaseQty || 0),
      futureHoldQty: Number(section.futureHoldQty || 0),
      repeatQualityHoldQty: Number(section.repeatQualityHoldQty || 0),
    };
  });
});

const summary = computed(() => {
  if (mode.value === 'today') {
    return (todaySnapshotData.value?.summary as Record<string, number>) || {};
  }
  if (mode.value === 'current') {
    return (currentSnapshotData.value?.summary as Record<string, number>) || {};
  }

  const days = selectedTrendDays.value;

  const releaseQty = days.reduce((total, item) => total + Number(item.releaseQty || 0), 0);
  const newHoldQty = days.reduce((total, item) => total + Number(item.newHoldQty || 0), 0);
  const futureHoldQty = days.reduce((total, item) => total + Number(item.futureHoldQty || 0), 0);
  const repeatQualityHoldQty = days.reduce((total, item) => total + Number(item.repeatQualityHoldQty || 0), 0);
  const netChange = releaseQty - newHoldQty - futureHoldQty;

  const today = new Date().toISOString().slice(0, 10);
  const pastDays = days.filter((d) => d.date <= today);
  const lastDay = pastDays.length > 0 ? pastDays[pastDays.length - 1] : null;
  const stillOnHoldCount = Number(lastDay?.holdQty || 0);

  const dur = durationData.value || {};

  return {
    releaseQty,
    newHoldQty,
    futureHoldQty,
    repeatQualityHoldQty,
    stillOnHoldCount,
    netChange,
    avgReleasedHours: Number(dur.avgReleasedHours || 0),
    avgOnHoldHours: Number(dur.avgOnHoldHours || 0),
    maxReleasedHours: Number(dur.maxReleasedHours || 0),
    maxOnHoldHours: Number(dur.maxOnHoldHours || 0),
  };
});

const activeReasonParetoItems = computed(() => {
  if (mode.value === 'today') {
    const rp = todaySnapshotData.value?.reason_pareto as Record<string, unknown> | undefined;
    return (rp?.items as unknown[]) || [];
  }
  if (mode.value === 'current') {
    const rp = currentSnapshotData.value?.reason_pareto as Record<string, unknown> | undefined;
    return (rp?.items as unknown[]) || [];
  }
  return reasonParetoData.value?.items || [];
});

const activeDurationData = computed(() => {
  if (mode.value === 'today') {
    return (todaySnapshotData.value?.duration as { items: unknown[] }) || { items: [] };
  }
  if (mode.value === 'current') {
    return (currentSnapshotData.value?.duration as { items: unknown[] }) || { items: [] };
  }
  return durationData.value || { items: [] };
});

const activeDetailData = computed(() => {
  if (mode.value === 'today') {
    return normalizeListPayload(todaySnapshotData.value?.list as Record<string, unknown>);
  }
  if (mode.value === 'current') {
    return normalizeListPayload(currentSnapshotData.value?.list as Record<string, unknown>);
  }
  return detailData.value;
});

const activeLoading = computed(() => {
  if (mode.value === 'today') return todayLoading.value;
  if (mode.value === 'current') return currentLoading.value;
  return loading.list;
});

const activeGlobalLoading = computed(() => {
  if (mode.value === 'today') return todayLoading.value;
  if (mode.value === 'current') return currentLoading.value;
  return loading.global;
});

const todayEmptyState = computed(() => {
  if (mode.value !== 'today') return false;
  if (todayLoading.value) return false;
  const list = todaySnapshotData.value?.list as Record<string, unknown> | undefined;
  return ((list?.items as unknown[])?.length ?? 0) === 0;
});

const currentEmptyState = computed(() => {
  if (mode.value !== 'current') return false;
  if (currentLoading.value) return false;
  const list = currentSnapshotData.value?.list as Record<string, unknown> | undefined;
  return ((list?.items as unknown[])?.length ?? 0) === 0;
});

const holdTypeLabel = computed(() => {
  if (committed.holdType === 'non-quality') return '非品質異常';
  if (committed.holdType === 'all') return '全部';
  return '品質異常';
});

const staleLabel = computed(() => {
  if (!autoRefresh.isStale.value) return '';
  if (mode.value !== 'today' && mode.value !== 'current') return '';
  if (!autoRefresh.lastRefreshAt.value) return '⚠ 自動更新已暫停';
  const diff = Math.round((Date.now() - autoRefresh.lastRefreshAt.value.getTime()) / 1000);
  return `⚠ 資料可能過期（${diff}s 前更新）`;
});

const recordTypeModel = computed({
  get: (): string => {
    if (mode.value === 'today') return todayRecordType.value;
    if (mode.value === 'current') return currentRecordType.value;
    // committed.recordType is string | string[] in range mode; RecordTypeFilter expects string
    const rt = committed.recordType;
    return Array.isArray(rt) ? (rt[0] || 'new') : String(rt || 'new');
  },
  set: (val: string) => {
    if (mode.value === 'today') {
      todayRecordType.value = val;
    } else if (mode.value === 'current') {
      currentRecordType.value = val;
    } else {
      orchestrator.updateField('recordType', val);
    }
  },
});

// ── Event handlers ────────────────────────────────────────────────────────────

function handleApply(next: { startDate?: string; endDate?: string } | null): void {
  const nextStartDate = next?.startDate || '';
  const nextEndDate = next?.endDate || '';
  draft.startDate = nextStartDate;
  draft.endDate = nextEndDate;
  committed.reasonFilter = '';
  draft.reasonFilter = '';
  committed.durationFilter = '';
  draft.durationFilter = '';
  committed.recordType = ['new'];
  draft.recordType = ['new'];
  orchestrator.applyDraft();
}

function handleHoldTypeChange(nextHoldType: string): void {
  const holdType = nextHoldType || 'quality';
  if (committed.holdType === holdType) return;
  orchestrator.updateField('holdType', holdType);
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleRecordTypeChange() {
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleReasonToggle(reason: string): void {
  const nextReason = String(reason || '').trim();
  if (!nextReason) return;
  const current = committed.reasonFilter;
  orchestrator.updateField('reasonFilter', current === nextReason ? '' : nextReason);
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function clearReasonFilter() {
  if (!committed.reasonFilter) return;
  orchestrator.updateField('reasonFilter', '');
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleDurationToggle(range: string): void {
  const nextRange = String(range || '').trim();
  if (!nextRange) return;
  const current = committed.durationFilter;
  orchestrator.updateField('durationFilter', current === nextRange ? '' : nextRange);
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function clearDurationFilter() {
  if (!committed.durationFilter) return;
  orchestrator.updateField('durationFilter', '');
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleSort(payload: { key: string; direction: string }): void {
  sortCol.value = payload.key;
  sortDir.value = payload.direction as 'asc' | 'desc';
  page.value = 1;
  updateUrlState();
  if (mode.value === 'today') {
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    void executeCurrentSnapshot();
  } else {
    void refreshViewPage();
  }
}

function prevPage() {
  if (paginationLoading.value || page.value <= 1) return;
  page.value -= 1;
  updateUrlState();
  if (mode.value === 'today') {
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    void executeCurrentSnapshot();
  } else {
    void refreshViewPage();
  }
}

function nextPage() {
  if (paginationLoading.value) return;
  const totalPages = Number(activeDetailData.value?.pagination?.totalPages || 1);
  if (page.value >= totalPages) return;
  page.value += 1;
  updateUrlState();
  if (mode.value === 'today') {
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    void executeCurrentSnapshot();
  } else {
    void refreshViewPage();
  }
}

// ── CSV export ────────────────────────────────────────────────────────────────

const exportLoading = ref(false);

function _toCsvField(value: unknown): string {
  const s = String(value ?? '');
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

function _buildCsv(items: Record<string, unknown>[]): string {
  const headers = [
    'Lot ID', 'WorkOrder', 'Product', '站別', 'Hold Reason',
    '數量', 'Hold 時間', 'Hold 人員', 'Hold Comment',
    'Release 時間', 'Release 人員', 'Release Comment',
    '時長(hr)', 'NCR', 'Future Hold Comment',
  ];
  const rows = items.map((r) => [
    r.lotId, r.workorder, r.product, r.workcenter, r.holdReason,
    r.qty, r.holdDate, r.holdEmp, r.holdComment,
    r.releaseDate, r.releaseEmp, r.releaseComment,
    r.holdHours, r.ncr, r.futureHoldComment,
  ].map(_toCsvField).join(','));
  return [headers.join(','), ...rows].join('\n');
}

function _downloadCsv(content: string, filename: string): void {
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function handleExport(): Promise<void> {
  if (exportLoading.value) return;
  exportLoading.value = true;
  try {
    let items: Record<string, unknown>[] = [];

    if (mode.value === 'today' || mode.value === 'current') {
      const body = {
        snapshot_mode: mode.value === 'current' ? 'current' : 'today',
        hold_type: committed.holdType,
        record_type: mode.value === 'current' ? currentRecordType.value : todayRecordType.value,
        export: true,
      };
      const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
      // TODO: type — export response shape not yet formally typed
      const result = unwrapApiResult(resp, '匯出失敗') as Record<string, unknown>;
      items = ((result?.list as Record<string, unknown>)?.items as Record<string, unknown>[]) || [];
    } else {
      const params = {
        query_id: queryId.value,
        hold_type: committed.holdType,
        record_type: recordTypeCsv(),
        export: 1,
      };
      const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT });
      // TODO: type — export response shape not yet formally typed
      const result = unwrapApiResult(resp, '匯出失敗') as Record<string, unknown>;
      items = ((result?.list as Record<string, unknown>)?.items as Record<string, unknown>[]) || [];
    }

    if (!items.length) return;
    const dateStr = new Date().toISOString().slice(0, 10);
    _downloadCsv(_buildCsv(items), `hold-history-${dateStr}.csv`);
  } catch (err) {
    console.error('[hold-history] CSV export failed:', err);
  } finally {
    exportLoading.value = false;
  }
}

async function manualRefresh() {
  page.value = 1;
  committed.reasonFilter = '';
  draft.reasonFilter = '';
  committed.durationFilter = '';
  draft.durationFilter = '';
  updateUrlState();
  if (mode.value === 'today') {
    await executeTodaySnapshot();
  } else if (mode.value === 'current') {
    await executeCurrentSnapshot();
  } else {
    await executePrimaryQuery();
  }
}

// ── Watch todayRecordType / currentRecordType (update URL only; actual fetch triggered by handler) ─
watch(todayRecordType, () => {
  if (mode.value === 'today') updateUrlState();
});

watch(currentRecordType, () => {
  if (mode.value === 'current') updateUrlState();
});

// ── Mount ─────────────────────────────────────────────────────────────────────

onMounted(async () => {
  // Load feature flags
  try {
    // TODO: type — config API response shape not formally typed; cast via Record
    const resp = await apiGet('/api/hold-history/config') as Record<string, unknown>;
    const respData = resp?.data as Record<string, unknown> | undefined;
    if (respData) {
      todayModeEnabled.value = respData.today_mode_enabled !== false;
      if (respData.auto_refresh_seconds) {
        autoRefreshSeconds.value = Number(respData.auto_refresh_seconds) || 60;
      }
    }
  } catch {
    // default values already set
  }

  // Read URL params
  const urlMode = getUrlParam('mode');
  const initMode = (urlMode === 'today' && todayModeEnabled.value) ? 'today'
                 : (urlMode === 'current' && todayModeEnabled.value) ? 'current'
                 : 'range';
  mode.value = initMode;

  const startDate = getUrlParam('start_date');
  const endDate = getUrlParam('end_date');
  if (startDate && endDate) {
    committed.startDate = startDate;
    draft.startDate = startDate;
    committed.endDate = endDate;
    draft.endDate = endDate;
  } else {
    setDefaultDateRange();
  }

  const initHoldType = normalizeHoldType(getUrlParam('hold_type'));
  committed.holdType = initHoldType;
  draft.holdType = initHoldType;

  const initReason = getUrlParam('reason');
  committed.reasonFilter = initReason;
  draft.reasonFilter = initReason;

  const initDuration = getUrlParam('duration_range');
  committed.durationFilter = initDuration;
  draft.durationFilter = initDuration;

  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }

  if (initMode === 'today') {
    const initTodayRt = parseTodayRecordTypeCsv(getUrlParam('record_type'));
    todayRecordType.value = Array.isArray(initTodayRt) ? (initTodayRt[0] || 'on_hold') : (initTodayRt || 'on_hold');
    updateUrlState();
    await executeTodaySnapshot();
    initialLoading.value = false;
    autoRefresh.start();
  } else if (initMode === 'current') {
    const initCurrentRt = parseTodayRecordTypeCsv(getUrlParam('record_type'));
    currentRecordType.value = Array.isArray(initCurrentRt) ? (initCurrentRt[0] || 'on_hold') : (initCurrentRt || 'on_hold');
    updateUrlState();
    await executeCurrentSnapshot();
    initialLoading.value = false;
    autoRefresh.start();
  } else {
    const initRecordType = parseRecordTypeCsv(getUrlParam('record_type'));
    committed.recordType = initRecordType;
    draft.recordType = initRecordType;
    updateUrlState();
    void executePrimaryQuery({ showOverlay: true });
  }
});
</script>

<template>
  <div class="dashboard hold-history-page theme-hold-history" data-testid="hold-history-app">
    <ErrorBanner :message="errorMessage || todayError || currentError" :dismissible="false" data-testid="error-banner" />

    <!-- Async query progress bar (shown when POST /api/hold-history/query returns 202) -->
    <!-- AC-5: only shown for long-range queries; short-range path is unchanged -->
    <AsyncQueryProgress
      data-testid="loading-state"
      :active="asyncJobProgress.active"
      :progress="asyncJobProgress.progress"
      :pct="asyncJobProgress.pct"
      :elapsed-seconds="asyncJobProgress.elapsedSeconds"
      :status="asyncJobProgress.status"
      :can-cancel="true"
      @cancel="cancelAsyncJob"
    />

    <FilterBar
      :start-date="committed.startDate"
      :end-date="committed.endDate"
      :hold-type="committed.holdType"
      :mode="mode"
      :today-mode-enabled="todayModeEnabled"
      :disabled="activeGlobalLoading"
      @apply="handleApply"
      @hold-type-change="handleHoldTypeChange"
      @mode-change="handleModeChange"
    />

    <div class="hold-history-summary-row" data-testid="results-summary">
      <SummaryCards :summary="summary" :mode="mode" />
    </div>

    <!-- DailyTrend hidden in today mode -->
    <DailyTrend v-if="mode === 'range'" :days="selectedTrendDays" />

    <RecordTypeFilter
      v-model="recordTypeModel"
      :mode="mode"
      :disabled="activeGlobalLoading"
      @update:model-value="handleRecordTypeChange"
    />

    <section class="hold-history-chart-grid">
      <ReasonPareto
        :items="(activeReasonParetoItems as Record<string, unknown>[])"
        :active-reason="committed.reasonFilter"
        @toggle="handleReasonToggle"
      />
      <DurationChart
        :items="(activeDurationData.items as Record<string, unknown>[] || [])"
        :active-range="committed.durationFilter"
        @toggle="handleDurationToggle"
      />
    </section>

    <FilterIndicator
      :reason="committed.reasonFilter"
      :duration-range="committed.durationFilter"
      @clear-reason="clearReasonFilter"
      @clear-duration="clearDurationFilter"
    />

    <EmptyState
      v-if="todayEmptyState"
      data-testid="empty-state"
      message="今日無符合條件的 lot"
    />
    <EmptyState
      v-else-if="currentEmptyState"
      data-testid="empty-state"
      message="現況無符合條件的 lot"
    />

    <div v-else class="ui-table-wrap">
      <DetailTable
        :items="activeDetailData.items || []"
        :pagination="activeDetailData.pagination"
        :loading="activeLoading"
        :paginating="paginationLoading"
        :exporting="exportLoading"
        :error-message="errorMessage || todayError || currentError"
        :server-sort="true"
        @prev-page="prevPage"
        @next-page="nextPage"
        @export="handleExport"
        @sort="handleSort"
      />
    </div>
  </div>

  <!-- css-contract Rule 4.6: LoadingOverlay must be suppressed while asyncJobProgress.active -->
  <LoadingOverlay v-if="(initialLoading || loading.primaryQuery) && !asyncJobProgress.active" tier="page" />
</template>
