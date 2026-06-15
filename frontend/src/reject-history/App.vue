<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api';
import { unwrapApiResult } from '../core/unwrap-api-result';
import { isDuckDBSupported } from '../core/duckdb-client';
import {
  buildViewParams,
  parseMultiLineInput,
  PRIMARY_QUERY_MAX_DAYS,
  validateDateRange,
} from '../core/reject-history-filters';
import { replaceRuntimeHistory } from '../core/shell-navigation';
import { postExport } from '../core/post-export';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useRejectHistoryDuckDB } from './useRejectHistoryDuckDB';
import type { DetailRow, SummaryData } from './useRejectHistoryDuckDB';

import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import DetailTable from './components/DetailTable.vue';
import FilterPanel from './components/FilterPanel.vue';
import ParetoGrid from './components/ParetoGrid.vue';
import SummaryCards from './components/SummaryCards.vue';
import TrendChart from './components/TrendChart.vue';

// ── Local type aliases ────────────────────────────────────────────────────────

interface DraftFilters {
  startDate: string;
  endDate: string;
  includeExcludedScrap: boolean;
  excludeMaterialScrap: boolean;
  excludePbDiode: boolean;
}

interface CommittedPrimary {
  mode: string;
  startDate: string;
  endDate: string;
  containerInputType: string;
  containerValues: string[];
  includeExcludedScrap: boolean;
  excludeMaterialScrap: boolean;
  excludePbDiode: boolean;
}

interface SupplementaryFilters {
  packages: string[];
  workcenterGroups: string[];
  reasons: string[];
}

interface AvailableFiltersState {
  workcenterGroups: string[];
  packages: string[];
  reasons: string[];
}

interface LoadingState {
  initial: boolean;
  querying: boolean;
  list: boolean;
  pareto: boolean;
  exporting: boolean;
}

interface JobProgressState {
  active: boolean;
  jobId: string | null;
  status: string | null;
  progress: string;
  pct: number;
  elapsedSeconds: number;
}

interface ResolutionInfo {
  resolved_count: number;
  expansion_info?: Record<string, unknown>;
  not_found?: string[];
}

interface DetailPaginationState {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
}

interface DetailState {
  items: DetailRow[];
  pagination: DetailPaginationState;
}

interface ParetoItemData {
  reason: string;
  metric_value: number;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  count: number;
  pct: number;
  cumPct: number;
}

interface ParetoDimensionState {
  items: ParetoItemData[];
  dimension: string;
  metric_mode: string;
}

interface ParetoDataState {
  reason: ParetoDimensionState;
  package: ParetoDimensionState;
  type: ParetoDimensionState;
}

interface ParetoSelectionsState {
  reason: string[];
  package: string[];
  type: string[];
}

interface FilterChip {
  key: string;
  label: string;
  removable: boolean;
  type: string;
  value: string;
  dimension?: string;
}

interface KpiCard {
  key: string;
  label: string;
  value: number;
  lane: string;
  isPct: boolean;
}

interface TrendItem {
  bucket_date: string;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  REJECT_RATE_PCT: number;
  DEFECT_RATE_PCT: number;
}

interface AnalyticsRawItem {
  bucket_date: string;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 20;
const DUCKDB_THRESHOLD = 5000;
const PARETO_DIMENSIONS: string[] = ['reason', 'package', 'type'];
const PARETO_DISPLAY_SCOPE_FIXED = 'top20';
const PARETO_SELECTION_PARAM_MAP: Record<string, string> = {
  reason: 'sel_reason',
  package: 'sel_package',
  type: 'sel_type',
};

function createEmptyParetoSelections(): ParetoSelectionsState {
  return {
    reason: [],
    package: [],
    type: [],
  };
}

function createEmptyParetoData(): ParetoDataState {
  return {
    reason: { items: [], dimension: 'reason', metric_mode: 'reject_total' },
    package: { items: [], dimension: 'package', metric_mode: 'reject_total' },
    type: { items: [], dimension: 'type', metric_mode: 'reject_total' },
  };
}

function getDimensionLabel(dimension: string): string {
  switch (dimension) {
    case 'reason':
      return '不良原因';
    case 'package':
      return 'PACKAGE';
    case 'type':
      return 'TYPE';
    default:
      return 'Pareto';
  }
}

// ---- Primary query form state ----
const queryMode = ref<string>('date_range');
const containerInputType = ref<string>('lot');
const containerInput = ref<string>('');

const draftFilters = reactive<DraftFilters>({
  startDate: '',
  endDate: '',
  includeExcludedScrap: false,
  excludeMaterialScrap: true,
  excludePbDiode: true,
});

// ---- Committed primary params (for URL + chips) ----
const committedPrimary = reactive<CommittedPrimary>({
  mode: 'date_range',
  startDate: '',
  endDate: '',
  containerInputType: 'lot',
  containerValues: [],
  includeExcludedScrap: false,
  excludeMaterialScrap: true,
  excludePbDiode: true,
});

// ---- Query result state ----
const queryId = ref<string>('');
const resolutionInfo = ref<ResolutionInfo | null>(null);
const availableFilters = ref<AvailableFiltersState>({ workcenterGroups: [], packages: [], reasons: [] });

// ---- Supplementary filters (post-query, applied via /view) ----
const supplementaryFilters = reactive<SupplementaryFilters>({
  packages: [],
  workcenterGroups: [],
  reasons: [],
});

// ---- Interactive state ----
const page = ref<number>(1);
const selectedTrendDates = ref<string[]>([]);
const trendLegendSelected = ref<Record<string, boolean>>({ '扣帳報廢量': true, '不扣帳報廢量': true });
const paretoSelections = reactive<ParetoSelectionsState>(createEmptyParetoSelections());
const paretoData = reactive<ParetoDataState>(createEmptyParetoData());

// ---- Data state ----
const summary = ref<SummaryData>({
  MOVEIN_QTY: 0,
  REJECT_TOTAL_QTY: 0,
  DEFECT_QTY: 0,
  REJECT_RATE_PCT: 0,
  DEFECT_RATE_PCT: 0,
  REJECT_SHARE_PCT: 0,
  AFFECTED_LOT_COUNT: 0,
  AFFECTED_WORKORDER_COUNT: 0,
});
const analyticsRawItems = ref<AnalyticsRawItem[]>([]);
const detail = ref<DetailState>({
  items: [],
  pagination: {
    page: 1,
    perPage: DEFAULT_PER_PAGE,
    total: 0,
    totalPages: 1,
  },
});
const detailSortCol = ref('');
const detailSortDir = ref<'asc' | 'desc'>('asc');

// ---- Loading / error state ----
const loading = reactive<LoadingState>({
  initial: false,
  querying: false,
  list: false,
  pareto: false,
  exporting: false,
});
const paginationLoading = ref<boolean>(false);
const errorMessage = ref<string>('');
const partialFailureWarning = ref<string>('');
const lastQueryAt = ref<string>('');
const refreshSuccess = ref<boolean>(false);
const refreshError = ref<boolean>(false);

// ---- DuckDB-WASM state ----
const duckdb = useRejectHistoryDuckDB();
const duckdbMode = ref<boolean>(false);   // true when frontend DuckDB-WASM has taken over view computation

// ---- Async job progress state ----
const jobProgress = reactive<JobProgressState>({
  active: false,
  jobId: null,
  status: null,
  progress: '',
  pct: 0,
  elapsedSeconds: 0,
});
let _jobAbortController: AbortController | null = null;

// ---- Request staleness tracking ----
let activeRequestId = 0;
let activeParetoRequestId = 0;

function nextRequestId(): number {
  activeRequestId += 1;
  return activeRequestId;
}

function isStaleRequest(id: number): boolean {
  return id !== activeRequestId;
}

function nextParetoRequestId(): number {
  activeParetoRequestId += 1;
  return activeParetoRequestId;
}

function isStaleParetoRequest(id: number): boolean {
  return id !== activeParetoRequestId;
}

// -- useFilterOrchestrator: two-phase (primary query -> supplementary filters unlock) --
// TODO: type — useFilterOrchestrator accepts a loose config object; _committed param is untyped from the JS composable
const filterOrchestrator = useFilterOrchestrator({
  fields: {
    startDate:            { trigger: 'draft-apply', initial: '' },
    endDate:              { trigger: 'draft-apply', initial: '' },
    includeExcludedScrap: { trigger: 'draft-apply', initial: false },
    excludeMaterialScrap: { trigger: 'draft-apply', initial: true },
    excludePbDiode:       { trigger: 'draft-apply', initial: true },
    packages:             { trigger: 'immediate', initial: [] },
    workcenterGroups:     { trigger: 'immediate', initial: [] },
    reasons:              { trigger: 'immediate', initial: [] },
  },
  pagination: { resetOn: ['*'] },
  onPrimaryQuery(_committed) {
    // Primary query (Apply) -> executePrimaryQuery
    void executePrimaryQuery();
  },
  onViewRefresh(_committed) {
    // Supplementary filter change -> refreshView + fetchBatchPareto
    page.value = 1;
    selectedTrendDates.value = [];
    resetParetoSelections();
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
  },
});

// ---- Helpers ----
function toDateString(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function setDefaultDateRange(): void {
  const today = new Date();
  const end = new Date(today);
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  draftFilters.startDate = toDateString(start);
  draftFilters.endDate = toDateString(end);
}

function metricFilterParam(): string {
  const mode = paretoMetricMode.value;
  if (mode === 'reject' || mode === 'defect') return mode;
  return 'all';
}

function paretoMetricApiMode(): string {
  return paretoMetricMode.value === 'defect' ? 'defect' : 'reject_total';
}

// unwrapApiResult imported from ../core/unwrap-api-result

function resetParetoSelections(): void {
  for (const dimension of PARETO_DIMENSIONS) {
    paretoSelections[dimension as keyof ParetoSelectionsState] = [];
  }
}

function resetParetoData(): void {
  for (const dimension of PARETO_DIMENSIONS) {
    paretoData[dimension as keyof ParetoDataState] = {
      items: [],
      dimension,
      metric_mode: paretoMetricApiMode(),
    };
  }
}

function buildBatchParetoParams(): Record<string, unknown> {
  const params: Record<string, unknown> = {
    query_id: queryId.value,
    metric_mode: paretoMetricApiMode(),
    pareto_scope: 'top80',
    pareto_display_scope: PARETO_DISPLAY_SCOPE_FIXED,
    include_excluded_scrap: committedPrimary.includeExcludedScrap ? 'true' : 'false',
    exclude_material_scrap: committedPrimary.excludeMaterialScrap ? 'true' : 'false',
    exclude_pb_diode: committedPrimary.excludePbDiode ? 'true' : 'false',
  };

  if (supplementaryFilters.packages.length > 0) {
    params.packages = supplementaryFilters.packages;
  }
  if (supplementaryFilters.workcenterGroups.length > 0) {
    params.workcenter_groups = supplementaryFilters.workcenterGroups;
  }
  if (supplementaryFilters.reasons.length > 0) {
    params.reasons = supplementaryFilters.reasons;
  }
  if (selectedTrendDates.value.length > 0) {
    params.trend_dates = selectedTrendDates.value;
  }
  for (const [dimension, key] of Object.entries(PARETO_SELECTION_PARAM_MAP)) {
    const sel = paretoSelections[dimension as keyof ParetoSelectionsState];
    if (sel?.length > 0) {
      params[key] = sel;
    }
  }
  return params;
}

async function fetchBatchPareto(): Promise<void> {
  if (!queryId.value) return;
  // In DuckDB mode, batch_pareto is computed inside refreshView() — skip server call.
  if (duckdbMode.value && duckdb.isActive.value) return;

  const requestId = nextParetoRequestId();
  loading.pareto = true;

  try {
    const resp = await apiPost('/api/reject-history/batch-pareto', buildBatchParetoParams(), {
      timeout: API_TIMEOUT,
    });
    if (isStaleParetoRequest(requestId)) return;

    // TODO: type — resp is untyped from core/api (JS, not yet migrated); cast via unknown
    const respAny = resp as Record<string, unknown>;
    if (respAny?.success === false && respAny?.error === 'cache_miss') {
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '查詢批次 Pareto 失敗') as Record<string, unknown> | null | undefined;
    const resultData = (result?.data as Record<string, unknown> | undefined);
    const dimensions = (resultData?.dimensions || {}) as Record<string, ParetoDimensionState>;
    for (const dimension of PARETO_DIMENSIONS) {
      paretoData[dimension as keyof ParetoDataState] = dimensions[dimension] || {
        items: [],
        dimension,
        metric_mode: paretoMetricApiMode(),
      };
    }
  } catch (err) {
    if (isStaleParetoRequest(requestId)) return;
    resetParetoData();
    const e = err as Record<string, unknown>;
    if (e?.name !== 'AbortError') {
      errorMessage.value = String(e?.message || '查詢批次 Pareto 失敗');
    }
  } finally {
    if (!isStaleParetoRequest(requestId)) {
      loading.pareto = false;
    }
  }
}

// ---- Primary query (POST /query → Oracle → cache) ----
function cancelAsyncJob(): void {
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  jobProgress.active = false;
}

async function _loadViewAfterQuery(queryIdValue: string): Promise<void> {
  // After a successful query (sync or async), load view data via /view
  committedPrimary.mode = queryMode.value;
  committedPrimary.startDate = draftFilters.startDate;
  committedPrimary.endDate = draftFilters.endDate;
  committedPrimary.containerInputType = containerInputType.value;
  committedPrimary.containerValues =
    queryMode.value === 'container' ? parseMultiLineInput(containerInput.value) : [];
  committedPrimary.includeExcludedScrap = draftFilters.includeExcludedScrap;
  committedPrimary.excludeMaterialScrap = draftFilters.excludeMaterialScrap;
  committedPrimary.excludePbDiode = draftFilters.excludePbDiode;

  queryId.value = queryIdValue;
}

async function _applyQueryResult(result: Record<string, unknown>): Promise<void> {
  const meta = (result.meta || {}) as Record<string, unknown>;
  if (meta.has_partial_failure) {
    const failedChunkCount = Number(meta.failed_chunk_count || 0);
    const failedRanges: Array<{ start: string; end: string }> = Array.isArray(meta.failed_ranges)
      ? (meta.failed_ranges as Array<{ start: string; end: string }>)
      : [];
    if (failedRanges.length > 0) {
      const rangesText = failedRanges
        .map((item) => `${item.start} ~ ${item.end}`)
        .join('、');
      partialFailureWarning.value = `警告：以下日期區間的資料擷取失敗（${failedChunkCount} 個批次）：${rangesText}。目前顯示結果可能不完整。`;
    } else {
      partialFailureWarning.value = `警告：${failedChunkCount} 個查詢批次的資料擷取失敗。目前顯示結果可能不完整。`;
    }
  }

  resolutionInfo.value = (result.resolution_info as ResolutionInfo | null | undefined) ?? null;
  const af = (result.available_filters || {}) as Record<string, unknown>;
  availableFilters.value = {
    workcenterGroups: (af.workcenter_groups as string[] | undefined) || (af.workcenterGroups as string[] | undefined) || [],
    packages: (af.packages as string[] | undefined) || [],
    reasons: (af.reasons as string[] | undefined) || [],
  };

  supplementaryFilters.packages = [];
  supplementaryFilters.workcenterGroups = [];
  supplementaryFilters.reasons = [];
  page.value = 1;
  selectedTrendDates.value = [];
  resetParetoSelections();
  resetParetoData();

  analyticsRawItems.value = Array.isArray(result.analytics_raw)
    ? (result.analytics_raw as AnalyticsRawItem[])
    : [];
  summary.value = (result.summary as SummaryData) || summary.value;
  detail.value = (result.detail as DetailState) || detail.value;

  // Activate DuckDB-WASM mode for large datasets
  const totalRowCount = (result.total_row_count as number | undefined) ?? 0;
  const spoolUrl = result.spool_download_url as string | undefined;
  if (spoolUrl && totalRowCount >= DUCKDB_THRESHOLD && isDuckDBSupported() && !duckdbMode.value) {
    try {
      await duckdb.activate(spoolUrl);
      duckdbMode.value = true;
    } catch (err) {
      console.warn('[DuckDB] activation failed, staying in server mode:', err);
    }
  }

  // When DuckDB mode is active, refreshView() computes both view data and pareto;
  // otherwise, fetch pareto from server separately.
  if (duckdbMode.value && duckdb.isActive.value) {
    await refreshView();
  } else {
    await fetchBatchPareto();
  }

  const _now = new Date();
  const _pad = (n: number) => String(n).padStart(2, '0');
  lastQueryAt.value = `${_now.getFullYear()}-${_pad(_now.getMonth() + 1)}-${_pad(_now.getDate())} ${_pad(_now.getHours())}:${_pad(_now.getMinutes())}:${_pad(_now.getSeconds())}`;
  updateUrlState();
}

async function executePrimaryQuery(): Promise<void> {
  const requestId = nextRequestId();
  loading.querying = true;
  loading.list = true;
  paginationLoading.value = false;
  errorMessage.value = '';
  partialFailureWarning.value = '';
  refreshError.value = false;
  cancelAsyncJob();

  try {
    const body: Record<string, unknown> = { mode: queryMode.value };

    if (queryMode.value === 'date_range') {
      const dateValidationError = validateDateRange(
        draftFilters.startDate,
        draftFilters.endDate,
      );
      if (dateValidationError) {
        errorMessage.value = dateValidationError as string;
        return;
      }
      body.start_date = draftFilters.startDate;
      body.end_date = draftFilters.endDate;
    } else {
      body.container_input_type = containerInputType.value;
      body.container_values = parseMultiLineInput(containerInput.value);
    }

    body.include_excluded_scrap = draftFilters.includeExcludedScrap;
    body.exclude_material_scrap = draftFilters.excludeMaterialScrap;
    body.exclude_pb_diode = draftFilters.excludePbDiode;

    // Reset display state before new query — hide stale data from previous queryId
    queryId.value = '';
    analyticsRawItems.value = [];
    summary.value = { MOVEIN_QTY: 0, REJECT_TOTAL_QTY: 0, DEFECT_QTY: 0, REJECT_RATE_PCT: 0, DEFECT_RATE_PCT: 0, REJECT_SHARE_PCT: 0, AFFECTED_LOT_COUNT: 0, AFFECTED_WORKORDER_COUNT: 0 };
    detail.value = { items: [], pagination: { page: 1, perPage: DEFAULT_PER_PAGE, total: 0, totalPages: 1 } };
    supplementaryFilters.packages = [];
    supplementaryFilters.workcenterGroups = [];
    supplementaryFilters.reasons = [];
    availableFilters.value = { workcenterGroups: [], packages: [], reasons: [] };
    resolutionInfo.value = null;
    page.value = 1;
    selectedTrendDates.value = [];
    resetParetoSelections();
    resetParetoData();

    const resp = await apiPost('/api/reject-history/query', body, { timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    // ---- Async 202 path ----
    // TODO: type — resp is untyped from core/api (JS, not yet migrated); cast via Record<string, unknown>
    const respAny = resp as Record<string, unknown>;
    const respData = (respAny?.data || {}) as Record<string, unknown>;
    if (respAny?._status === 202 || (respData.async === true && respData.job_id)) {
      const jobId = respData.job_id as string;
      const statusUrl = (respData.status_url as string | undefined) || `/api/reject-history/job/${jobId}`;
      const preQueryId = respData.query_id as string;

      jobProgress.active = true;
      jobProgress.jobId = jobId;
      jobProgress.status = 'queued';
      jobProgress.progress = '';
      jobProgress.pct = 0;

      const controller = new AbortController();
      _jobAbortController = controller;

      try {
        await pollJobUntilComplete(statusUrl, {
          signal: controller.signal,
          onProgress: (statusResp: Record<string, unknown>) => {
            if (isStaleRequest(requestId)) return;
            jobProgress.status = statusResp.status as string;
            jobProgress.progress = (statusResp.progress as string) || '';
            jobProgress.pct = (statusResp.pct as number) || 0;
            jobProgress.elapsedSeconds = (statusResp.elapsed_seconds as number) || 0;
          },
        });
      } finally {
        if (_jobAbortController === controller) _jobAbortController = null;
        jobProgress.active = false;
      }

      if (isStaleRequest(requestId)) return;

      // Load view data using the pre-computed query_id from the 202 response
      await _loadViewAfterQuery(preQueryId);

      // Refresh view to populate result data from cache
      await refreshView();

      // refreshView() increments activeRequestId, making the outer finally stale.
      // Explicitly clear loading state and fetch pareto here.
      loading.querying = false;
      const _now = new Date();
  const _pad = (n: number) => String(n).padStart(2, '0');
  lastQueryAt.value = `${_now.getFullYear()}-${_pad(_now.getMonth() + 1)}-${_pad(_now.getDate())} ${_pad(_now.getHours())}:${_pad(_now.getMinutes())}:${_pad(_now.getSeconds())}`;
      updateUrlState();
      await fetchBatchPareto();
      refreshSuccess.value = true;
      setTimeout(() => { refreshSuccess.value = false; }, 1500);
      return;
    }

    // ---- Sync 200 path (original behavior) ----
    const result = unwrapApiResult(resp, '主查詢執行失敗');
    // TODO: type — unwrapApiResult returns untyped result from JS core module
    const resultData = ((result as Record<string, unknown>).data || result) as Record<string, unknown>;
    await _loadViewAfterQuery(resultData.query_id as string);
    await _applyQueryResult(resultData);

    refreshSuccess.value = true;
    setTimeout(() => { refreshSuccess.value = false; }, 1500);
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    refreshError.value = true;
    const e = err as Record<string, unknown>;
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢已取消';
    } else if (e?.errorCode === 'JOB_FAILED') {
      errorMessage.value = String(e?.message || '背景查詢失敗');
    } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
      errorMessage.value = '背景查詢超時，請稍後重試';
    } else {
      errorMessage.value = String(e?.message || '主查詢執行失敗');
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.querying = false;
    loading.list = false;
    jobProgress.active = false;
  }
}

// ---- View refresh (GET /view → read cache → filter) ----
async function refreshView(): Promise<void> {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  loading.list = true;
  paginationLoading.value = false;
  errorMessage.value = '';

  // ── DuckDB-WASM mode path ─────────────────────────────────────────────
  if (duckdbMode.value && duckdb.isActive.value) {
    try {
      const result = await duckdb.computeView({
        policyFilters: {
          includeExcludedScrap: committedPrimary.includeExcludedScrap,
          excludeMaterialScrap: committedPrimary.excludeMaterialScrap,
          excludePbDiode: committedPrimary.excludePbDiode,
        },
        packages: supplementaryFilters.packages,
        workcenterGroups: supplementaryFilters.workcenterGroups,
        reasons: supplementaryFilters.reasons,
        trendDates: selectedTrendDates.value,
        metricFilter: metricFilterParam(),
        metricMode: paretoMetricApiMode(),
        paretoScope: 'top80',
        paretoSelections,
        page: page.value,
        perPage: DEFAULT_PER_PAGE,
      });
      if (isStaleRequest(requestId)) return;

      analyticsRawItems.value = Array.isArray(result.analytics_raw)
        ? (result.analytics_raw as AnalyticsRawItem[])
        : analyticsRawItems.value;
      summary.value = (result.summary as SummaryData) || summary.value;
      detail.value = (result.detail as DetailState) || detail.value;

      // Update pareto data from combined result
      const dims = (result.batch_pareto?.dimensions || {}) as Record<string, ParetoDimensionState>;
      for (const dimension of PARETO_DIMENSIONS) {
        paretoData[dimension as keyof ParetoDataState] = dims[dimension] || {
          items: [],
          dimension,
          metric_mode: paretoMetricApiMode(),
        };
      }

      const af = result.available_filters;
      if (af) {
        availableFilters.value = {
          workcenterGroups: (af.workcenter_groups as string[] | undefined) || [],
          packages: (af.packages as string[] | undefined) || [],
          reasons: (af.reasons as string[] | undefined) || [],
        };
      }

      updateUrlState();
      loading.list = false;
      return;
    } catch (err) {
      if (isStaleRequest(requestId)) return;
      console.warn('[DuckDB] computeView failed, falling back to server:', err);
      duckdbMode.value = false;
      duckdb.deactivate();
      // fetchBatchPareto() returned early (saw duckdbMode=true at call time) —
      // re-trigger via server so pareto is not left stale after DuckDB fallback.
      void fetchBatchPareto();
    }
  }

  // ── Server-side path ──────────────────────────────────────────────────
  try {
    const params = buildViewParams(queryId.value, {
      supplementaryFilters,
      metricFilter: metricFilterParam(),
      trendDates: selectedTrendDates.value,
      paretoSelections,
      page: page.value,
      perPage: DEFAULT_PER_PAGE,
      policyFilters: {
        includeExcludedScrap: committedPrimary.includeExcludedScrap,
        excludeMaterialScrap: committedPrimary.excludeMaterialScrap,
        excludePbDiode: committedPrimary.excludePbDiode,
      },
    });

    const resp = await apiPost('/api/reject-history/view', params, {
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    const respAny = resp as Record<string, unknown>;
    if (respAny?.success === false && respAny?.error === 'cache_expired') {
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '視圖查詢失敗');
    const resultAny = result as Record<string, unknown>;
    const data = ((resultAny.data || result) as Record<string, unknown>);

    analyticsRawItems.value = Array.isArray(data.analytics_raw)
      ? (data.analytics_raw as AnalyticsRawItem[])
      : analyticsRawItems.value;
    summary.value = (data.summary as SummaryData) || summary.value;
    detail.value = (data.detail as DetailState) || detail.value;

    // Populate available filters (needed for async path and refreshes)
    const af = data.available_filters as Record<string, unknown> | undefined;
    if (af) {
      availableFilters.value = {
        workcenterGroups: (af.workcenter_groups as string[] | undefined) || (af.workcenterGroups as string[] | undefined) || [],
        packages: (af.packages as string[] | undefined) || [],
        reasons: (af.reasons as string[] | undefined) || [],
      };
    }

    // Activate DuckDB-WASM in background (fire-and-forget so loading.list is not blocked).
    // fetchBatchPareto() will still run from server since duckdbMode is still false here.
    const totalRowCount = (data.total_row_count as number | undefined) ?? 0;
    const spoolUrl = data.spool_download_url as string | undefined;
    if (spoolUrl && totalRowCount >= DUCKDB_THRESHOLD && isDuckDBSupported() && !duckdbMode.value) {
      duckdb.activate(spoolUrl).then(() => {
        duckdbMode.value = true;
      }).catch((err: unknown) => {
        console.warn('[DuckDB] activation failed, staying in server mode:', err);
      });
    }

    updateUrlState();
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    const e = err as Record<string, unknown>;
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = String(e?.message || '視圖查詢失敗');
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.list = false;
  }
}

async function refreshDetailPage(): Promise<void> {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  paginationLoading.value = true;
  errorMessage.value = '';

  try {
    if (duckdbMode.value && duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          policyFilters: {
            includeExcludedScrap: committedPrimary.includeExcludedScrap,
            excludeMaterialScrap: committedPrimary.excludeMaterialScrap,
            excludePbDiode: committedPrimary.excludePbDiode,
          },
          packages: supplementaryFilters.packages,
          workcenterGroups: supplementaryFilters.workcenterGroups,
          reasons: supplementaryFilters.reasons,
          trendDates: selectedTrendDates.value,
          metricFilter: metricFilterParam(),
          metricMode: paretoMetricApiMode(),
          paretoScope: 'top80',
          paretoSelections,
          page: page.value,
          perPage: DEFAULT_PER_PAGE,
          sortCol: detailSortCol.value,
          sortDir: detailSortDir.value,
        });
        if (isStaleRequest(requestId)) return;

        detail.value = (result.detail as DetailState) || detail.value;
        updateUrlState();
        return;
      } catch (err) {
        if (isStaleRequest(requestId)) return;
        console.warn('[DuckDB] computeView failed, falling back to server:', err);
        duckdbMode.value = false;
        duckdb.deactivate();
      }
    }

    const params = buildViewParams(queryId.value, {
      supplementaryFilters,
      metricFilter: metricFilterParam(),
      trendDates: selectedTrendDates.value,
      paretoSelections,
      page: page.value,
      perPage: DEFAULT_PER_PAGE,
      sortCol: detailSortCol.value,
      sortDir: detailSortDir.value,
      policyFilters: {
        includeExcludedScrap: committedPrimary.includeExcludedScrap,
        excludeMaterialScrap: committedPrimary.excludeMaterialScrap,
        excludePbDiode: committedPrimary.excludePbDiode,
      },
    });

    const resp = await apiPost('/api/reject-history/view', params, {
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    const respAny2 = resp as Record<string, unknown>;
    if (respAny2?.success === false && respAny2?.error === 'cache_expired') {
      paginationLoading.value = false;
      await executePrimaryQuery();
      return;
    }

    const result2 = unwrapApiResult(resp, '視圖查詢失敗');
    const result2Any = result2 as Record<string, unknown>;
    const data2 = (result2Any.data || result2) as Record<string, unknown>;
    detail.value = (data2.detail as DetailState) || detail.value;
    updateUrlState();
  } catch (err) {
    if (isStaleRequest(requestId)) return;
    const e = err as Record<string, unknown>;
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = String(e?.message || '視圖查詢失敗');
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    paginationLoading.value = false;
  }
}

// ---- Event handlers ----
function applyFilters(): void {
  void executePrimaryQuery();
}

function clearFilters(): void {
  queryMode.value = 'date_range';
  containerInputType.value = 'lot';
  containerInput.value = '';
  setDefaultDateRange();
  draftFilters.includeExcludedScrap = false;
  draftFilters.excludeMaterialScrap = true;
  draftFilters.excludePbDiode = true;
  resetParetoSelections();
  void executePrimaryQuery();
}

function goToPage(nextPage: number): void {
  if (
    paginationLoading.value
    || loading.list
    || nextPage < 1
    || nextPage > Number(detail.value?.pagination?.totalPages || 1)
  ) {
    return;
  }
  page.value = nextPage;
  void refreshDetailPage();
}

function onDetailSort(payload: { key: string; direction: string }): void {
  detailSortCol.value = payload.key;
  detailSortDir.value = payload.direction === 'desc' ? 'desc' : 'asc';
  page.value = 1;
  void refreshDetailPage();
}

function onTrendDateClick(dateStr: string): void {
  if (!dateStr) return;
  const idx = selectedTrendDates.value.indexOf(dateStr);
  if (idx >= 0) {
    selectedTrendDates.value = selectedTrendDates.value.filter((d: string) => d !== dateStr);
  } else {
    selectedTrendDates.value = [...selectedTrendDates.value, dateStr];
  }
  page.value = 1;
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function onTrendLegendChange(selected: Record<string, boolean>): void {
  trendLegendSelected.value = { ...selected };
  page.value = 1;
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function onParetoItemToggle(dimension: string, itemValue: string): void {
  if (!Object.prototype.hasOwnProperty.call(PARETO_SELECTION_PARAM_MAP, dimension)) {
    return;
  }
  const normalized = String(itemValue || '').trim();
  if (!normalized) return;

  const current = paretoSelections[dimension as keyof ParetoSelectionsState] || [];
  if (current.includes(normalized)) {
    paretoSelections[dimension as keyof ParetoSelectionsState] = current.filter((item: string) => item !== normalized);
  } else {
    paretoSelections[dimension as keyof ParetoSelectionsState] = [...current, normalized];
  }

  page.value = 1;
  updateUrlState();
  void Promise.all([fetchBatchPareto(), refreshView()]);
}

function clearParetoSelection(): void {
  resetParetoSelections();
  page.value = 1;
  updateUrlState();
  void Promise.all([fetchBatchPareto(), refreshView()]);
}

function onSupplementaryChange(filters: { packages?: string[]; workcenterGroups?: string[]; reasons?: string[] }): void {
  supplementaryFilters.packages = filters.packages || [];
  supplementaryFilters.workcenterGroups = filters.workcenterGroups || [];
  supplementaryFilters.reasons = filters.reasons || [];
  page.value = 1;
  selectedTrendDates.value = [];
  resetParetoSelections();
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function removeFilterChip(chip: FilterChip): void {
  if (!chip?.removable) return;

  if (chip.type === 'pareto-value') {
    onParetoItemToggle(chip.dimension ?? '', chip.value);
    return;
  }

  if (chip.type === 'trend-dates') {
    selectedTrendDates.value = [];
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
    return;
  }

  if (chip.type === 'reason') {
    supplementaryFilters.reasons = supplementaryFilters.reasons.filter((r: string) => r !== chip.value);
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
    return;
  }

  if (chip.type === 'workcenter') {
    supplementaryFilters.workcenterGroups = supplementaryFilters.workcenterGroups.filter(
      (g: string) => g !== chip.value,
    );
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
    return;
  }

  if (chip.type === 'package') {
    supplementaryFilters.packages = supplementaryFilters.packages.filter(
      (p: string) => p !== chip.value,
    );
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
  }
}

// ---- CSV export (from cache, via POST to avoid URL length limits) ----
async function exportCsv(): Promise<void> {
  if (loading.exporting || !queryId.value) return;

  loading.exporting = true;
  errorMessage.value = '';

  try {
    const body: Record<string, unknown> = {
      query_id: queryId.value,
      packages: supplementaryFilters.packages,
      workcenter_groups: supplementaryFilters.workcenterGroups,
      reasons: supplementaryFilters.reasons,
      metric_filter: metricFilterParam(),
      trend_dates: selectedTrendDates.value,
      ...Object.fromEntries(
        Object.entries(PARETO_SELECTION_PARAM_MAP)
          .filter(([dimension]) => (paretoSelections[dimension as keyof ParetoSelectionsState] || []).length > 0)
          .map(([dimension, key]) => [key, paretoSelections[dimension as keyof ParetoSelectionsState]])
      ),
    };

    if (committedPrimary.includeExcludedScrap) body.include_excluded_scrap = true;
    if (!committedPrimary.excludeMaterialScrap) body.exclude_material_scrap = false;
    if (!committedPrimary.excludePbDiode) body.exclude_pb_diode = false;

    await postExport('/api/reject-history/export-cached', body, 'reject_history_export.csv');
  } catch (err) {
    const e = err as Record<string, unknown>;
    if (e?.status === 410) {
      errorMessage.value = '快取已過期，請重新查詢後再匯出';
    } else {
      errorMessage.value = String(e?.message || '匯出 CSV 失敗');
    }
  } finally {
    loading.exporting = false;
  }
}

// ---- Computed: trend items (derived from analytics_raw) ----
const trendItems = computed<TrendItem[]>(() => {
  const raw = analyticsRawItems.value;
  if (!raw || raw.length === 0) return [];

  const byDate: Record<string, { MOVEIN_QTY: number; REJECT_TOTAL_QTY: number; DEFECT_QTY: number }> = {};
  for (const item of raw) {
    const d = item.bucket_date;
    if (!byDate[d]) {
      byDate[d] = { MOVEIN_QTY: 0, REJECT_TOTAL_QTY: 0, DEFECT_QTY: 0 };
    }
    byDate[d].MOVEIN_QTY += Number(item.MOVEIN_QTY || 0);
    byDate[d].REJECT_TOTAL_QTY += Number(item.REJECT_TOTAL_QTY || 0);
    byDate[d].DEFECT_QTY += Number(item.DEFECT_QTY || 0);
  }

  return Object.keys(byDate)
    .sort()
    .map((dateStr) => {
      const v = byDate[dateStr];
      const movein = v.MOVEIN_QTY;
      return {
        bucket_date: dateStr,
        MOVEIN_QTY: movein,
        REJECT_TOTAL_QTY: v.REJECT_TOTAL_QTY,
        DEFECT_QTY: v.DEFECT_QTY,
        REJECT_RATE_PCT: movein
          ? Number(((v.REJECT_TOTAL_QTY / movein) * 100).toFixed(4))
          : 0,
        DEFECT_RATE_PCT: movein
          ? Number(((v.DEFECT_QTY / movein) * 100).toFixed(4))
          : 0,
      };
    });
});

const totalScrapQty = computed(() => {
  return Number(summary.value.REJECT_TOTAL_QTY || 0) + Number(summary.value.DEFECT_QTY || 0);
});

const paretoMetricMode = computed(() => {
  const s = trendLegendSelected.value;
  const rejectOn = s['扣帳報廢量'] !== false;
  const defectOn = s['不扣帳報廢量'] !== false;
  if (rejectOn && defectOn) return 'all';
  if (rejectOn) return 'reject';
  if (defectOn) return 'defect';
  return 'none';
});

const paretoMetricLabel = computed(() => {
  switch (paretoMetricMode.value) {
    case 'reject':
      return '扣帳報廢量';
    case 'defect':
      return '不扣帳報廢量';
    case 'none':
      return '報廢量';
    default:
      return '全部報廢量';
  }
});

const selectedParetoCount = computed<number>(() => {
  let count = 0;
  for (const dimension of PARETO_DIMENSIONS) {
    count += (paretoSelections[dimension as keyof ParetoSelectionsState] || []).length;
  }
  return count;
});

const selectedParetoSummary = computed<string>(() => {
  const tokens: string[] = [];
  for (const dimension of PARETO_DIMENSIONS) {
    for (const value of paretoSelections[dimension as keyof ParetoSelectionsState] || []) {
      tokens.push(`${getDimensionLabel(dimension)}:${value}`);
    }
  }
  if (tokens.length <= 3) {
    return tokens.join(', ');
  }
  return `${tokens.slice(0, 3).join(', ')}... (${tokens.length} 項)`;
});

const activeFilterChips = computed<FilterChip[]>(() => {
  const chips: FilterChip[] = [];

  if (committedPrimary.mode === 'date_range') {
    chips.push({
      key: 'date-range',
      label: `日期: ${committedPrimary.startDate || '-'} ~ ${committedPrimary.endDate || '-'}`,
      removable: false,
      type: 'date',
      value: '',
    });
  } else {
    const inputLabel =
      ({ lot: 'LOT', work_order: '工單', wafer_lot: 'WAFER LOT' } as Record<string, string>)[
        committedPrimary.containerInputType
      ] || 'LOT';
    chips.push({
      key: 'container-mode',
      label: `${inputLabel}: ${committedPrimary.containerValues.length} 筆`,
      removable: false,
      type: 'container',
      value: '',
    });
  }

  chips.push({
    key: 'policy-mode',
    label: committedPrimary.includeExcludedScrap
      ? '政策: 納入不計良率報廢'
      : '政策: 排除不計良率報廢',
    removable: false,
    type: 'policy',
    value: '',
  });
  chips.push({
    key: 'material-policy-mode',
    label: committedPrimary.excludeMaterialScrap ? '原物料: 已排除' : '原物料: 已納入',
    removable: false,
    type: 'policy',
    value: '',
  });
  chips.push({
    key: 'pb-diode-policy',
    label: committedPrimary.excludePbDiode ? 'PB_* 系列: 已排除' : 'PB_* 系列: 已納入',
    removable: false,
    type: 'policy',
    value: '',
  });

  for (const reason of supplementaryFilters.reasons) {
    chips.push({
      key: `reason:${reason}`,
      label: `原因: ${reason}`,
      removable: true,
      type: 'reason',
      value: reason,
    });
  }

  supplementaryFilters.workcenterGroups.forEach((group: string) => {
    chips.push({
      key: `workcenter:${group}`,
      label: `WC: ${group}`,
      removable: true,
      type: 'workcenter',
      value: group,
    });
  });

  supplementaryFilters.packages.forEach((pkg: string) => {
    chips.push({
      key: `package:${pkg}`,
      label: `Package: ${pkg}`,
      removable: true,
      type: 'package',
      value: pkg,
    });
  });

  if (selectedTrendDates.value.length > 0) {
    const dates = selectedTrendDates.value;
    const label =
      dates.length === 1 ? `趨勢日期: ${dates[0]}` : `趨勢日期: ${dates.length} 日`;
    chips.push({
      key: 'trend-dates',
      label,
      removable: true,
      type: 'trend-dates',
      value: '',
    });
  }

  for (const dimension of PARETO_DIMENSIONS) {
    for (const value of paretoSelections[dimension as keyof ParetoSelectionsState] || []) {
      chips.push({
        key: `pareto-value:${dimension}:${value}`,
        label: `${getDimensionLabel(dimension)}: ${value}`,
        removable: true,
        type: 'pareto-value',
        dimension,
        value,
      });
    }
  }

  return chips;
});

const kpiCards = computed<KpiCard[]>(() => {
  return [
    { key: 'REJECT_TOTAL_QTY', label: '扣帳報廢量', value: summary.value.REJECT_TOTAL_QTY, lane: 'reject', isPct: false },
    { key: 'DEFECT_QTY', label: '不扣帳報廢量', value: summary.value.DEFECT_QTY, lane: 'defect', isPct: false },
    { key: 'TOTAL_SCRAP_QTY', label: '總報廢量', value: totalScrapQty.value, lane: 'neutral', isPct: false },
    { key: 'REJECT_SHARE_PCT', label: '扣帳占比', value: summary.value.REJECT_SHARE_PCT, lane: 'neutral', isPct: true },
    { key: 'AFFECTED_LOT_COUNT', label: '受影響 LOT', value: summary.value.AFFECTED_LOT_COUNT, lane: 'neutral', isPct: false },
    { key: 'AFFECTED_WORKORDER_COUNT', label: '受影響工單', value: summary.value.AFFECTED_WORKORDER_COUNT, lane: 'neutral', isPct: false },
  ];
});

const pagination = computed(
  () =>
    detail.value?.pagination || {
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      totalPages: 1,
    },
);

// ---- URL state ----
function appendArrayParams(params: URLSearchParams, key: string, values: string[]): void {
  for (const value of values || []) {
    params.append(key, value);
  }
}

function updateUrlState(): void {
  const params = new URLSearchParams();

  params.set('mode', committedPrimary.mode);
  if (committedPrimary.mode === 'date_range') {
    params.set('start_date', committedPrimary.startDate);
    params.set('end_date', committedPrimary.endDate);
  } else {
    params.set('container_input_type', committedPrimary.containerInputType);
  }

  if (committedPrimary.includeExcludedScrap) {
    params.set('include_excluded_scrap', 'true');
  }
  params.set('exclude_material_scrap', String(committedPrimary.excludeMaterialScrap));
  params.set('exclude_pb_diode', String(committedPrimary.excludePbDiode));

  appendArrayParams(params, 'packages', supplementaryFilters.packages);
  appendArrayParams(params, 'workcenter_groups', supplementaryFilters.workcenterGroups);
  appendArrayParams(params, 'reasons', supplementaryFilters.reasons);

  appendArrayParams(params, 'trend_dates', selectedTrendDates.value);
  for (const [dimension, key] of Object.entries(PARETO_SELECTION_PARAM_MAP)) {
    appendArrayParams(params, key, paretoSelections[dimension as keyof ParetoSelectionsState] || []);
  }

  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/reject-history?${params.toString()}`);
}

// ---- URL restore ----
function readArrayParam(params: URLSearchParams, key: string): string[] {
  const repeated = params
    .getAll(key)
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  if (repeated.length > 0) {
    return repeated;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function readBooleanParam(params: URLSearchParams, key: string, defaultValue = false): boolean {
  const value = String(params.get(key) || '').trim().toLowerCase();
  if (!value) {
    return defaultValue;
  }
  return ['1', 'true', 'yes', 'y', 'on'].includes(value);
}

function restoreFromUrl(): void {
  const params = new URLSearchParams(window.location.search);

  const mode = String(params.get('mode') || '').trim();
  if (mode === 'container') {
    queryMode.value = 'container';
    containerInputType.value = String(
      params.get('container_input_type') || 'lot',
    ).trim();
  } else {
    queryMode.value = 'date_range';
    const startDate = String(params.get('start_date') || '').trim();
    const endDate = String(params.get('end_date') || '').trim();
    if (startDate && endDate) {
      draftFilters.startDate = startDate;
      draftFilters.endDate = endDate;
    }
  }

  draftFilters.includeExcludedScrap = readBooleanParam(
    params,
    'include_excluded_scrap',
    false,
  );
  draftFilters.excludeMaterialScrap = readBooleanParam(
    params,
    'exclude_material_scrap',
    true,
  );
  draftFilters.excludePbDiode = readBooleanParam(params, 'exclude_pb_diode', true);

  supplementaryFilters.packages = readArrayParam(params, 'packages');
  supplementaryFilters.workcenterGroups = readArrayParam(params, 'workcenter_groups');
  supplementaryFilters.reasons = readArrayParam(params, 'reasons');

  selectedTrendDates.value = readArrayParam(params, 'trend_dates');

  const restoredSelections = createEmptyParetoSelections();
  for (const [dimension, key] of Object.entries(PARETO_SELECTION_PARAM_MAP)) {
    restoredSelections[dimension as keyof ParetoSelectionsState] = readArrayParam(params, key);
  }

  const legacyDimension = String(params.get('pareto_dimension') || '').trim().toLowerCase();
  const legacyValues = readArrayParam(params, 'pareto_values');
  const hasSelParams = Object.values(restoredSelections).some((values) => values.length > 0);
  if (!hasSelParams && legacyValues.length > 0) {
    const fallbackDimension = Object.prototype.hasOwnProperty.call(PARETO_SELECTION_PARAM_MAP, legacyDimension)
      ? legacyDimension
      : 'reason';
    restoredSelections[fallbackDimension as keyof ParetoSelectionsState] = legacyValues;
  }

  for (const dimension of PARETO_DIMENSIONS) {
    paretoSelections[dimension as keyof ParetoSelectionsState] = restoredSelections[dimension as keyof ParetoSelectionsState];
  }

  const parsedPage = Number(params.get('page') || '1');
  page.value = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
}

onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
});

onUnmounted(() => {
  _jobAbortController?.abort();
  duckdb.deactivate();
});
</script>

<template>
  <div class="dashboard reject-history-page theme-reject-history">

    <ErrorBanner :message="errorMessage" :dismissible="false" />
    <div v-if="partialFailureWarning" class="warning-banner">
      {{ partialFailureWarning }}
    </div>

    <FilterPanel
      :filters="draftFilters"
      :query-mode="queryMode"
      :container-input-type="containerInputType"
      :container-input="containerInput"
      :available-filters="availableFilters"
      :supplementary-filters="supplementaryFilters"
      :query-id="queryId"
      :resolution-info="resolutionInfo"
      :loading="loading"
      :active-filter-chips="activeFilterChips"
      :primary-query-max-days="PRIMARY_QUERY_MAX_DAYS"
      @apply="applyFilters"
      @clear="clearFilters"
      @export-csv="exportCsv"
      @remove-chip="removeFilterChip"
      @update:query-mode="queryMode = $event"
      @update:container-input-type="containerInputType = $event"
      @update:container-input="containerInput = $event"
      @supplementary-change="onSupplementaryChange"
    />

    <!-- Async job inline status bar (non-blocking, shows progress text + cancel) -->
    <div v-if="jobProgress.active" class="async-job-status-bar">
      <LoadingSpinner size="sm" />
      <span class="async-job-status-text">
        {{ jobProgress.progress || '背景查詢中...' }}
        <template v-if="jobProgress.pct > 0">（{{ jobProgress.pct }}%）</template>
        <template v-if="jobProgress.elapsedSeconds > 0"> · 已等待 {{ jobProgress.elapsedSeconds }} 秒</template>
      </span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" @click="cancelAsyncJob">取消查詢</button>
    </div>

    <template v-if="queryId">
      <SummaryCards :cards="kpiCards" />

      <TrendChart
        :items="trendItems"
        :selected-dates="selectedTrendDates"
        :loading="loading.querying"
        @date-click="onTrendDateClick"
        @legend-change="onTrendLegendChange"
      />

      <ParetoGrid
        :pareto-data="paretoData"
        :pareto-selections="paretoSelections"
        :display-scope="PARETO_DISPLAY_SCOPE_FIXED"
        :selected-dates="selectedTrendDates"
        :metric-label="paretoMetricLabel"
        :loading="loading.querying || loading.pareto"
        @item-toggle="onParetoItemToggle"
      />

      <DetailTable
        :items="detail.items"
        :pagination="pagination"
        :loading="loading.list"
        :paginating="paginationLoading"
        :selected-pareto-count="selectedParetoCount"
        :selected-pareto-summary="selectedParetoSummary"
        @go-to-page="goToPage"
        @clear-pareto-selection="clearParetoSelection"
        @sort="onDetailSort"
      />
    </template>
    <LoadingOverlay v-if="loading.querying && !jobProgress.active" tier="page" />
  </div>
</template>
