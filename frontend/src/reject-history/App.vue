<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

import { apiGet } from '../core/api.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';
import MultiSelect from '../resource-shared/components/MultiSelect.vue';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

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
  paretoTop80: true,
});

const page = ref(1);
const detailReason = ref('');

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
const pareto = ref({ items: [], metric_mode: 'reject_total', pareto_scope: 'top80' });
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
  pareto: false,
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

  filters.includeExcludedScrap = readBooleanParam(params, 'include_excluded_scrap', false);
  filters.excludeMaterialScrap = readBooleanParam(params, 'exclude_material_scrap', true);
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

  if (filters.includeExcludedScrap) {
    params.set('include_excluded_scrap', 'true');
  }
  params.set('exclude_material_scrap', String(filters.excludeMaterialScrap));

  if (!filters.paretoTop80) {
    params.set('pareto_scope_all', 'true');
  }

  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/reject-history?${params.toString()}`);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
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
  };

  if (reason) {
    params.reasons = [reason];
  }

  return params;
}

function buildParetoParams() {
  return {
    ...buildCommonParams({ reason: filters.reason }),
    metric_mode: 'reject_total',
    pareto_scope: filters.paretoTop80 ? 'top80' : 'all',
  };
}

function buildListParams() {
  const effectiveReason = detailReason.value || filters.reason;
  return {
    ...buildCommonParams({ reason: effectiveReason }),
    page: page.value,
    per_page: DEFAULT_PER_PAGE,
  };
}

async function fetchOptions() {
  const response = await apiGet('/api/reject-history/options', {
    params: {
      start_date: filters.startDate,
      end_date: filters.endDate,
      include_excluded_scrap: filters.includeExcludedScrap,
      exclude_material_scrap: filters.excludeMaterialScrap,
    },
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入篩選選項失敗');
  return payload.data || {};
}

async function fetchSummary() {
  const response = await apiGet('/api/reject-history/summary', {
    params: buildCommonParams(),
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入摘要資料失敗');
  return payload;
}

async function fetchTrend() {
  const response = await apiGet('/api/reject-history/trend', {
    params: {
      ...buildCommonParams(),
      granularity: 'day',
    },
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入趨勢資料失敗');
  return payload;
}

async function fetchPareto() {
  const response = await apiGet('/api/reject-history/reason-pareto', {
    params: buildParetoParams(),
    timeout: API_TIMEOUT,
  });
  const payload = unwrapApiResult(response, '載入柏拉圖資料失敗');
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
  loading.pareto = true;
  errorMessage.value = '';

  try {
    const tasks = [fetchSummary(), fetchTrend(), fetchPareto(), fetchList()];
    if (loadOptions) {
      loading.options = true;
      tasks.push(fetchOptions());
    }

    const responses = await Promise.all(tasks);
    if (isStaleRequest(requestId)) {
      return;
    }

    const [summaryResp, trendResp, paretoResp, listResp, optionsResp] = responses;

    summary.value = summaryResp.data || summary.value;
    trend.value = trendResp.data || trend.value;
    pareto.value = paretoResp.data || pareto.value;
    detail.value = listResp.data || detail.value;

    const meta = {
      ...(summaryResp.meta || {}),
      ...(trendResp.meta || {}),
      ...(paretoResp.meta || {}),
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
    loading.pareto = false;
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

async function loadParetoOnly() {
  const requestId = nextRequestId();
  loading.pareto = true;
  errorMessage.value = '';

  try {
    const paretoResp = await fetchPareto();
    if (isStaleRequest(requestId)) {
      return;
    }
    pareto.value = paretoResp.data || pareto.value;
    mergePolicyMeta(paretoResp.meta || {});
    updateUrlState();
  } catch (error) {
    if (isStaleRequest(requestId)) {
      return;
    }
    errorMessage.value = error?.message || '載入柏拉圖資料失敗';
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    loading.pareto = false;
  }
}

function applyFilters() {
  page.value = 1;
  detailReason.value = '';
  void loadAllData({ loadOptions: true });
}

function clearFilters() {
  setDefaultDateRange();
  filters.workcenterGroups = [];
  filters.packages = [];
  filters.reason = '';
  detailReason.value = '';
  filters.includeExcludedScrap = false;
  filters.excludeMaterialScrap = true;
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
  void loadParetoOnly();
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

const quantityChartOption = computed(() => {
  const items = Array.isArray(trend.value?.items) ? trend.value.items : [];
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['扣帳報廢量', '不扣帳報廢量'],
      bottom: 0,
    },
    grid: { left: 48, right: 24, top: 22, bottom: 70 },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.bucket_date || ''),
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter(value) {
          return Number(value || 0).toLocaleString('zh-TW');
        },
      },
    },
    series: [
      {
        name: '扣帳報廢量',
        type: 'bar',
        data: items.map((item) => Number(item.REJECT_TOTAL_QTY || 0)),
        itemStyle: { color: '#dc2626' },
        barMaxWidth: 28,
      },
      {
        name: '不扣帳報廢量',
        type: 'bar',
        data: items.map((item) => Number(item.DEFECT_QTY || 0)),
        itemStyle: { color: '#0284c7' },
        barMaxWidth: 28,
      },
    ],
  };
});

const paretoChartOption = computed(() => {
  const items = Array.isArray(pareto.value?.items) ? pareto.value.items : [];
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const idx = Number(params?.[0]?.dataIndex || 0);
        const item = items[idx] || {};
        return [
          `<b>${item.reason || '(未填寫)'}</b>`,
          `報廢量: ${formatNumber(item.metric_value || 0)}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
          `累計: ${Number(item.cumPct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    legend: {
      data: ['報廢量', '累積%'],
      bottom: 0,
    },
    grid: {
      left: 52,
      right: 52,
      top: 20,
      bottom: 96,
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.reason || '(未填寫)'),
      axisLabel: {
        interval: 0,
        rotate: items.length > 6 ? 35 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 100,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '量',
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: '報廢量',
        type: 'bar',
        data: items.map((item) => Number(item.metric_value || 0)),
        barMaxWidth: 34,
        itemStyle: {
          color(params) {
            const reason = items[params.dataIndex]?.reason || '';
            return reason === detailReason.value ? '#b91c1c' : '#2563eb';
          },
          borderRadius: [4, 4, 0, 0],
        },
      },
      {
        name: '累積%',
        type: 'line',
        yAxisIndex: 1,
        data: items.map((item) => Number(item.cumPct || 0)),
        lineStyle: { color: '#f59e0b', width: 2 },
        itemStyle: { color: '#f59e0b' },
        symbolSize: 6,
      },
    ],
  };
});

function onParetoChartClick(params) {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const selected = pareto.value?.items?.[params.dataIndex]?.reason;
  onParetoClick(selected);
}

const pagination = computed(() => detail.value?.pagination || {
  page: 1,
  perPage: DEFAULT_PER_PAGE,
  total: 0,
  totalPages: 1,
});

const hasTrendData = computed(() => Array.isArray(trend.value?.items) && trend.value.items.length > 0);
const hasParetoData = computed(() => Array.isArray(pareto.value?.items) && pareto.value.items.length > 0);

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
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <section class="card">
      <div class="card-header">
        <div class="card-title">查詢條件</div>
      </div>
      <div class="card-body filter-panel">
        <div class="filter-group">
          <label class="filter-label" for="start-date">開始日期</label>
          <input id="start-date" v-model="filters.startDate" type="date" class="filter-input" />
        </div>
        <div class="filter-group">
          <label class="filter-label" for="end-date">結束日期</label>
          <input id="end-date" v-model="filters.endDate" type="date" class="filter-input" />
        </div>

        <div class="filter-group">
          <label class="filter-label">Package</label>
          <MultiSelect
            :model-value="filters.packages"
            :options="options.packages"
            placeholder="全部 Package"
            searchable
            @update:model-value="filters.packages = $event"
          />
        </div>

        <div class="filter-group filter-group-wide">
          <label class="filter-label">WORKCENTER GROUP</label>
          <MultiSelect
            :model-value="filters.workcenterGroups"
            :options="options.workcenterGroups"
            placeholder="全部工作中心群組"
            searchable
            @update:model-value="filters.workcenterGroups = $event"
          />
        </div>

        <div class="filter-group filter-group-wide">
          <label class="filter-label" for="reason">報廢原因</label>
          <select id="reason" v-model="filters.reason" class="filter-input">
            <option value="">全部原因</option>
            <option v-for="reason in options.reasons" :key="reason" :value="reason">
              {{ reason }}
            </option>
          </select>
        </div>

        <div class="filter-group filter-group-wide inline-toggle-group">
          <div class="checkbox-row">
            <label class="checkbox-pill">
              <input v-model="filters.includeExcludedScrap" type="checkbox" />
              納入不計良率報廢
            </label>
            <label class="checkbox-pill">
              <input v-model="filters.excludeMaterialScrap" type="checkbox" />
              排除原物料報廢
            </label>
            <label class="checkbox-pill">
              <input
                :checked="filters.paretoTop80"
                type="checkbox"
                @change="handleParetoScopeToggle($event.target.checked)"
              />
              Pareto 僅顯示累計前 80%
            </label>
          </div>
        </div>

        <div class="filter-actions">
          <button class="btn btn-primary" :disabled="loading.querying" @click="applyFilters">查詢</button>
          <button class="btn btn-secondary" :disabled="loading.querying" @click="clearFilters">清除條件</button>
          <button class="btn btn-light btn-export" :disabled="loading.querying" @click="exportCsv">匯出 CSV</button>
        </div>
      </div>
      <div class="card-body active-filter-chip-row" v-if="activeFilterChips.length > 0">
        <div class="filter-label">套用中篩選</div>
        <div class="chip-list">
          <div v-for="chip in activeFilterChips" :key="chip.key" class="filter-chip">
            <span>{{ chip.label }}</span>
            <button
              v-if="chip.removable"
              type="button"
              class="chip-remove"
              @click="removeFilterChip(chip)"
            >
              ×
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="summary-row reject-summary-row">
      <article
        v-for="card in kpiCards"
        :key="card.key"
        class="summary-card"
        :class="`lane-${card.lane}`"
      >
        <div class="summary-label">{{ card.label }}</div>
        <div class="summary-value small">{{ card.isPct ? formatPct(card.value) : formatNumber(card.value) }}</div>
      </article>
    </section>

    <section class="chart-grid">
      <article class="card">
        <div class="card-header"><div class="card-title">報廢量趨勢</div></div>
        <div class="card-body chart-wrap">
          <VChart :option="quantityChartOption" autoresize />
          <div v-if="!hasTrendData && !loading.querying" class="placeholder chart-empty">No data</div>
        </div>
      </article>
    </section>

    <section class="card">
      <div class="card-header pareto-header">
        <div class="card-title">報廢量 vs 報廢原因（Pareto）</div>
      </div>
      <div class="card-body pareto-layout">
        <div class="pareto-chart-wrap">
          <VChart :option="paretoChartOption" autoresize @click="onParetoChartClick" />
          <div v-if="!hasParetoData && !loading.pareto" class="placeholder chart-empty">No data</div>
        </div>
        <div class="pareto-table-wrap">
          <table class="detail-table pareto-table">
            <thead>
              <tr>
                <th>原因</th>
                <th>報廢量</th>
                <th>占比</th>
                <th>累積</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in pareto.items"
                :key="item.reason"
                :class="{ active: detailReason === item.reason }"
              >
                <td>
                  <button class="reason-link" type="button" @click="onParetoClick(item.reason)">
                    {{ item.reason }}
                  </button>
                </td>
                <td>{{ formatNumber(item.metric_value) }}</td>
                <td>{{ formatPct(item.pct) }}</td>
                <td>{{ formatPct(item.cumPct) }}</td>
              </tr>
              <tr v-if="!pareto.items || pareto.items.length === 0">
                <td colspan="4" class="placeholder">No data</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-header">
        <div class="card-title">明細列表</div>
      </div>
      <div class="card-body detail-table-wrap">
        <table class="detail-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>WORKCENTER_GROUP</th>
              <th>WORKCENTER</th>
              <th>Package</th>
              <th>原因</th>
              <th>REJECT_TOTAL_QTY</th>
              <th>DEFECT_QTY</th>
              <th>REJECT_QTY</th>
              <th>STANDBY_QTY</th>
              <th>QTYTOPROCESS_QTY</th>
              <th>INPROCESS_QTY</th>
              <th>PROCESSED_QTY</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in detail.items" :key="`${row.TXN_DAY}-${row.WORKCENTERNAME}-${row.LOSSREASONNAME}`">
              <td>{{ row.TXN_DAY }}</td>
              <td>{{ row.WORKCENTER_GROUP }}</td>
              <td>{{ row.WORKCENTERNAME }}</td>
              <td>{{ row.PRODUCTLINENAME }}</td>
              <td>{{ row.LOSSREASONNAME }}</td>
              <td>{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
              <td>{{ formatNumber(row.DEFECT_QTY) }}</td>
              <td>{{ formatNumber(row.REJECT_QTY) }}</td>
              <td>{{ formatNumber(row.STANDBY_QTY) }}</td>
              <td>{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.INPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.PROCESSED_QTY) }}</td>
            </tr>
            <tr v-if="!detail.items || detail.items.length === 0">
              <td colspan="12" class="placeholder">No data</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <button :disabled="pagination.page <= 1 || loading.list" @click="goToPage(pagination.page - 1)">Prev</button>
        <span class="page-info">
          Page {{ pagination.page }} / {{ pagination.totalPages }} · Total {{ formatNumber(pagination.total) }}
        </span>
        <button :disabled="pagination.page >= pagination.totalPages || loading.list" @click="goToPage(pagination.page + 1)">Next</button>
      </div>
    </section>
  </div>
</template>
