<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';

import DetailTable from './components/DetailTable.vue';
import FilterPanel from './components/FilterPanel.vue';
import ParetoSection from './components/ParetoSection.vue';
import SummaryCards from './components/SummaryCards.vue';
import TrendChart from './components/TrendChart.vue';

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 50;

const filters = reactive({
  startDate: '',
  endDate: '',
  workcenterGroups: [],
  packages: [],
  reason: '',
  includeExcludedScrap: false,
  excludeMaterialScrap: true,
  excludePbDiode: true,
  paretoTop80: true,
});

const page = ref(1);
const detailReason = ref('');
const selectedTrendDates = ref([]);
const trendLegendSelected = ref({ '扣帳報廢量': true, '不扣帳報廢量': true });

const options = reactive({
  workcenterGroups: [],
  packages: [],
  reasons: [],
});

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

const trend = ref({ items: [], granularity: 'day' });
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

const loading = reactive({
  initial: true,
  querying: false,
  options: false,
  list: false,
});

const errorMessage = ref('');
const lastQueryAt = ref('');
const lastPolicyMeta = ref({
  include_excluded_scrap: false,
  exclusion_applied: false,
  excluded_reason_count: 0,
});

let activeRequestId = 0;

function nextRequestId() {
  activeRequestId += 1;
  return activeRequestId;
}

function isStaleRequest(requestId) {
  return requestId !== activeRequestId;
}

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
  filters.startDate = toDateString(start);
  filters.endDate = toDateString(end);
}

function readArrayParam(params, key) {
  const repeated = params.getAll(key).map((value) => String(value || '').trim()).filter(Boolean);
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
  const startDate = String(params.get('start_date') || '').trim();
  const endDate = String(params.get('end_date') || '').trim();

  if (startDate && endDate) {
    filters.startDate = startDate;
    filters.endDate = endDate;
  }

  const wcGroups = readArrayParam(params, 'workcenter_groups');
  if (wcGroups.length > 0) {
    filters.workcenterGroups = wcGroups;
  }

  const packages = readArrayParam(params, 'packages');
  if (packages.length > 0) {
    filters.packages = packages;
  }

  const reason = String(params.get('reason') || '').trim();
  if (reason) {
    filters.reason = reason;
  }
  const detailReasonFromUrl = String(params.get('detail_reason') || '').trim();
  if (detailReasonFromUrl) {
    detailReason.value = detailReasonFromUrl;
  }
  const trendDates = readArrayParam(params, 'trend_dates');
  if (trendDates.length > 0) {
    selectedTrendDates.value = trendDates;
  }

  filters.includeExcludedScrap = readBooleanParam(params, 'include_excluded_scrap', false);
  filters.excludeMaterialScrap = readBooleanParam(params, 'exclude_material_scrap', true);
  filters.excludePbDiode = readBooleanParam(params, 'exclude_pb_diode', true);
  filters.paretoTop80 = !readBooleanParam(params, 'pareto_scope_all', false);

  const parsedPage = Number(params.get('page') || '1');
  page.value = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
}

function updateUrlState() {
  const params = new URLSearchParams();

  params.set('start_date', filters.startDate);
  params.set('end_date', filters.endDate);
  filters.workcenterGroups.forEach((item) => params.append('workcenter_groups', item));
  filters.packages.forEach((item) => params.append('packages', item));

  if (filters.reason) {
    params.set('reason', filters.reason);
  }
  if (detailReason.value) {
    params.set('detail_reason', detailReason.value);
  }
  selectedTrendDates.value.forEach((d) => params.append('trend_dates', d));

  if (filters.includeExcludedScrap) {
    params.set('include_excluded_scrap', 'true');
  }
  params.set('exclude_material_scrap', String(filters.excludeMaterialScrap));
  params.set('exclude_pb_diode', String(filters.excludePbDiode));

  if (!filters.paretoTop80) {
    params.set('pareto_scope_all', 'true');
  }

  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/reject-history?${params.toString()}`);
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

function buildCommonParams({ reason = filters.reason } = {}) {
  const params = {
    start_date: filters.startDate,
    end_date: filters.endDate,
    workcenter_groups: filters.workcenterGroups,
    packages: filters.packages,
    include_excluded_scrap: filters.includeExcludedScrap,
    exclude_material_scrap: filters.excludeMaterialScrap,
    exclude_pb_diode: filters.excludePbDiode,
  };

  if (reason) {
    params.reasons = [reason];
  }

  return params;
}

function buildListParams() {
  const effectiveReason = detailReason.value || filters.reason;
  const params = {
    ...buildCommonParams({ reason: effectiveReason }),
    page: page.value,
    per_page: DEFAULT_PER_PAGE,
  };
  if (selectedTrendDates.value.length > 0) {
    const sorted = [...selectedTrendDates.value].sort();
    params.start_date = sorted[0];
    params.end_date = sorted[sorted.length - 1];
  }
  return params;
}

async function fetchOptions() {
  const response = await apiGet('/api/reject-history/options', {
    params: {
      start_date: filters.startDate,
      end_date: filters.endDate,
      include_excluded_scrap: filters.includeExcludedScrap,
      exclude_material_scrap: filters.excludeMaterialScrap,
      exclude_pb_diode: filters.excludePbDiode,
    },
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入篩選選項失敗');
  return payload.data || {};
}

async function fetchAnalytics() {
  const response = await apiGet('/api/reject-history/analytics', {
    params: {
      ...buildCommonParams(),
      metric_mode: 'reject_total',
    },
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入分析資料失敗');
  return payload;
}

async function fetchList() {
  const response = await apiGet('/api/reject-history/list', {
    params: buildListParams(),
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入明細資料失敗');
  return payload;
}

function mergePolicyMeta(meta) {
  lastPolicyMeta.value = {
    include_excluded_scrap: Boolean(meta?.include_excluded_scrap),
    exclusion_applied: Boolean(meta?.exclusion_applied),
    excluded_reason_count: Number(meta?.excluded_reason_count || 0),
  };
}

function normalizeFiltersByOptions() {
  if (filters.reason && !options.reasons.includes(filters.reason)) {
    filters.reason = '';
  }

  if (filters.packages.length > 0) {
    const packageSet = new Set(options.packages);
    filters.packages = filters.packages.filter((pkg) => packageSet.has(pkg));
  }
}

async function loadAllData({ loadOptions = true } = {}) {
  const requestId = nextRequestId();

  loading.querying = true;
  loading.list = true;
  errorMessage.value = '';

  try {
    const tasks = [fetchAnalytics(), fetchList()];
    if (loadOptions) {
      loading.options = true;
      tasks.push(fetchOptions());
    }

    const responses = await Promise.all(tasks);
    if (isStaleRequest(requestId)) {
      return;
    }

    const [analyticsResp, listResp, optionsResp] = responses;

    const analyticsData = analyticsResp.data || {};
    summary.value = analyticsData.summary || summary.value;
    trend.value = analyticsData.trend || trend.value;
    analyticsRawItems.value = Array.isArray(analyticsData.raw_items) ? analyticsData.raw_items : [];
    detail.value = listResp.data || detail.value;

    const meta = {
      ...(analyticsResp.meta || {}),
      ...(listResp.meta || {}),
    };
    mergePolicyMeta(meta);

    if (loadOptions && optionsResp) {
      options.workcenterGroups = Array.isArray(optionsResp.workcenter_groups)
        ? optionsResp.workcenter_groups
        : [];
      options.reasons = Array.isArray(optionsResp.reasons)
        ? optionsResp.reasons
        : [];
      options.packages = Array.isArray(optionsResp.packages)
        ? optionsResp.packages
        : [];
      normalizeFiltersByOptions();
    }

    lastQueryAt.value = new Date().toLocaleString('zh-TW');
    updateUrlState();
  } catch (error) {
    if (isStaleRequest(requestId)) {
      return;
    }
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    loading.initial = false;
    loading.querying = false;
    loading.options = false;
    loading.list = false;
  }
}

async function loadListOnly() {
  const requestId = nextRequestId();
  loading.list = true;
  errorMessage.value = '';

  try {
    const listResp = await fetchList();
    if (isStaleRequest(requestId)) {
      return;
    }
    detail.value = listResp.data || detail.value;
    mergePolicyMeta(listResp.meta || {});
    updateUrlState();
  } catch (error) {
    if (isStaleRequest(requestId)) {
      return;
    }
    errorMessage.value = error?.message || '載入明細資料失敗';
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    loading.list = false;
  }
}

function applyFilters() {
  page.value = 1;
  detailReason.value = '';
  selectedTrendDates.value = [];
  void loadAllData({ loadOptions: true });
}

function clearFilters() {
  setDefaultDateRange();
  filters.workcenterGroups = [];
  filters.packages = [];
  filters.reason = '';
  detailReason.value = '';
  selectedTrendDates.value = [];
  filters.includeExcludedScrap = false;
  filters.excludeMaterialScrap = true;
  filters.excludePbDiode = true;
  filters.paretoTop80 = true;
  page.value = 1;
  void loadAllData({ loadOptions: true });
}

function goToPage(nextPage) {
  if (nextPage < 1 || nextPage > Number(detail.value?.pagination?.totalPages || 1)) {
    return;
  }
  page.value = nextPage;
  void loadListOnly();
}

function onTrendDateClick(dateStr) {
  if (!dateStr) {
    return;
  }
  const idx = selectedTrendDates.value.indexOf(dateStr);
  if (idx >= 0) {
    selectedTrendDates.value = selectedTrendDates.value.filter((d) => d !== dateStr);
  } else {
    selectedTrendDates.value = [...selectedTrendDates.value, dateStr];
  }
  page.value = 1;
  void loadListOnly();
}

function onTrendLegendChange(selected) {
  trendLegendSelected.value = selected;
  updateUrlState();
}

function onParetoClick(reason) {
  if (!reason) {
    return;
  }
  detailReason.value = detailReason.value === reason ? '' : reason;
  page.value = 1;
  void loadListOnly();
}

function handleParetoScopeToggle(checked) {
  filters.paretoTop80 = Boolean(checked);
  updateUrlState();
}

function removeFilterChip(chip) {
  if (!chip?.removable) {
    return;
  }

  if (chip.type === 'reason') {
    filters.reason = '';
    detailReason.value = '';
  } else if (chip.type === 'workcenter') {
    filters.workcenterGroups = filters.workcenterGroups.filter((item) => item !== chip.value);
  } else if (chip.type === 'package') {
    filters.packages = filters.packages.filter((item) => item !== chip.value);
  } else if (chip.type === 'detail-reason') {
    detailReason.value = '';
    page.value = 1;
    void loadListOnly();
    return;
  } else if (chip.type === 'trend-dates') {
    selectedTrendDates.value = [];
    page.value = 1;
    void loadListOnly();
    return;
  } else {
    return;
  }

  page.value = 1;
  void loadAllData({ loadOptions: false });
}

function exportCsv() {
  const params = new URLSearchParams();
  params.set('start_date', filters.startDate);
  params.set('end_date', filters.endDate);
  params.set('include_excluded_scrap', String(filters.includeExcludedScrap));
  params.set('exclude_material_scrap', String(filters.excludeMaterialScrap));
  params.set('exclude_pb_diode', String(filters.excludePbDiode));

  filters.workcenterGroups.forEach((item) => params.append('workcenter_groups', item));
  filters.packages.forEach((item) => params.append('packages', item));
  const effectiveReason = detailReason.value || filters.reason;
  if (effectiveReason) {
    params.append('reasons', effectiveReason);
  }

  window.location.href = `/api/reject-history/export?${params.toString()}`;
}

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
    case 'reject': return '扣帳報廢量';
    case 'defect': return '不扣帳報廢量';
    case 'none': return '報廢量';
    default: return '全部報廢量';
  }
});

const allParetoItems = computed(() => {
  const raw = analyticsRawItems.value;
  if (!raw || raw.length === 0) return [];

  const mode = paretoMetricMode.value;
  if (mode === 'none') return [];

  const dateSet = selectedTrendDates.value.length > 0 ? new Set(selectedTrendDates.value) : null;
  const filtered = dateSet ? raw.filter((r) => dateSet.has(r.bucket_date)) : raw;
  if (filtered.length === 0) return [];

  const map = new Map();
  for (const item of filtered) {
    const key = item.reason;
    if (!map.has(key)) {
      map.set(key, { reason: key, MOVEIN_QTY: 0, REJECT_TOTAL_QTY: 0, DEFECT_QTY: 0, AFFECTED_LOT_COUNT: 0 });
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

  const sorted = withMetric.filter((r) => r.metric_value > 0).sort((a, b) => b.metric_value - a.metric_value);
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
  if (!filters.paretoTop80 || items.length === 0) {
    return items;
  }
  const top = items.filter((item) => Number(item.cumPct || 0) <= 80);
  return top.length > 0 ? top : [items[0]];
});

const activeFilterChips = computed(() => {
  const chips = [
    {
      key: 'date-range',
      label: `日期: ${filters.startDate || '-'} ~ ${filters.endDate || '-'}`,
      removable: false,
      type: 'date',
      value: '',
    },
    {
      key: 'policy-mode',
      label: filters.includeExcludedScrap ? '政策: 納入不計良率報廢' : '政策: 排除不計良率報廢',
      removable: false,
      type: 'policy',
      value: '',
    },
    {
      key: 'material-policy-mode',
      label: filters.excludeMaterialScrap ? '原物料: 已排除' : '原物料: 已納入',
      removable: false,
      type: 'policy',
      value: '',
    },
    {
      key: 'pb-diode-policy',
      label: filters.excludePbDiode ? 'PB_Diode: 已排除' : 'PB_Diode: 已納入',
      removable: false,
      type: 'policy',
      value: '',
    },
  ];

  if (filters.reason) {
    chips.push({
      key: `reason:${filters.reason}`,
      label: `原因: ${filters.reason}`,
      removable: true,
      type: 'reason',
      value: filters.reason,
    });
  }
  if (selectedTrendDates.value.length > 0) {
    const dates = selectedTrendDates.value;
    const label = dates.length === 1
      ? `趨勢日期: ${dates[0]}`
      : `趨勢日期: ${dates.length} 日`;
    chips.push({
      key: 'trend-dates',
      label,
      removable: true,
      type: 'trend-dates',
      value: '',
    });
  }
  if (detailReason.value) {
    chips.push({
      key: `detail-reason:${detailReason.value}`,
      label: `明細原因: ${detailReason.value}`,
      removable: true,
      type: 'detail-reason',
      value: detailReason.value,
    });
  }

  filters.workcenterGroups.forEach((group) => {
    chips.push({
      key: `workcenter:${group}`,
      label: `WC: ${group}`,
      removable: true,
      type: 'workcenter',
      value: group,
    });
  });

  filters.packages.forEach((pkg) => {
    chips.push({
      key: `package:${pkg}`,
      label: `Package: ${pkg}`,
      removable: true,
      type: 'package',
      value: pkg,
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

const pagination = computed(() => detail.value?.pagination || {
  page: 1,
  perPage: DEFAULT_PER_PAGE,
  total: 0,
  totalPages: 1,
});

onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
  void loadAllData({ loadOptions: true });
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
        <button type="button" class="btn btn-light" :disabled="loading.querying" @click="applyFilters">重新整理</button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <FilterPanel
      :filters="filters"
      :options="options"
      :loading="loading"
      :active-filter-chips="activeFilterChips"
      @apply="applyFilters"
      @clear="clearFilters"
      @export-csv="exportCsv"
      @remove-chip="removeFilterChip"
      @pareto-scope-toggle="handleParetoScopeToggle"
    />

    <SummaryCards :cards="kpiCards" />

    <TrendChart
      :items="trend.items"
      :selected-dates="selectedTrendDates"
      :loading="loading.querying"
      @date-click="onTrendDateClick"
      @legend-change="onTrendLegendChange"
    />

    <ParetoSection
      :items="filteredParetoItems"
      :detail-reason="detailReason"
      :selected-dates="selectedTrendDates"
      :metric-label="paretoMetricLabel"
      :loading="loading.querying"
      @reason-click="onParetoClick"
    />

    <DetailTable
      :items="detail.items"
      :pagination="pagination"
      :loading="loading.list"
      :detail-reason="detailReason"
      @go-to-page="goToPage"
      @clear-reason="onParetoClick(detailReason)"
    />
  </div>

  <div v-if="loading.initial" class="loading-overlay">
    <span class="loading-spinner"></span>
  </div>
</template>
