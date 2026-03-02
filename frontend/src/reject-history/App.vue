<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import {
  buildViewParams,
  parseMultiLineInput,
} from '../core/reject-history-filters.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';

import DetailTable from './components/DetailTable.vue';
import FilterPanel from './components/FilterPanel.vue';
import ParetoSection from './components/ParetoSection.vue';
import SummaryCards from './components/SummaryCards.vue';
import TrendChart from './components/TrendChart.vue';

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 50;
const PARETO_TOP20_DIMENSIONS = new Set(['type', 'workflow', 'equipment']);
const PARETO_DIMENSION_LABELS = {
  reason: '不良原因',
  package: 'PACKAGE',
  type: 'TYPE',
  workflow: 'WORKFLOW',
  workcenter: '站點',
  equipment: '機台',
};

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
  paretoTop80: true,
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
  paretoTop80: true,
});

// ---- Query result state ----
const queryId = ref('');
const resolutionInfo = ref(null);
const availableFilters = ref({ workcenterGroups: [], packages: [], reasons: [] });

// ---- Supplementary filters (post-query, applied via /view) ----
const supplementaryFilters = reactive({
  packages: [],
  workcenterGroups: [],
  reason: '',
});

// ---- Interactive state ----
const page = ref(1);
const selectedTrendDates = ref([]);
const trendLegendSelected = ref({ '扣帳報廢量': true, '不扣帳報廢量': true });
const paretoDimension = ref('reason');
const selectedParetoValues = ref([]);
const paretoDisplayScope = ref('all');
const dimensionParetoItems = ref([]);
const dimensionParetoLoading = ref(false);

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
  exporting: false,
});
const errorMessage = ref('');
const lastQueryAt = ref('');

// ---- Request staleness tracking ----
let activeRequestId = 0;

function nextRequestId() {
  activeRequestId += 1;
  return activeRequestId;
}

function isStaleRequest(id) {
  return id !== activeRequestId;
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

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success === true) {
    return result;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  return result;
}

// ---- Primary query (POST /query → Oracle → cache) ----
async function executePrimaryQuery() {
  const requestId = nextRequestId();
  loading.querying = true;
  loading.list = true;
  errorMessage.value = '';

  try {
    const body = { mode: queryMode.value };

    if (queryMode.value === 'date_range') {
      body.start_date = draftFilters.startDate;
      body.end_date = draftFilters.endDate;
    } else {
      body.container_input_type = containerInputType.value;
      body.container_values = parseMultiLineInput(containerInput.value);
    }

    body.include_excluded_scrap = draftFilters.includeExcludedScrap;
    body.exclude_material_scrap = draftFilters.excludeMaterialScrap;
    body.exclude_pb_diode = draftFilters.excludePbDiode;

    const resp = await apiPost('/api/reject-history/query', body, { timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    const result = unwrapApiResult(resp, '主查詢執行失敗');

    // Commit primary params for URL state and chips
    committedPrimary.mode = queryMode.value;
    committedPrimary.startDate = draftFilters.startDate;
    committedPrimary.endDate = draftFilters.endDate;
    committedPrimary.containerInputType = containerInputType.value;
    committedPrimary.containerValues =
      queryMode.value === 'container' ? parseMultiLineInput(containerInput.value) : [];
    committedPrimary.includeExcludedScrap = draftFilters.includeExcludedScrap;
    committedPrimary.excludeMaterialScrap = draftFilters.excludeMaterialScrap;
    committedPrimary.excludePbDiode = draftFilters.excludePbDiode;
    committedPrimary.paretoTop80 = draftFilters.paretoTop80;

    // Store query result
    queryId.value = result.query_id;
    resolutionInfo.value = result.resolution_info || null;
    const af = result.available_filters || {};
    availableFilters.value = {
      workcenterGroups: af.workcenter_groups || af.workcenterGroups || [],
      packages: af.packages || [],
      reasons: af.reasons || [],
    };

    // Reset supplementary + interactive
    supplementaryFilters.packages = [];
    supplementaryFilters.workcenterGroups = [];
    supplementaryFilters.reason = '';
    page.value = 1;
    selectedTrendDates.value = [];
    selectedParetoValues.value = [];
    paretoDisplayScope.value = 'all';
    paretoDimension.value = 'reason';
    dimensionParetoItems.value = [];

    // Apply initial data
    analyticsRawItems.value = Array.isArray(result.analytics_raw)
      ? result.analytics_raw
      : [];
    summary.value = result.summary || summary.value;
    detail.value = result.detail || detail.value;

    lastQueryAt.value = new Date().toLocaleString('zh-TW');
    updateUrlState();
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    if (error?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = error?.message || '主查詢執行失敗';
    }
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.querying = false;
    loading.list = false;
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
      paretoDimension: paretoDimension.value,
      paretoValues: selectedParetoValues.value,
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

    // Handle cache expired → auto re-execute primary query
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
  draftFilters.paretoTop80 = true;
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
  void refreshView();
  refreshDimensionParetoIfActive();
}

function onTrendLegendChange(selected) {
  trendLegendSelected.value = { ...selected };
  page.value = 1;
  updateUrlState();
  void refreshView();
  refreshDimensionParetoIfActive();
}

function onParetoItemToggle(itemValue) {
  const normalized = String(itemValue || '').trim();
  if (!normalized) return;
  if (selectedParetoValues.value.includes(normalized)) {
    selectedParetoValues.value = selectedParetoValues.value.filter(
      (item) => item !== normalized,
    );
  } else {
    selectedParetoValues.value = [...selectedParetoValues.value, normalized];
  }
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function handleParetoScopeToggle(checked) {
  draftFilters.paretoTop80 = Boolean(checked);
  committedPrimary.paretoTop80 = Boolean(checked);
  updateUrlState();
  refreshDimensionParetoIfActive();
}

let activeDimRequestId = 0;

async function fetchDimensionPareto(dim) {
  if (dim === 'reason' || !queryId.value) return;
  activeDimRequestId += 1;
  const myId = activeDimRequestId;
  dimensionParetoLoading.value = true;
  try {
    const params = {
      query_id: queryId.value,
      start_date: committedPrimary.startDate,
      end_date: committedPrimary.endDate,
      dimension: dim,
      metric_mode: paretoMetricMode.value === 'defect' ? 'defect' : 'reject_total',
      pareto_scope: committedPrimary.paretoTop80 ? 'top80' : 'all',
      include_excluded_scrap: committedPrimary.includeExcludedScrap,
      exclude_material_scrap: committedPrimary.excludeMaterialScrap,
      exclude_pb_diode: committedPrimary.excludePbDiode,
      packages: supplementaryFilters.packages.length > 0 ? supplementaryFilters.packages : undefined,
      workcenter_groups: supplementaryFilters.workcenterGroups.length > 0 ? supplementaryFilters.workcenterGroups : undefined,
      reason: supplementaryFilters.reason || undefined,
      trend_dates: selectedTrendDates.value.length > 0 ? selectedTrendDates.value : undefined,
    };
    const resp = await apiGet('/api/reject-history/reason-pareto', { params, timeout: API_TIMEOUT });
    if (myId !== activeDimRequestId) return;
    const result = unwrapApiResult(resp, '查詢維度 Pareto 失敗');
    dimensionParetoItems.value = result.data?.items || [];
  } catch (err) {
    if (myId !== activeDimRequestId) return;
    dimensionParetoItems.value = [];
    if (err?.name !== 'AbortError') {
      errorMessage.value = err.message || '查詢維度 Pareto 失敗';
    }
  } finally {
    if (myId === activeDimRequestId) {
      dimensionParetoLoading.value = false;
    }
  }
}

function refreshDimensionParetoIfActive() {
  if (paretoDimension.value !== 'reason') {
    void fetchDimensionPareto(paretoDimension.value);
  }
}

function onDimensionChange(dim) {
  paretoDimension.value = dim;
  selectedParetoValues.value = [];
  paretoDisplayScope.value = 'all';
  page.value = 1;
  if (dim === 'reason') {
    dimensionParetoItems.value = [];
    void refreshView();
  } else {
    void fetchDimensionPareto(dim);
    void refreshView();
  }
}

function onParetoDisplayScopeChange(scope) {
  paretoDisplayScope.value = scope === 'top20' ? 'top20' : 'all';
  updateUrlState();
}

function clearParetoSelection() {
  selectedParetoValues.value = [];
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function onSupplementaryChange(filters) {
  supplementaryFilters.packages = filters.packages || [];
  supplementaryFilters.workcenterGroups = filters.workcenterGroups || [];
  supplementaryFilters.reason = filters.reason || '';
  page.value = 1;
  selectedTrendDates.value = [];
  selectedParetoValues.value = [];
  void refreshView();
  refreshDimensionParetoIfActive();
}

function removeFilterChip(chip) {
  if (!chip?.removable) return;

  if (chip.type === 'pareto-value') {
    selectedParetoValues.value = selectedParetoValues.value.filter(
      (value) => value !== chip.value,
    );
    page.value = 1;
    updateUrlState();
    void refreshView();
    return;
  }

  if (chip.type === 'trend-dates') {
    selectedTrendDates.value = [];
    page.value = 1;
    void refreshView();
    refreshDimensionParetoIfActive();
    return;
  }

  if (chip.type === 'reason') {
    supplementaryFilters.reason = '';
    page.value = 1;
    void refreshView();
    refreshDimensionParetoIfActive();
    return;
  }

  if (chip.type === 'workcenter') {
    supplementaryFilters.workcenterGroups = supplementaryFilters.workcenterGroups.filter(
      (g) => g !== chip.value,
    );
    page.value = 1;
    void refreshView();
    refreshDimensionParetoIfActive();
    return;
  }

  if (chip.type === 'package') {
    supplementaryFilters.packages = supplementaryFilters.packages.filter(
      (p) => p !== chip.value,
    );
    page.value = 1;
    void refreshView();
    refreshDimensionParetoIfActive();
    return;
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
    if (supplementaryFilters.reason) params.set('reason', supplementaryFilters.reason);
    params.set('metric_filter', metricFilterParam());
    for (const date of selectedTrendDates.value) params.append('trend_dates', date);
    params.set('pareto_dimension', paretoDimension.value);
    for (const value of selectedParetoValues.value) params.append('pareto_values', value);

    // Policy filters (applied in-memory on cached data)
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

const allParetoItems = computed(() => {
  const raw = analyticsRawItems.value;
  if (!raw || raw.length === 0) return [];

  const mode = paretoMetricMode.value;
  if (mode === 'none') return [];

  const dateSet =
    selectedTrendDates.value.length > 0 ? new Set(selectedTrendDates.value) : null;
  const filtered = dateSet ? raw.filter((r) => dateSet.has(r.bucket_date)) : raw;
  if (filtered.length === 0) return [];

  const map = new Map();
  for (const item of filtered) {
    const key = item.reason;
    if (!map.has(key)) {
      map.set(key, {
        reason: key,
        MOVEIN_QTY: 0,
        REJECT_TOTAL_QTY: 0,
        DEFECT_QTY: 0,
        AFFECTED_LOT_COUNT: 0,
      });
    }
    const acc = map.get(key);
    acc.MOVEIN_QTY += Number(item.MOVEIN_QTY || 0);
    acc.REJECT_TOTAL_QTY += Number(item.REJECT_TOTAL_QTY || 0);
    acc.DEFECT_QTY += Number(item.DEFECT_QTY || 0);
    acc.AFFECTED_LOT_COUNT += Number(item.AFFECTED_LOT_COUNT || 0);
  }

  const withMetric = Array.from(map.values()).map((row) => {
    let mv;
    if (mode === 'all') mv = row.REJECT_TOTAL_QTY + row.DEFECT_QTY;
    else if (mode === 'reject') mv = row.REJECT_TOTAL_QTY;
    else mv = row.DEFECT_QTY;
    return { ...row, metric_value: mv };
  });

  const sorted = withMetric
    .filter((r) => r.metric_value > 0)
    .sort((a, b) => b.metric_value - a.metric_value);
  const total = sorted.reduce((sum, r) => sum + r.metric_value, 0);
  let cum = 0;
  return sorted.map((row) => {
    const pct = total ? Number(((row.metric_value / total) * 100).toFixed(4)) : 0;
    cum += pct;
    return {
      reason: row.reason,
      metric_value: row.metric_value,
      MOVEIN_QTY: row.MOVEIN_QTY,
      REJECT_TOTAL_QTY: row.REJECT_TOTAL_QTY,
      DEFECT_QTY: row.DEFECT_QTY,
      count: row.AFFECTED_LOT_COUNT,
      pct,
      cumPct: Number(cum.toFixed(4)),
    };
  });
});

const filteredParetoItems = computed(() => {
  const items = allParetoItems.value || [];
  if (!committedPrimary.paretoTop80 || items.length === 0) {
    return items;
  }
  const cutIdx = items.findIndex((item) => Number(item.cumPct || 0) >= 80);
  const top80Count = cutIdx >= 0 ? cutIdx + 1 : items.length;
  return items.slice(0, Math.max(top80Count, Math.min(5, items.length)));
});

const activeParetoItems = computed(() => {
  const baseItems =
    paretoDimension.value === 'reason'
      ? filteredParetoItems.value
      : (dimensionParetoItems.value || []);

  if (
    PARETO_TOP20_DIMENSIONS.has(paretoDimension.value)
    && paretoDisplayScope.value === 'top20'
  ) {
    return baseItems.slice(0, 20);
  }
  return baseItems;
});

const selectedParetoDimensionLabel = computed(
  () => PARETO_DIMENSION_LABELS[paretoDimension.value] || 'Pareto',
);

const activeFilterChips = computed(() => {
  const chips = [];

  // Primary query info
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

  // Policy chips
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

  // Supplementary chips (removable)
  if (supplementaryFilters.reason) {
    chips.push({
      key: `reason:${supplementaryFilters.reason}`,
      label: `原因: ${supplementaryFilters.reason}`,
      removable: true,
      type: 'reason',
      value: supplementaryFilters.reason,
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

  // Interactive chips (removable)
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

  selectedParetoValues.value.forEach((value) => {
    chips.push({
      key: `pareto-value:${paretoDimension.value}:${value}`,
      label: `${selectedParetoDimensionLabel.value}: ${value}`,
      removable: true,
      type: 'pareto-value',
      value,
    });
  });

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

  // Supplementary
  appendArrayParams(params, 'packages', supplementaryFilters.packages);
  appendArrayParams(params, 'workcenter_groups', supplementaryFilters.workcenterGroups);
  if (supplementaryFilters.reason) {
    params.set('reason', supplementaryFilters.reason);
  }

  // Interactive
  appendArrayParams(params, 'trend_dates', selectedTrendDates.value);
  params.set('pareto_dimension', paretoDimension.value);
  appendArrayParams(params, 'pareto_values', selectedParetoValues.value);
  if (paretoDisplayScope.value !== 'all') params.set('pareto_display_scope', paretoDisplayScope.value);
  if (!committedPrimary.paretoTop80) {
    params.set('pareto_scope_all', 'true');
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

  // Mode
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

  // Policy
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
  draftFilters.paretoTop80 = !readBooleanParam(params, 'pareto_scope_all', false);

  // Supplementary (will be applied after primary query)
  const urlPackages = readArrayParam(params, 'packages');
  const urlWcGroups = readArrayParam(params, 'workcenter_groups');
  const urlReason = String(params.get('reason') || '').trim();

  // Interactive
  const urlTrendDates = readArrayParam(params, 'trend_dates');
  const rawParetoDimension = String(params.get('pareto_dimension') || '').trim().toLowerCase();
  const urlParetoDimension = Object.hasOwn(PARETO_DIMENSION_LABELS, rawParetoDimension)
    ? rawParetoDimension
    : 'reason';
  const urlParetoValues = readArrayParam(params, 'pareto_values');
  const urlParetoDisplayScope = String(params.get('pareto_display_scope') || '').trim().toLowerCase();
  const parsedPage = Number(params.get('page') || '1');

  paretoDimension.value = urlParetoDimension;
  selectedParetoValues.value = urlParetoValues;
  paretoDisplayScope.value = urlParetoDisplayScope === 'top20' ? 'top20' : 'all';

  return {
    packages: urlPackages,
    workcenterGroups: urlWcGroups,
    reason: urlReason,
    trendDates: urlTrendDates,
    paretoDimension: urlParetoDimension,
    paretoValues: urlParetoValues,
    paretoDisplayScope: paretoDisplayScope.value,
    page: Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1,
  };
}

// ---- Mount ----
onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
});
</script>

<template>
  <div class="dashboard reject-history-page">
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
      @apply="applyFilters"
      @clear="clearFilters"
      @export-csv="exportCsv"
      @remove-chip="removeFilterChip"
      @pareto-scope-toggle="handleParetoScopeToggle"
      @update:query-mode="queryMode = $event"
      @update:container-input-type="containerInputType = $event"
      @update:container-input="containerInput = $event"
      @supplementary-change="onSupplementaryChange"
    />

    <template v-if="queryId">
      <SummaryCards :cards="kpiCards" />

      <TrendChart
        :items="trendItems"
        :selected-dates="selectedTrendDates"
        :loading="loading.querying"
        @date-click="onTrendDateClick"
        @legend-change="onTrendLegendChange"
      />

      <ParetoSection
        :items="activeParetoItems"
        :selected-values="selectedParetoValues"
        :display-scope="paretoDisplayScope"
        :selected-dates="selectedTrendDates"
        :metric-label="paretoMetricLabel"
        :loading="loading.querying || dimensionParetoLoading"
        :dimension="paretoDimension"
        :show-dimension-selector="committedPrimary.mode === 'date_range'"
        @item-toggle="onParetoItemToggle"
        @dimension-change="onDimensionChange"
        @display-scope-change="onParetoDisplayScopeChange"
      />

      <DetailTable
        :items="detail.items"
        :pagination="pagination"
        :loading="loading.list"
        :selected-pareto-values="selectedParetoValues"
        :selected-pareto-dimension-label="selectedParetoDimensionLabel"
        @go-to-page="goToPage"
        @clear-pareto-selection="clearParetoSelection"
      />
    </template>
  </div>
</template>
