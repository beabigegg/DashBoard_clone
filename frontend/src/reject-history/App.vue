<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import {
  buildViewParams,
  parseMultiLineInput,
  PRIMARY_QUERY_MAX_DAYS,
  validateDateRange,
} from '../core/reject-history-filters.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling.js';

import DetailTable from './components/DetailTable.vue';
import FilterPanel from './components/FilterPanel.vue';
import ParetoGrid from './components/ParetoGrid.vue';
import SummaryCards from './components/SummaryCards.vue';
import TrendChart from './components/TrendChart.vue';

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 50;
const PARETO_DIMENSIONS = ['reason', 'package', 'type'];
const PARETO_DISPLAY_SCOPE_FIXED = 'top20';
const PARETO_SELECTION_PARAM_MAP = {
  reason: 'sel_reason',
  package: 'sel_package',
  type: 'sel_type',
};

function createEmptyParetoSelections() {
  return {
    reason: [],
    package: [],
    type: [],
  };
}

function createEmptyParetoData() {
  return {
    reason: { items: [], dimension: 'reason', metric_mode: 'reject_total' },
    package: { items: [], dimension: 'package', metric_mode: 'reject_total' },
    type: { items: [], dimension: 'type', metric_mode: 'reject_total' },
  };
}

function getDimensionLabel(dimension) {
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
const queryMode = ref('date_range');
const containerInputType = ref('lot');
const containerInput = ref('');

const draftFilters = reactive({
  startDate: '',
  endDate: '',
  includeExcludedScrap: false,
  excludeMaterialScrap: true,
  excludePbDiode: true,
});

// ---- Committed primary params (for URL + chips) ----
const committedPrimary = reactive({
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
const queryId = ref('');
const resolutionInfo = ref(null);
const availableFilters = ref({ workcenterGroups: [], packages: [], reasons: [] });

// ---- Supplementary filters (post-query, applied via /view) ----
const supplementaryFilters = reactive({
  packages: [],
  workcenterGroups: [],
  reasons: [],
});

// ---- Interactive state ----
const page = ref(1);
const selectedTrendDates = ref([]);
const trendLegendSelected = ref({ '扣帳報廢量': true, '不扣帳報廢量': true });
const paretoSelections = reactive(createEmptyParetoSelections());
const paretoData = reactive(createEmptyParetoData());

// ---- Data state ----
const summary = ref({
  MOVEIN_QTY: 0,
  REJECT_TOTAL_QTY: 0,
  DEFECT_QTY: 0,
  REJECT_RATE_PCT: 0,
  DEFECT_RATE_PCT: 0,
  REJECT_SHARE_PCT: 0,
  AFFECTED_LOT_COUNT: 0,
  AFFECTED_WORKORDER_COUNT: 0,
});
const analyticsRawItems = ref([]);
const detail = ref({
  items: [],
  pagination: {
    page: 1,
    perPage: DEFAULT_PER_PAGE,
    total: 0,
    totalPages: 1,
  },
});

// ---- Loading / error state ----
const loading = reactive({
  initial: false,
  querying: false,
  list: false,
  pareto: false,
  exporting: false,
});
const errorMessage = ref('');
const partialFailureWarning = ref('');
const lastQueryAt = ref('');

// ---- Async job progress state ----
const jobProgress = reactive({
  active: false,
  jobId: null,
  status: null,
  progress: '',
  pct: 0,
  elapsedSeconds: 0,
});
let _jobAbortController = null;

// ---- Request staleness tracking ----
let activeRequestId = 0;
let activeParetoRequestId = 0;

function nextRequestId() {
  activeRequestId += 1;
  return activeRequestId;
}

function isStaleRequest(id) {
  return id !== activeRequestId;
}

function nextParetoRequestId() {
  activeParetoRequestId += 1;
  return activeParetoRequestId;
}

function isStaleParetoRequest(id) {
  return id !== activeParetoRequestId;
}

// ---- Helpers ----
function toDateString(value) {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function setDefaultDateRange() {
  const today = new Date();
  const end = new Date(today);
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  draftFilters.startDate = toDateString(start);
  draftFilters.endDate = toDateString(end);
}

function metricFilterParam() {
  const mode = paretoMetricMode.value;
  if (mode === 'reject' || mode === 'defect') return mode;
  return 'all';
}

function paretoMetricApiMode() {
  return paretoMetricMode.value === 'defect' ? 'defect' : 'reject_total';
}

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success === true) {
    return result;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  return result;
}

function resetParetoSelections() {
  for (const dimension of PARETO_DIMENSIONS) {
    paretoSelections[dimension] = [];
  }
}

function resetParetoData() {
  for (const dimension of PARETO_DIMENSIONS) {
    paretoData[dimension] = {
      items: [],
      dimension,
      metric_mode: paretoMetricApiMode(),
    };
  }
}

function buildBatchParetoParams() {
  const params = {
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
    if (paretoSelections[dimension]?.length > 0) {
      params[key] = paretoSelections[dimension];
    }
  }
  return params;
}

async function fetchBatchPareto() {
  if (!queryId.value) return;

  const requestId = nextParetoRequestId();
  loading.pareto = true;

  try {
    const resp = await apiGet('/api/reject-history/batch-pareto', {
      params: buildBatchParetoParams(),
      timeout: API_TIMEOUT,
    });
    if (isStaleParetoRequest(requestId)) return;

    if (resp?.success === false && resp?.error === 'cache_miss') {
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '查詢批次 Pareto 失敗');
    const dimensions = result.data?.dimensions || {};
    for (const dimension of PARETO_DIMENSIONS) {
      paretoData[dimension] = dimensions[dimension] || {
        items: [],
        dimension,
        metric_mode: paretoMetricApiMode(),
      };
    }
  } catch (error) {
    if (isStaleParetoRequest(requestId)) return;
    resetParetoData();
    if (error?.name !== 'AbortError') {
      errorMessage.value = error?.message || '查詢批次 Pareto 失敗';
    }
  } finally {
    if (!isStaleParetoRequest(requestId)) {
      loading.pareto = false;
    }
  }
}

// ---- Primary query (POST /query → Oracle → cache) ----
function cancelAsyncJob() {
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  jobProgress.active = false;
}

async function _loadViewAfterQuery(queryIdValue) {
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

async function _applyQueryResult(result) {
  const meta = result.meta || {};
  if (meta.has_partial_failure) {
    const failedChunkCount = Number(meta.failed_chunk_count || 0);
    const failedRanges = Array.isArray(meta.failed_ranges) ? meta.failed_ranges : [];
    if (failedRanges.length > 0) {
      const rangesText = failedRanges
        .map((item) => `${item.start} ~ ${item.end}`)
        .join('、');
      partialFailureWarning.value = `警告：以下日期區間的資料擷取失敗（${failedChunkCount} 個批次）：${rangesText}。目前顯示結果可能不完整。`;
    } else {
      partialFailureWarning.value = `警告：${failedChunkCount} 個查詢批次的資料擷取失敗。目前顯示結果可能不完整。`;
    }
  }

  resolutionInfo.value = result.resolution_info || null;
  const af = result.available_filters || {};
  availableFilters.value = {
    workcenterGroups: af.workcenter_groups || af.workcenterGroups || [],
    packages: af.packages || [],
    reasons: af.reasons || [],
  };

  supplementaryFilters.packages = [];
  supplementaryFilters.workcenterGroups = [];
  supplementaryFilters.reasons = [];
  page.value = 1;
  selectedTrendDates.value = [];
  resetParetoSelections();
  resetParetoData();

  analyticsRawItems.value = Array.isArray(result.analytics_raw)
    ? result.analytics_raw
    : [];
  summary.value = result.summary || summary.value;
  detail.value = result.detail || detail.value;

  await fetchBatchPareto();

  lastQueryAt.value = new Date().toLocaleString('zh-TW');
  updateUrlState();
}

async function executePrimaryQuery() {
  const requestId = nextRequestId();
  loading.querying = true;
  loading.list = true;
  errorMessage.value = '';
  partialFailureWarning.value = '';
  cancelAsyncJob();

  try {
    const body = { mode: queryMode.value };

    if (queryMode.value === 'date_range') {
      const dateValidationError = validateDateRange(
        draftFilters.startDate,
        draftFilters.endDate,
      );
      if (dateValidationError) {
        errorMessage.value = dateValidationError;
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
    const respData = resp?.data || {};
    if (resp?._status === 202 || (respData.async === true && respData.job_id)) {
      const jobId = respData.job_id;
      const statusUrl = respData.status_url || `/api/reject-history/job/${jobId}`;
      const preQueryId = respData.query_id;

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
          onProgress: (statusResp) => {
            if (isStaleRequest(requestId)) return;
            jobProgress.status = statusResp.status;
            jobProgress.progress = statusResp.progress || '';
            jobProgress.pct = statusResp.pct || 0;
            jobProgress.elapsedSeconds = statusResp.elapsed_seconds || 0;
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
      lastQueryAt.value = new Date().toLocaleString('zh-TW');
      updateUrlState();
      await fetchBatchPareto();
      return;
    }

    // ---- Sync 200 path (original behavior) ----
    const result = unwrapApiResult(resp, '主查詢執行失敗');
    const resultData = result.data || result;
    await _loadViewAfterQuery(resultData.query_id);
    await _applyQueryResult(resultData);

  } catch (error) {
    if (isStaleRequest(requestId)) return;
    if (error?.name === 'AbortError') {
      errorMessage.value = '查詢已取消';
    } else if (error?.errorCode === 'JOB_FAILED') {
      errorMessage.value = error?.message || '背景查詢失敗';
    } else if (error?.errorCode === 'JOB_POLL_TIMEOUT') {
      errorMessage.value = '背景查詢超時，請稍後重試';
    } else {
      errorMessage.value = error?.message || '主查詢執行失敗';
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.querying = false;
    loading.list = false;
    jobProgress.active = false;
  }
}

// ---- View refresh (GET /view → read cache → filter) ----
async function refreshView() {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  loading.list = true;
  errorMessage.value = '';

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

    const resp = await apiGet('/api/reject-history/view', {
      params,
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    if (resp?.success === false && resp?.error === 'cache_expired') {
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '視圖查詢失敗');
    const data = result.data || result;

    analyticsRawItems.value = Array.isArray(data.analytics_raw)
      ? data.analytics_raw
      : analyticsRawItems.value;
    summary.value = data.summary || summary.value;
    detail.value = data.detail || detail.value;

    // Populate available filters (needed for async path and refreshes)
    const af = data.available_filters;
    if (af) {
      availableFilters.value = {
        workcenterGroups: af.workcenter_groups || af.workcenterGroups || [],
        packages: af.packages || [],
        reasons: af.reasons || [],
      };
    }

    updateUrlState();
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    if (error?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = error?.message || '視圖查詢失敗';
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.list = false;
  }
}

// ---- Event handlers ----
function applyFilters() {
  void executePrimaryQuery();
}

function clearFilters() {
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

function goToPage(nextPage) {
  if (nextPage < 1 || nextPage > Number(detail.value?.pagination?.totalPages || 1)) {
    return;
  }
  page.value = nextPage;
  void refreshView();
}

function onTrendDateClick(dateStr) {
  if (!dateStr) return;
  const idx = selectedTrendDates.value.indexOf(dateStr);
  if (idx >= 0) {
    selectedTrendDates.value = selectedTrendDates.value.filter((d) => d !== dateStr);
  } else {
    selectedTrendDates.value = [...selectedTrendDates.value, dateStr];
  }
  page.value = 1;
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function onTrendLegendChange(selected) {
  trendLegendSelected.value = { ...selected };
  page.value = 1;
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function onParetoItemToggle(dimension, itemValue) {
  if (!Object.hasOwn(PARETO_SELECTION_PARAM_MAP, dimension)) {
    return;
  }
  const normalized = String(itemValue || '').trim();
  if (!normalized) return;

  const current = paretoSelections[dimension] || [];
  if (current.includes(normalized)) {
    paretoSelections[dimension] = current.filter((item) => item !== normalized);
  } else {
    paretoSelections[dimension] = [...current, normalized];
  }

  page.value = 1;
  updateUrlState();
  void Promise.all([fetchBatchPareto(), refreshView()]);
}

function clearParetoSelection() {
  resetParetoSelections();
  page.value = 1;
  updateUrlState();
  void Promise.all([fetchBatchPareto(), refreshView()]);
}

function onSupplementaryChange(filters) {
  supplementaryFilters.packages = filters.packages || [];
  supplementaryFilters.workcenterGroups = filters.workcenterGroups || [];
  supplementaryFilters.reasons = filters.reasons || [];
  page.value = 1;
  selectedTrendDates.value = [];
  resetParetoSelections();
  updateUrlState();
  void Promise.all([refreshView(), fetchBatchPareto()]);
}

function removeFilterChip(chip) {
  if (!chip?.removable) return;

  if (chip.type === 'pareto-value') {
    onParetoItemToggle(chip.dimension, chip.value);
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
    supplementaryFilters.reasons = supplementaryFilters.reasons.filter((r) => r !== chip.value);
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
    return;
  }

  if (chip.type === 'workcenter') {
    supplementaryFilters.workcenterGroups = supplementaryFilters.workcenterGroups.filter(
      (g) => g !== chip.value,
    );
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
    return;
  }

  if (chip.type === 'package') {
    supplementaryFilters.packages = supplementaryFilters.packages.filter(
      (p) => p !== chip.value,
    );
    page.value = 1;
    updateUrlState();
    void Promise.all([refreshView(), fetchBatchPareto()]);
  }
}

// ---- CSV export (from cache) ----
async function exportCsv() {
  if (loading.exporting || !queryId.value) return;

  loading.exporting = true;
  errorMessage.value = '';

  try {
    const params = new URLSearchParams();
    params.set('query_id', queryId.value);
    for (const pkg of supplementaryFilters.packages) params.append('packages', pkg);
    for (const wc of supplementaryFilters.workcenterGroups) params.append('workcenter_groups', wc);
    for (const r of supplementaryFilters.reasons) params.append('reasons', r);
    params.set('metric_filter', metricFilterParam());
    for (const date of selectedTrendDates.value) params.append('trend_dates', date);
    for (const [dimension, key] of Object.entries(PARETO_SELECTION_PARAM_MAP)) {
      for (const value of paretoSelections[dimension] || []) {
        params.append(key, value);
      }
    }

    if (committedPrimary.includeExcludedScrap) params.set('include_excluded_scrap', 'true');
    if (!committedPrimary.excludeMaterialScrap) params.set('exclude_material_scrap', 'false');
    if (!committedPrimary.excludePbDiode) params.set('exclude_pb_diode', 'false');

    const response = await fetch(`/api/reject-history/export-cached?${params.toString()}`);

    if (response.status === 410) {
      errorMessage.value = '快取已過期，請重新查詢後再匯出';
      return;
    }
    if (!response.ok) {
      throw new Error('匯出 CSV 失敗');
    }

    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename=(.+?)(?:;|$)/);
    const filename = filenameMatch ? filenameMatch[1] : 'reject_history_export.csv';

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    errorMessage.value = error?.message || '匯出 CSV 失敗';
  } finally {
    loading.exporting = false;
  }
}

// ---- Computed: trend items (derived from analytics_raw) ----
const trendItems = computed(() => {
  const raw = analyticsRawItems.value;
  if (!raw || raw.length === 0) return [];

  const byDate = {};
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

const selectedParetoCount = computed(() => {
  let count = 0;
  for (const dimension of PARETO_DIMENSIONS) {
    count += (paretoSelections[dimension] || []).length;
  }
  return count;
});

const selectedParetoSummary = computed(() => {
  const tokens = [];
  for (const dimension of PARETO_DIMENSIONS) {
    for (const value of paretoSelections[dimension] || []) {
      tokens.push(`${getDimensionLabel(dimension)}:${value}`);
    }
  }
  if (tokens.length <= 3) {
    return tokens.join(', ');
  }
  return `${tokens.slice(0, 3).join(', ')}... (${tokens.length} 項)`;
});

const activeFilterChips = computed(() => {
  const chips = [];

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
      { lot: 'LOT', work_order: '工單', wafer_lot: 'WAFER LOT' }[
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

  supplementaryFilters.workcenterGroups.forEach((group) => {
    chips.push({
      key: `workcenter:${group}`,
      label: `WC: ${group}`,
      removable: true,
      type: 'workcenter',
      value: group,
    });
  });

  supplementaryFilters.packages.forEach((pkg) => {
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
    for (const value of paretoSelections[dimension] || []) {
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

const kpiCards = computed(() => {
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
function appendArrayParams(params, key, values) {
  for (const value of values || []) {
    params.append(key, value);
  }
}

function updateUrlState() {
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
    appendArrayParams(params, key, paretoSelections[dimension] || []);
  }

  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/reject-history?${params.toString()}`);
}

// ---- URL restore ----
function readArrayParam(params, key) {
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

function readBooleanParam(params, key, defaultValue = false) {
  const value = String(params.get(key) || '').trim().toLowerCase();
  if (!value) {
    return defaultValue;
  }
  return ['1', 'true', 'yes', 'y', 'on'].includes(value);
}

function restoreFromUrl() {
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
    restoredSelections[dimension] = readArrayParam(params, key);
  }

  const legacyDimension = String(params.get('pareto_dimension') || '').trim().toLowerCase();
  const legacyValues = readArrayParam(params, 'pareto_values');
  const hasSelParams = Object.values(restoredSelections).some((values) => values.length > 0);
  if (!hasSelParams && legacyValues.length > 0) {
    const fallbackDimension = Object.hasOwn(PARETO_SELECTION_PARAM_MAP, legacyDimension)
      ? legacyDimension
      : 'reason';
    restoredSelections[fallbackDimension] = legacyValues;
  }

  for (const dimension of PARETO_DIMENSIONS) {
    paretoSelections[dimension] = restoredSelections[dimension];
  }

  const parsedPage = Number(params.get('page') || '1');
  page.value = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
}

onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
});
</script>

<template>
  <div class="dashboard reject-history-page theme-reject-history">
    <header class="header reject-history-header">
      <div class="header-left">
        <h1>報廢歷史查詢</h1>
      </div>
      <div class="header-right">
        <div class="last-update" v-if="lastQueryAt">更新時間：{{ lastQueryAt }}</div>
        <button
          type="button"
          class="btn btn-light"
          :disabled="loading.querying"
          @click="applyFilters"
        >
          重新整理
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>
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
      <span class="btn-spinner"></span>
      <span class="async-job-status-text">
        {{ jobProgress.progress || '背景查詢中...' }}
        <template v-if="jobProgress.pct > 0">（{{ jobProgress.pct }}%）</template>
        <template v-if="jobProgress.elapsedSeconds > 0"> · 已等待 {{ jobProgress.elapsedSeconds }} 秒</template>
      </span>
      <button type="button" class="btn btn-light" @click="cancelAsyncJob">取消查詢</button>
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
        :selected-pareto-count="selectedParetoCount"
        :selected-pareto-summary="selectedParetoSummary"
        @go-to-page="goToPage"
        @clear-pareto-selection="clearParetoSelection"
      />
    </template>
  </div>
</template>
