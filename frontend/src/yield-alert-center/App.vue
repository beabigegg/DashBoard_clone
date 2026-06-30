<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';

import { ArrowDown, ArrowUp, ArrowUpDown, Download } from 'lucide-vue-next';

import { apiGet, apiPost } from '../core/api';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';
import { useYieldAlertDuckDB } from './useYieldAlertDuckDB';
import { isDuckDBSupported } from '../core/duckdb-client';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import { replaceRuntimeHistory } from '../core/shell-navigation';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { toQueryParams } from './utils';

import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import YieldHeatmap from './YieldHeatmap.vue';
import YieldStationChart from './YieldStationChart.vue';
import YieldPackageChart from './YieldPackageChart.vue';
import YieldTrendChart from './YieldTrendChart.vue';

const API_TIMEOUT = 180000;
const DEFAULT_PER_PAGE = 20;
const DEFAULT_WORKCENTER_GROUP_OPTIONS = [
  '焊接_DB',
  '焊接_WB',
  '成型',
  '去膠',
  '水吹砂',
  '電鍍',
  '移印',
  '切彎腳',
  'TMTT',
  '品檢',
  'FQC',
];

const loading = ref(false);
const trendLoading = ref(false);
const summaryLoading = ref(false);
const alertLoading = ref(false);
const paginationLoading = ref(false);
const isExporting = ref(false);

const errorMessage = ref('');
const warningMessage = ref('');

const expandedRowKey = ref('');
const reasonDetailRows = ref([]);
const reasonDetailLoading = ref(false);

const queryId = ref('');
const hasQueried = ref(false);
const committedDateRange = reactive({
  start_date: '',
  end_date: '',
});

const jobProgress = reactive<{
  active: boolean;
  jobId: string | null;
  status: string;
  progress: string;
  pct: number;
}>({
  active: false,
  jobId: null,
  status: '',
  progress: '',
  pct: 0,
});

let _jobAbortController: AbortController | null = null;

const granularity = ref('day');
const GRANULARITY_OPTIONS = [
  { value: 'day', label: '日' },
  { value: 'week', label: '週' },
  { value: 'month', label: '月' },
  { value: 'year', label: '年' },
];

// ── Process type selector (primary query level) ───────────────────────────────
const selectedProcessType = ref('GA%');
const PROCESS_TYPE_OPTIONS = [
  { value: 'GA%', label: '封裝 (GA%)' },
  { value: 'GC%', label: '點測 (GC%)' },
];

const summary = ref({ transaction_qty: 0, scrap_qty: 0, yield_pct: 100 });
const trend = ref([]);
const heatmapData = ref([]);
const stationSummary = ref([]);
const packageSummary = ref([]);
const alerts = ref([]);
const pagination = ref({ page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 1 });
const sortState = reactive({ sort_by: 'date_bucket', sort_dir: 'desc' });
const workcenterGroupOptions = ref([...DEFAULT_WORKCENTER_GROUP_OPTIONS]);
const lineOptions = ref([]);
const packageOptions = ref([]);
const typeOptions = ref([]);
const functionOptions = ref([]);
const filters = reactive({
  start_date: '',
  end_date: '',
  workcenterGroups: [],
  lines: [],
  packages: [],
  types: [],
  functions: [],
  risk_threshold: '98',
  min_scrap_qty: '1',
});


// ── DuckDB-WASM mode (Task 7.2) ───────────────────────────────────────────
const DUCKDB_THRESHOLD = 5000;
const duckdb = useYieldAlertDuckDB();
const duckdbMode = ref(false);   // true when frontend DuckDB-WASM is active
const duckdbActivating = ref(false);

// -- useFilterOrchestrator: two-phase primary query, supplementary/sort -> page=1 --
const filterOrchestrator = useFilterOrchestrator({
  fields: {
    start_date:       { trigger: 'draft-apply', initial: '' },
    end_date:         { trigger: 'draft-apply', initial: '' },
    workcenterGroups: { trigger: 'immediate', initial: [] },
    lines:            { trigger: 'immediate', initial: [] },
    packages:         { trigger: 'immediate', initial: [] },
    types:            { trigger: 'immediate', initial: [] },
    functions:        { trigger: 'immediate', initial: [] },
    risk_threshold:   { trigger: 'immediate', initial: '98' },
    min_scrap_qty:    { trigger: 'immediate', initial: '1' },
    granularity:      { trigger: 'immediate', initial: 'day' },
    sort_by:          { trigger: 'immediate', initial: 'date_bucket' },
    sort_dir:         { trigger: 'immediate', initial: 'desc' },
  },
  pagination: { resetOn: ['*'] },
  onPrimaryQuery(_committed) {
    // Date stage changed -> full primary query
    void runQuery(1);
  },
  onViewRefresh(_committed) {
    // Supplementary/sort change -> page=1, re-query from cache
    void runQuery(1);
  },
});

const parsedFilters = computed(() => ({
  start_date: filters.start_date,
  end_date: filters.end_date,
  workcenter_groups: filters.workcenterGroups,
  lines: filters.lines,
  packages: filters.packages,
  types: filters.types,
  functions: filters.functions,
  risk_threshold: filters.risk_threshold,
  min_scrap_qty: filters.min_scrap_qty,
}));

const canSubmit = computed(() => !loading.value && !paginationLoading.value && Boolean(filters.start_date && filters.end_date));
const canApplySupplementary = computed(
  () => !loading.value && !paginationLoading.value && Boolean(queryId.value) && canSubmit.value,
);
const isDateStageDirty = computed(() => (
  !queryId.value
  || filters.start_date !== committedDateRange.start_date
  || filters.end_date !== committedDateRange.end_date
));
const submitLabel = computed(() => (isDateStageDirty.value ? '查詢(日期)' : '套用篩選'));
const hasData = computed(() => alerts.value.length > 0);
const alertEmptyMessage = computed(() => {
  if (!hasQueried.value) return '請先設定日期並查詢';
  if (alertLoading.value || paginationLoading.value) return '告警資料載入中...';
  return '目前無符合條件的告警候選';
});

const summaryCards = computed(() => [
  {
    key: 'transaction',
    label: '移轉量',
    value: Number(summary.value.transaction_qty || 0),
    accent: 'brand',
    format: 'number',
  },
  {
    key: 'scrap',
    label: '報廢量',
    value: Number(summary.value.scrap_qty || 0),
    accent: 'warning',
    format: 'number',
  },
  {
    key: 'yield',
    label: '良率',
    value: Number(summary.value.yield_pct || 0),
    accent: Number(summary.value.yield_pct || 0) < Number(filters.risk_threshold || 98) ? 'danger' : 'success',
    format: 'percent',
  },
]);

function alertRowKey(row) {
  const lotPart = row.source_code != null ? `|${row.source_code}` : '';
  return `${row.date_bucket}|${row.workorder}|${row.reason_code}|${row.department}${lotPart}`;
}



function setDefaultDateRange() {
  const end = new Date();
  const start = new Date(Date.now() - 29 * 24 * 60 * 60 * 1000);
  filters.start_date = start.toISOString().slice(0, 10);
  filters.end_date = end.toISOString().slice(0, 10);
}

function syncUrlState() {
  const params = toQueryParams({
    query_id: queryId.value,
    start_date: parsedFilters.value.start_date,
    end_date: parsedFilters.value.end_date,
    workcenter_groups: parsedFilters.value.workcenter_groups,
    lines: parsedFilters.value.lines,
    packages: parsedFilters.value.packages,
    types: parsedFilters.value.types,
    functions: parsedFilters.value.functions,
    risk_threshold: parsedFilters.value.risk_threshold,
    min_scrap_qty: parsedFilters.value.min_scrap_qty,
    granularity: granularity.value,
    page: pagination.value.page,
    per_page: pagination.value.per_page,
    sort_by: sortState.sort_by,
    sort_dir: sortState.sort_dir,
  });
  replaceRuntimeHistory(`/yield-alert-center?${params.toString()}`);
}

function readArrayParam(params, key) {
  const values = params.getAll(key).map((item) => String(item || '').trim()).filter(Boolean);
  if (values.length > 0) {
    return values;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function restoreFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const restoredQueryId = String(params.get('query_id') || '').trim();
  if (restoredQueryId) {
    queryId.value = restoredQueryId;
  }
  const startDate = String(params.get('start_date') || '').trim();
  const endDate = String(params.get('end_date') || '').trim();
  if (startDate) filters.start_date = startDate;
  if (endDate) filters.end_date = endDate;
  if (queryId.value && filters.start_date && filters.end_date) {
    committedDateRange.start_date = filters.start_date;
    committedDateRange.end_date = filters.end_date;
  }

  const groupsFromUrl = readArrayParam(params, 'workcenter_groups');
  const groupsFromLegacy = readArrayParam(params, 'departments');
  filters.workcenterGroups = groupsFromUrl.length > 0 ? groupsFromUrl : groupsFromLegacy;
  filters.lines = readArrayParam(params, 'lines');
  filters.packages = readArrayParam(params, 'packages');
  filters.types = readArrayParam(params, 'types');
  filters.functions = readArrayParam(params, 'functions');

  const riskThreshold = String(params.get('risk_threshold') || '').trim();
  const minScrapQty = String(params.get('min_scrap_qty') || '').trim();
  if (riskThreshold) filters.risk_threshold = riskThreshold;
  if (minScrapQty) filters.min_scrap_qty = minScrapQty;

  const page = Number(params.get('page') || '1');
  if (Number.isFinite(page) && page > 0) {
    pagination.value.page = page;
  }
  const perPage = Number(params.get('per_page') || String(DEFAULT_PER_PAGE));
  if (Number.isFinite(perPage) && perPage > 0) {
    pagination.value.per_page = perPage;
  }

  const sortBy = String(params.get('sort_by') || '').trim();
  const sortDir = String(params.get('sort_dir') || '').trim().toLowerCase();
  if (sortBy) sortState.sort_by = sortBy;
  if (sortDir === 'asc' || sortDir === 'desc') sortState.sort_dir = sortDir;

  const gran = String(params.get('granularity') || '').trim().toLowerCase();
  if (['day', 'week', 'month', 'year'].includes(gran)) granularity.value = gran;
}

async function loadFilterOptions() {
  try {
    const resp = await apiGet('/api/yield-alert/filter-options', { timeout: 30000 });
    if (!resp.success) {
      return;
    }
    const options = Array.isArray(resp.data?.workcenter_groups)
      ? resp.data.workcenter_groups.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    if (options.length > 0) {
      workcenterGroupOptions.value = options;
    }
  } catch (_error) {
    // Keep local fallback options when backend options are unavailable.
  }
}

function isCacheExpiredError(error) {
  if (Number(error?.status || 0) === 410) return true;
  const errorCode = String(error?.errorCode || error?.payload?.error?.code || error?.payload?.code || '').toUpperCase();
  if (errorCode === 'CACHE_EXPIRED') return true;
  const payloadError = String(error?.payload?.error || '').trim().toLowerCase();
  if (payloadError === 'cache_expired') return true;
  return false;
}

async function executePrimaryQuery() {
  // New primary query means new spool — stale DuckDB data must be discarded.
  duckdbMode.value = false;
  duckdbActivating.value = false;
  duckdb.deactivate();

  // Cancel any in-progress polling
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }

  const resp = await apiPost('/api/yield-alert/query', {
    start_date: filters.start_date,
    end_date: filters.end_date,
    process_type: selectedProcessType.value,
  }, {
    timeout: API_TIMEOUT,
  });

  const respData = resp?.data || {};

  // ---- Async 202 path ----
  if (resp?._status === 202 || (respData.async === true && respData.job_id)) {
    const jobId = respData.job_id;
    const statusUrl = respData.status_url || `/api/yield-alert/job/${jobId}`;
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
          jobProgress.status = statusResp.status;
          jobProgress.progress = statusResp.progress || '';
          jobProgress.pct = statusResp.pct || 0;
        },
      });
    } finally {
      if (_jobAbortController === controller) _jobAbortController = null;
      jobProgress.active = false;
    }

    // Use the pre-computed query_id from the 202 response
    if (preQueryId) {
      queryId.value = String(preQueryId);
    }
    committedDateRange.start_date = filters.start_date;
    committedDateRange.end_date = filters.end_date;
    return;
  }

  // ---- Sync 200 path ----
  if (!resp.success || !resp.data?.query_id) {
    throw new Error(resp.error || '主查詢執行失敗');
  }
  queryId.value = String(resp.data.query_id);
  committedDateRange.start_date = filters.start_date;
  committedDateRange.end_date = filters.end_date;
}

function buildViewParams(page) {
  return {
    query_id: queryId.value,
    workcenter_groups: parsedFilters.value.workcenter_groups,
    lines: parsedFilters.value.lines,
    packages: parsedFilters.value.packages,
    types: parsedFilters.value.types,
    functions: parsedFilters.value.functions,
    risk_threshold: parsedFilters.value.risk_threshold,
    min_scrap_qty: parsedFilters.value.min_scrap_qty,
    granularity: granularity.value,
    page,
    per_page: pagination.value.per_page,
    sort_by: sortState.sort_by,
    sort_dir: sortState.sort_dir,
  };
}

async function fetchViewPayload(page = 1) {
  if (!queryId.value) {
    throw new Error('尚未建立日期查詢快取');
  }

  // ── Task 7.2: DuckDB-WASM mode path ──────────────────────────────────
  if (duckdbMode.value && duckdb.isActive.value) {
    try {
      const result = await duckdb.computeView({
        filters: {
          departments: parsedFilters.value.workcenter_groups,
          lines: parsedFilters.value.lines,
          packages: parsedFilters.value.packages,
          types: parsedFilters.value.types,
          functions: parsedFilters.value.functions,
        },
        granularity: granularity.value,
        riskThreshold: Number(parsedFilters.value.risk_threshold) || 98,
        minScrapQty: Number(parsedFilters.value.min_scrap_qty) || 1,
        sortBy: sortState.sort_by,
        sortDir: sortState.sort_dir,
        page,
        perPage: pagination.value.per_page,
      });
      return result;
    } catch (err) {
      console.warn('[DuckDB] computeView failed, falling back to server:', err);
      duckdbMode.value = false;
      duckdb.deactivate();
    }
  }

  // ── Server-side path ──────────────────────────────────────────────────
  const resp = await apiGet('/api/yield-alert/view', {
    params: buildViewParams(page),
    timeout: API_TIMEOUT,
  });

  if (!resp.success) {
    throw new Error(resp.error || '視圖查詢失敗');
  }

  const payload = resp.data || {};

  // ── Task 7.2: Activate DuckDB mode for large datasets ─────────────────
  const totalRowCount = payload.total_row_count ?? 0;
  const spoolUrl = payload.spool_download_url;
  if (
    spoolUrl
    && totalRowCount >= DUCKDB_THRESHOLD
    && isDuckDBSupported()
    && !duckdbMode.value
    && !duckdbActivating.value
  ) {
    duckdbActivating.value = true;
    // Activate in background so UI can render server payload immediately.
    void duckdb.activate(spoolUrl)
      .then(() => {
        duckdbMode.value = true;
      })
      .catch((err) => {
        console.warn('[DuckDB] activation failed, staying in server mode:', err);
      })
      .finally(() => {
        duckdbActivating.value = false;
      });
  }

  return payload;
}

function applyFullView(payload = {}) {
  summary.value = payload.summary || summary.value;
  trend.value = payload.trend?.items || [];
  heatmapData.value = payload.heatmap?.items || [];
  stationSummary.value = payload.station_summary?.items || [];
  packageSummary.value = payload.package_summary?.items || [];
  alerts.value = payload.alerts?.items || [];
  pagination.value = payload.alerts?.pagination || pagination.value;

  const fo = payload.filter_options || {};
  if (fo.lines?.length) lineOptions.value = fo.lines;
  if (fo.packages?.length) packageOptions.value = fo.packages;
  if (fo.types?.length) typeOptions.value = fo.types;
  if (fo.functions?.length) functionOptions.value = fo.functions;
}

async function loadCachedView(page = 1) {
  const payload = await fetchViewPayload(page);
  applyFullView(payload);
}

async function loadAlertPage(page = 1) {
  const payload = await fetchViewPayload(page);
  alerts.value = payload.alerts?.items || [];
  pagination.value = payload.alerts?.pagination || pagination.value;
}

async function runQuery(page = 1) {
  if (!canSubmit.value) {
    return;
  }

  loading.value = true;
  summaryLoading.value = true;
  trendLoading.value = true;
  alertLoading.value = true;
  errorMessage.value = '';
  warningMessage.value = '';

  try {
    if (isDateStageDirty.value) {
      await executePrimaryQuery();
    }
    try {
      await loadCachedView(page);
    } catch (error) {
      if (isCacheExpiredError(error)) {
        warningMessage.value = '快取已過期，正在重新建立資料快取，請稍候…';
        await executePrimaryQuery();
        warningMessage.value = '';
        await loadCachedView(page);
      } else {
        throw error;
      }
    }
    hasQueried.value = true;
    syncUrlState();
  } catch (error) {
    if (error?.name === 'AbortError' || /abort/i.test(error?.message || '')) {
      errorMessage.value = '查詢逾時，請縮小日期範圍後重試';
    } else {
      errorMessage.value = error.message || '查詢失敗，請稍後再試';
    }
  } finally {
    loading.value = false;
    summaryLoading.value = false;
    trendLoading.value = false;
    alertLoading.value = false;
  }
}

async function runAlertPage(page = 1) {
  if (!queryId.value) {
    return;
  }
  paginationLoading.value = true;
  errorMessage.value = '';

  try {
    try {
      await loadAlertPage(page);
    } catch (error) {
      if (isCacheExpiredError(error)) {
        warningMessage.value = '快取已過期，正在重新建立資料快取，請稍候…';
        await executePrimaryQuery();
        warningMessage.value = '';
        await loadAlertPage(page);
      } else {
        throw error;
      }
    }
    hasQueried.value = true;
    syncUrlState();
  } catch (error) {
    errorMessage.value = error.message || '查詢失敗，請稍後再試';
  } finally {
    paginationLoading.value = false;
  }
}

function onSort(field) {
  if (!hasQueried.value) {
    return;
  }
  if (sortState.sort_by === field) {
    sortState.sort_dir = sortState.sort_dir === 'asc' ? 'desc' : 'asc';
  } else {
    sortState.sort_by = field;
    sortState.sort_dir = field === 'date_bucket' ? 'desc' : 'asc';
  }
  // Sort only affects alert row order — use runAlertPage to avoid a full-page
  // overlay and avoid re-fetching summary/trend/heatmap which haven't changed.
  void runAlertPage(1);
}

function goToPage(nextPage) {
  const totalPages = Number(pagination.value.total_pages || 1);
  if (
    loading.value
    || paginationLoading.value
    || nextPage < 1
    || nextPage > totalPages
  ) {
    return;
  }
  void runAlertPage(nextPage);
}

function sortIcon(field) {
  if (sortState.sort_by !== field) return ' \u2195';
  return sortState.sort_dir === 'asc' ? ' \u2191' : ' \u2193';
}

function sortIconComponent(field: string) {
  if (sortState.sort_by !== field) return ArrowUpDown;
  return sortState.sort_dir === 'asc' ? ArrowUp : ArrowDown;
}

function _buildAlertsCSV(items) {
  const header = ['\u65e5\u671f', '\u5de5\u55ae', 'LOT', '\u539f\u56e0\u78bc', '\u7ad9\u5225\u7fa4\u7d44', 'Package', 'Type', '\u8f49\u51fa\u6578', '\u5831\u5ee2\u91cf', '\u826f\u7387(%)', '\u98a8\u96aa\u7b49\u7d1a', '\u98a8\u96aa\u5206\u6578'].join(',');
  const rows = items.map((r) => [
    r.date_bucket,
    r.workorder,
    r.source_code ?? '',
    r.reason_code ?? '',
    r.department ?? '',
    r.package ?? '',
    r.type ?? '',
    Number(r.transaction_qty ?? 0),
    Number(r.scrap_qty ?? 0),
    Number(r.yield_pct ?? 0).toFixed(4),
    r.risk_level ?? '',
    Number(r.risk_score ?? 0).toFixed(2),
  ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
  return [header, ...rows].join('\n');
}

function _triggerCSVDownload(csv: string, filename: string) {
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function exportAllAlertsCSV() {
  if (!queryId.value || isExporting.value) return;
  isExporting.value = true;
  try {
    let allItems: unknown[] = [];

    if (duckdbMode.value && duckdb.isActive.value) {
      // DuckDB path: all records in memory \u2014 get everything in one shot
      const result = await duckdb.computeView({
        filters: {
          departments: parsedFilters.value.workcenter_groups,
          lines: parsedFilters.value.lines,
          packages: parsedFilters.value.packages,
          types: parsedFilters.value.types,
          functions: parsedFilters.value.functions,
        },
        granularity: granularity.value,
        riskThreshold: Number(parsedFilters.value.risk_threshold) || 98,
        minScrapQty: Number(parsedFilters.value.min_scrap_qty) || 1,
        sortBy: sortState.sort_by,
        sortDir: sortState.sort_dir,
        page: 1,
        perPage: 1_000_000,
      });
      allItems = result.alerts?.items || [];
    } else {
      // Server path: fetch all pages with max per_page (200)
      const EXPORT_PER_PAGE = 200;
      const baseParams = {
        query_id: queryId.value,
        workcenter_groups: parsedFilters.value.workcenter_groups,
        lines: parsedFilters.value.lines,
        packages: parsedFilters.value.packages,
        types: parsedFilters.value.types,
        functions: parsedFilters.value.functions,
        risk_threshold: parsedFilters.value.risk_threshold,
        min_scrap_qty: parsedFilters.value.min_scrap_qty,
        granularity: granularity.value,
        sort_by: sortState.sort_by,
        sort_dir: sortState.sort_dir,
        per_page: EXPORT_PER_PAGE,
      };
      const first = await apiGet('/api/yield-alert/alerts', { params: { ...baseParams, page: 1 }, timeout: API_TIMEOUT });
      if (!first.success) throw new Error(first.error || '\u532f\u51fa\u5931\u6557');
      allItems = [...(first.data?.items || [])];
      const totalPages = first.data?.pagination?.total_pages || 1;
      for (let p = 2; p <= totalPages; p++) {
        const resp = await apiGet('/api/yield-alert/alerts', { params: { ...baseParams, page: p }, timeout: API_TIMEOUT });
        if (resp.success) allItems.push(...(resp.data?.items || []));
      }
    }

    if (!allItems.length) return;
    _triggerCSVDownload(_buildAlertsCSV(allItems), `\u544a\u8b66\u5019\u9078\u6e05\u55ae_${filters.start_date}_${filters.end_date}.csv`);
  } catch (_err) {
    errorMessage.value = '\u532f\u51fa\u5931\u6557\uff0c\u8acb\u7a0d\u5f8c\u518d\u8a66';
  } finally {
    isExporting.value = false;
  }
}

function riskClass(level) {
  if (level === 'high') return 'risk-high';
  if (level === 'medium') return 'risk-medium';
  return 'risk-low';
}

async function toggleReasonDetail(row) {
  const rowKey = alertRowKey(row);
  if (expandedRowKey.value === rowKey) {
    expandedRowKey.value = '';
    return;
  }
  expandedRowKey.value = rowKey;
  reasonDetailRows.value = [];
  reasonDetailLoading.value = true;
  try {
    const resp = await apiGet('/api/yield-alert/reason-detail', {
      params: {
        workorder: row.workorder,
        date_bucket: row.date_bucket,
        reason_code: row.reason_code || '',
        department: row.department || '',
        source_code: row.source_code || '',
        granularity: granularity.value,
      },
      timeout: API_TIMEOUT,
    });
    if (resp.success) {
      reasonDetailRows.value = resp.data?.items || [];
    }
  } catch (_error) {
    reasonDetailRows.value = [];
  } finally {
    reasonDetailLoading.value = false;
  }
}

function resetFilters() {
  queryId.value = '';
  hasQueried.value = false;
  committedDateRange.start_date = '';
  committedDateRange.end_date = '';
  filters.workcenterGroups = [];
  filters.lines = [];
  filters.packages = [];
  filters.types = [];
  filters.functions = [];
  filters.risk_threshold = '98';
  filters.min_scrap_qty = '1';
  setDefaultDateRange();
  summary.value = { transaction_qty: 0, scrap_qty: 0, yield_pct: 100 };
  trend.value = [];
  heatmapData.value = [];
  stationSummary.value = [];
  packageSummary.value = [];
  alerts.value = [];
  pagination.value = { page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 1 };
  paginationLoading.value = false;
  duckdbActivating.value = false;
  expandedRowKey.value = '';
  reasonDetailRows.value = [];
  warningMessage.value = '';
  errorMessage.value = '';
  syncUrlState();
}

// ── Issue 1: granularity 變更立即 re-query，不需點套用篩選 ─────────────────
watch(granularity, (newVal, oldVal) => {
  if (newVal !== oldVal && queryId.value && hasQueried.value && !loading.value) {
    void runQuery(1);
  }
});

// ── Process type: when changed, clear stale state (GA%/GC% have different products/lines)
// User must click "執行日期查詢" to fetch new data after switching.
watch(selectedProcessType, (_newVal, oldVal) => {
  if (!oldVal) return; // skip initial mount
  queryId.value = '';
  hasQueried.value = false;
  filters.workcenterGroups = [];
  filters.lines = [];
  filters.packages = [];
  filters.types = [];
  filters.functions = [];
  lineOptions.value = [];
  packageOptions.value = [];
  typeOptions.value = [];
  functionOptions.value = [];
  summary.value = { transaction_qty: 0, scrap_qty: 0, yield_pct: 100 };
  trend.value = [];
  heatmapData.value = [];
  stationSummary.value = [];
  packageSummary.value = [];
  alerts.value = [];
});

// ── Cross-filter: dimension filter changes narrow other dropdowns' options ────
// Does NOT auto-run the full query; user still clicks "套用篩選" to execute.
let _crossFilterTimer: ReturnType<typeof setTimeout> | null = null;
async function fetchCrossFilterOptions() {
  if (!queryId.value || !hasQueried.value) return;
  const params = new URLSearchParams({ query_id: queryId.value });
  for (const g of filters.workcenterGroups) params.append('workcenter_groups', g);
  for (const v of filters.lines)            params.append('lines', v);
  for (const v of filters.packages)         params.append('packages', v);
  for (const v of filters.types)            params.append('types', v);
  for (const v of filters.functions)        params.append('functions', v);
  try {
    const resp = await apiGet(`/api/yield-alert/cross-filter-options?${params.toString()}`, { timeout: 15000 });
    if (!resp.success) return;
    const fo = resp.data || {};
    if (fo.lines?.length)     lineOptions.value     = fo.lines;
    if (fo.packages?.length)  packageOptions.value  = fo.packages;
    if (fo.types?.length)     typeOptions.value     = fo.types;
    if (fo.functions?.length) functionOptions.value = fo.functions;
  } catch (_e) {
    // Cross-filter is best-effort; silently ignore network errors
  }
}
function scheduleCrossFilter() {
  if (!queryId.value || !hasQueried.value) return;
  clearTimeout(_crossFilterTimer);
  _crossFilterTimer = setTimeout(() => { void fetchCrossFilterOptions(); }, 300);
}

watch(() => [...filters.workcenterGroups], scheduleCrossFilter);
watch(() => [...filters.lines],            scheduleCrossFilter);
watch(() => [...filters.packages],         scheduleCrossFilter);
watch(() => [...filters.types],            scheduleCrossFilter);
watch(() => [...filters.functions],        scheduleCrossFilter);

function cancelAsyncJob(): void {
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  jobProgress.active = false;
  loading.value = false;
}

onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
  loadFilterOptions();
});

onUnmounted(() => {
  _jobAbortController?.abort();
  duckdbActivating.value = false;
  duckdb.deactivate();
});
</script>

<template>
  <div class="dashboard theme-yield-alert-center" data-testid="yield-alert-app">
    <section class="filter-panel primary-query-panel">
      <header class="panel-header">
        <h2>日期查詢</h2>
        <span v-if="queryId" class="query-status-badge">資料已載入</span>
      </header>
      <div class="filter-row two">
        <label>
          開始日期
          <input v-model="filters.start_date" class="text-input" type="date" data-testid="start-date" />
        </label>
        <label>
          結束日期
          <input v-model="filters.end_date" class="text-input" type="date" data-testid="end-date" />
        </label>
      </div>
      <div class="filter-row one">
        <div class="ctrl-item">
          <span class="ctrl-label">製程類型</span>
          <div class="process-type-toggle" role="radiogroup" aria-label="製程類型選擇" data-testid="process-type-select">
            <label
              v-for="opt in PROCESS_TYPE_OPTIONS"
              :key="opt.value"
              class="process-type-option"
              :class="{ active: selectedProcessType === opt.value }"
            >
              <input
                type="radio"
                :value="opt.value"
                v-model="selectedProcessType"
                class="sr-only"
                name="process-type"
              />
              {{ opt.label }}
            </label>
          </div>
        </div>
      </div>
      <div class="filter-row one">
        <div class="filter-actions">
          <button class="ui-btn ui-btn--primary" :disabled="!canSubmit" @click="runQuery(1)" data-testid="query-submit-btn">
            {{ loading ? '查詢中...' : isDateStageDirty ? '執行日期查詢' : '重新查詢日期範圍' }}
          </button>
        </div>
      </div>
    </section>

    <AsyncQueryProgress
      :active="jobProgress.active"
      :progress="jobProgress.progress"
      :pct="jobProgress.pct"
      :elapsed-seconds="0"
      :status="jobProgress.status"
      @cancel="cancelAsyncJob"
      data-testid="loading-state"
    />

    <section class="filter-panel supplementary-query-panel">
      <header class="panel-header">
        <h2>快取內計算</h2>
      </header>
      <template v-if="queryId">
        <!-- Dimension selects -->
        <div class="filter-row three">
          <label>
            站別群組
            <MultiSelect
              v-model="filters.workcenterGroups"
              :options="workcenterGroupOptions"
              placeholder="請選擇站別群組"
              :searchable="true"
            />
          </label>
          <label v-if="lineOptions.length > 0">
            Line
            <MultiSelect
              v-model="filters.lines"
              :options="lineOptions"
              placeholder="請選擇 Line"
              :searchable="true"
            />
          </label>
          <label v-if="packageOptions.length > 0">
            Package
            <MultiSelect
              v-model="filters.packages"
              :options="packageOptions"
              placeholder="請選擇 Package"
              :searchable="true"
            />
          </label>
        </div>
        <div v-if="typeOptions.length > 0 || functionOptions.length > 0" class="filter-row three">
          <label v-if="typeOptions.length > 0">
            Type
            <MultiSelect
              v-model="filters.types"
              :options="typeOptions"
              placeholder="請選擇 Type"
              :searchable="true"
            />
          </label>
          <label v-if="functionOptions.length > 0">
            Function
            <MultiSelect
              v-model="filters.functions"
              :options="functionOptions"
              placeholder="請選擇 Function"
              :searchable="true"
            />
          </label>
        </div>
        <!-- Control bar: thresholds + granularity + submit in one line -->
        <div class="control-bar">
          <label class="ctrl-item">
            風險門檻良率(%)
            <input v-model="filters.risk_threshold" class="text-input ctrl-input" type="number" step="0.1" min="0" max="100" data-testid="risk-threshold-input" />
          </label>
          <label class="ctrl-item">
            最小報廢量
            <input v-model="filters.min_scrap_qty" class="text-input ctrl-input" type="number" step="0.1" min="0" data-testid="min-scrap-qty-input" />
          </label>
          <div class="ctrl-item">
            <span class="ctrl-label">時間粒度</span>
            <div class="granularity-toggle" data-testid="granularity-select">
              <button
                v-for="opt in GRANULARITY_OPTIONS"
                :key="opt.value"
                class="gran-btn"
                :class="{ active: granularity === opt.value }"
                @click="granularity = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div class="ctrl-item ctrl-action">
            <button class="ui-btn ui-btn--primary" :disabled="!canApplySupplementary" @click="runQuery(1)">
              {{ submitLabel }}
            </button>
          </div>
        </div>
      </template>
      <EmptyState v-else type="no-data" />
    </section>

    <section class="status-stack">
      <ErrorBanner :message="errorMessage" @dismiss="errorMessage = ''" data-testid="error-banner" />
      <div v-if="warningMessage" class="status warn">{{ warningMessage }}</div>
    </section>

    <section class="summary-section" data-testid="summary-cards">
      <SummaryCardGroup :columns="3">
        <SummaryCard
          v-for="card in summaryCards"
          :key="card.key"
          :label="card.label"
          :value="card.value"
          :accent="card.accent"
          :format="card.format"
        />
      </SummaryCardGroup>
    </section>

    <div v-if="hasQueried" class="chart-grid">
      <section class="trend-panel chart-grid-full" data-testid="trend-chart">
        <LoadingSpinner v-if="trendLoading" size="sm" />
        <YieldTrendChart
          :trend="trend"
          :risk-threshold="Number(filters.risk_threshold || 98)"
          :granularity="granularity"
        />
      </section>

      <section v-if="packageSummary.length > 0" class="package-summary-panel chart-grid-full">
        <YieldPackageChart
          :package-summary="packageSummary"
          :risk-threshold="Number(filters.risk_threshold || 98)"
        />
      </section>

      <section class="heatmap-panel chart-grid-full" data-testid="heatmap-chart">
        <YieldHeatmap :heatmap="heatmapData" :granularity="granularity" />
      </section>
    </div>

    <section class="alerts-panel">
      <header class="alerts-header">
        <div class="alerts-header-left">
          <h2>告警候選清單</h2>
          <span class="alerts-count">{{ pagination.total }} 筆</span>
        </div>
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm btn-export-csv"
          :disabled="!hasData || isExporting"
          @click="exportAllAlertsCSV"
          :title="isExporting ? '匯出中...' : `匯出全部 ${pagination.total} 筆資料為 CSV`"
        >
          <LoadingSpinner v-if="isExporting" size="sm" />
          <Download v-else :size="13" />
          {{ isExporting ? '匯出中...' : '匯出全部 CSV' }}
        </button>
      </header>
      <p class="alerts-hint">風險分數 = 良率缺口（門檻 − 實際良率，%）+ 報廢量權重（每 20 pcs 加 1 分，上限 10 分）；分數越高代表優先處理順序越前</p>
      <div class="ya-table-scroll" :class="{ 'is-loading': paginationLoading }" v-if="hasData" data-testid="alerts-table">
        <table class="ya-table">
          <thead class="ya-table-head">
            <tr>
              <th class="ya-th ya-th--expand"></th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'date_bucket' }" @click="onSort('date_bucket')">
                <span class="ya-th-inner">日期 <component :is="sortIconComponent('date_bucket')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'date_bucket' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'workorder' }" @click="onSort('workorder')">
                <span class="ya-th-inner">工單 <component :is="sortIconComponent('workorder')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'workorder' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'source_code' }" @click="onSort('source_code')">
                <span class="ya-th-inner">LOT <component :is="sortIconComponent('source_code')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'source_code' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'reason_code' }" @click="onSort('reason_code')">
                <span class="ya-th-inner">原因碼 <component :is="sortIconComponent('reason_code')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'reason_code' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'department' }" @click="onSort('department')">
                <span class="ya-th-inner">站別群組 <component :is="sortIconComponent('department')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'department' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'package' }" @click="onSort('package')">
                <span class="ya-th-inner">Package <component :is="sortIconComponent('package')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'package' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'type' }" @click="onSort('type')">
                <span class="ya-th-inner">Type <component :is="sortIconComponent('type')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'type' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'transaction_qty' }" @click="onSort('transaction_qty')">
                <span class="ya-th-inner">轉出數 <component :is="sortIconComponent('transaction_qty')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'transaction_qty' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'scrap_qty' }" @click="onSort('scrap_qty')">
                <span class="ya-th-inner">報廢量 <component :is="sortIconComponent('scrap_qty')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'scrap_qty' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'yield_pct' }" @click="onSort('yield_pct')">
                <span class="ya-th-inner">良率(%) <component :is="sortIconComponent('yield_pct')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'yield_pct' }" /></span>
              </th>
              <th class="ya-th ya-th--sortable" :class="{ 'ya-th--sorted': sortState.sort_by === 'risk_score' }" @click="onSort('risk_score')">
                <span class="ya-th-inner">風險分數 <component :is="sortIconComponent('risk_score')" :size="12" class="ya-sort-icon" :class="{ 'ya-sort-icon--active': sortState.sort_by === 'risk_score' }" /></span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, rowIdx) in alerts" :key="alertRowKey(row)">
              <tr class="ya-tr" :class="{ 'ya-tr--even': rowIdx % 2 === 1 }">
                <td class="ya-td ya-td--expand">
                  <button
                    class="ya-expand-btn"
                    :aria-expanded="expandedRowKey === alertRowKey(row)"
                    @click="toggleReasonDetail(row)"
                    data-testid="row-expand-btn"
                  >
                    <svg class="ya-expand-icon" :class="{ 'ya-expand-icon--open': expandedRowKey === alertRowKey(row) }" width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </td>
                <td class="ya-td">{{ row.date_bucket }}</td>
                <td class="ya-td">{{ row.workorder }}</td>
                <td class="ya-td">{{ row.source_code != null ? row.source_code : '—' }}</td>
                <td class="ya-td">{{ row.reason_code }}</td>
                <td class="ya-td">{{ row.department }}</td>
                <td class="ya-td">{{ row.package || '' }}</td>
                <td class="ya-td">{{ row.type || '' }}</td>
                <td class="ya-td ya-td--right">{{ Number(row.transaction_qty || 0).toLocaleString() }}</td>
                <td class="ya-td ya-td--right">{{ Number(row.scrap_qty || 0).toLocaleString() }}</td>
                <td class="ya-td ya-td--right">{{ Number(row.yield_pct || 0).toFixed(2) }}</td>
                <td class="ya-td">
                  <span class="risk-pill" :class="riskClass(row.risk_level)">
                    {{ row.risk_level }} · {{ Number(row.risk_score || 0).toFixed(2) }}
                  </span>
                </td>
              </tr>
              <tr v-if="expandedRowKey === alertRowKey(row)" class="ya-expand-row" data-testid="row-detail">
                <td colspan="12" class="ya-expand-td">
                  <EmptyState v-if="reasonDetailLoading" type="loading" />
                  <EmptyState v-else-if="reasonDetailRows.length === 0" type="filter-empty" />
                  <div v-else class="reason-sub-wrap">
                    <table class="reason-sub-table">
                      <thead>
                        <tr>
                          <th>LOT</th>
                          <th>站別</th>
                          <th>Package</th>
                          <th>Function</th>
                          <th>Type</th>
                          <th>Product</th>
                          <th>原因</th>
                          <th>Equipment</th>
                          <th>Comment</th>
                          <th>扣帳報廢量</th>
                          <th>不扣帳報廢量</th>
                          <th>報廢時間</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(detail, idx) in reasonDetailRows" :key="idx">
                          <td>{{ detail.containername }}</td>
                          <td>{{ detail.workcentername }}</td>
                          <td>{{ detail.package_name }}</td>
                          <td>{{ detail.pj_function }}</td>
                          <td>{{ detail.pj_type }}</td>
                          <td>{{ detail.productname }}</td>
                          <td>{{ detail.lossreasonname }}</td>
                          <td>{{ detail.equipmentname }}</td>
                          <td>{{ detail.rejectcomment }}</td>
                          <td class="num">{{ Number(detail.reject_total_qty || 0).toLocaleString() }}</td>
                          <td class="num">{{ Number(detail.defect_qty || 0).toLocaleString() }}</td>
                          <td class="nowrap">{{ detail.txn_time }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <EmptyState v-else :type="alertLoading || paginationLoading ? 'loading' : hasQueried ? 'filter-empty' : 'no-data'" data-testid="empty-state" />

      <footer class="pagination">
        <button class="ui-btn ui-btn--ghost" :disabled="loading || paginationLoading || pagination.page <= 1" @click="goToPage(pagination.page - 1)">上一頁</button>
        <span>第 {{ pagination.page }} / {{ pagination.total_pages }} 頁</span>
        <button class="ui-btn ui-btn--ghost" :disabled="loading || paginationLoading || pagination.page >= pagination.total_pages" @click="goToPage(pagination.page + 1)">下一頁</button>
      </footer>
    </section>
    <LoadingOverlay v-if="loading && !jobProgress.active" tier="page" />
  </div>
</template>
