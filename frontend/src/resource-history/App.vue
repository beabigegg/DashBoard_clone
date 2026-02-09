<script setup>
import { reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api.js';
import { buildResourceKpiFromHours } from '../core/compute.js';

import ComparisonChart from './components/ComparisonChart.vue';
import DetailSection from './components/DetailSection.vue';
import FilterBar from './components/FilterBar.vue';
import HeatmapChart from './components/HeatmapChart.vue';
import KpiCards from './components/KpiCards.vue';
import StackedChart from './components/StackedChart.vue';
import TrendChart from './components/TrendChart.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 60000;
const MAX_QUERY_DAYS = 730;

const filters = reactive({
  startDate: '',
  endDate: '',
  granularity: 'day',
  workcenterGroups: [],
  families: [],
  isProduction: false,
  isKey: false,
  isMonitor: false,
});

const options = reactive({
  workcenterGroups: [],
  families: [],
});

const summaryData = ref({
  kpi: {},
  trend: [],
  heatmap: [],
  workcenter_comparison: [],
});
const detailData = ref([]);
const hierarchyState = reactive({});

const loading = reactive({
  initial: true,
  querying: false,
  options: false,
});

const queryError = ref('');
const detailWarning = ref('');
const exportMessage = ref('');

function resetHierarchyState() {
  Object.keys(hierarchyState).forEach((key) => {
    delete hierarchyState[key];
  });
}

function setDefaultDates() {
  const today = new Date();
  const endDate = new Date(today);
  endDate.setDate(endDate.getDate() - 1);

  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 6);

  filters.startDate = toDateString(startDate);
  filters.endDate = toDateString(endDate);
}

function toDateString(value) {
  return value.toISOString().slice(0, 10);
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

function mergeComputedKpi(source) {
  return {
    ...source,
    ...buildResourceKpiFromHours(source),
  };
}

function buildQueryString() {
  const params = new URLSearchParams();

  params.append('start_date', filters.startDate);
  params.append('end_date', filters.endDate);
  params.append('granularity', filters.granularity);

  filters.workcenterGroups.forEach((group) => {
    params.append('workcenter_groups', group);
  });
  filters.families.forEach((family) => {
    params.append('families', family);
  });

  if (filters.isProduction) {
    params.append('is_production', '1');
  }
  if (filters.isKey) {
    params.append('is_key', '1');
  }
  if (filters.isMonitor) {
    params.append('is_monitor', '1');
  }

  return params.toString();
}

function validateDateRange() {
  if (!filters.startDate || !filters.endDate) {
    return '請先設定開始與結束日期';
  }

  const start = new Date(filters.startDate);
  const end = new Date(filters.endDate);
  const diffDays = (end - start) / (1000 * 60 * 60 * 24);

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

    const payload = unwrapApiResult(response, '載入篩選選項失敗');
    const data = payload.data || {};

    options.workcenterGroups = Array.isArray(data.workcenter_groups) ? data.workcenter_groups : [];
    options.families = Array.isArray(data.families) ? data.families : [];
  } finally {
    loading.options = false;
  }
}

async function executeQuery() {
  const validationError = validateDateRange();
  if (validationError) {
    queryError.value = validationError;
    return;
  }

  loading.querying = true;
  queryError.value = '';
  detailWarning.value = '';
  exportMessage.value = '';

  try {
    const queryString = buildQueryString();
    const [summaryResponse, detailResponse] = await Promise.all([
      apiGet(`/api/resource/history/summary?${queryString}`, {
        timeout: API_TIMEOUT,
        silent: true,
      }),
      apiGet(`/api/resource/history/detail?${queryString}`, {
        timeout: API_TIMEOUT,
        silent: true,
      }),
    ]);

    const summaryPayload = unwrapApiResult(summaryResponse, '查詢摘要失敗');
    const detailPayload = unwrapApiResult(detailResponse, '查詢明細失敗');

    const rawSummary = summaryPayload.data || {};
    summaryData.value = {
      ...rawSummary,
      kpi: mergeComputedKpi(rawSummary.kpi || {}),
      trend: (rawSummary.trend || []).map((item) => mergeComputedKpi(item || {})),
      heatmap: rawSummary.heatmap || [],
      workcenter_comparison: rawSummary.workcenter_comparison || [],
    };

    detailData.value = Array.isArray(detailPayload.data) ? detailPayload.data : [];
    resetHierarchyState();

    if (detailPayload.truncated) {
      detailWarning.value = `明細資料超過 ${detailPayload.max_records} 筆，僅顯示前 ${detailPayload.max_records} 筆。`;
    }
  } catch (error) {
    queryError.value = error?.message || '查詢失敗';
    summaryData.value = {
      kpi: {},
      trend: [],
      heatmap: [],
      workcenter_comparison: [],
    };
    detailData.value = [];
    resetHierarchyState();
  } finally {
    loading.querying = false;
    loading.initial = false;
  }
}

function updateFilters(nextFilters) {
  filters.startDate = nextFilters.startDate || '';
  filters.endDate = nextFilters.endDate || '';
  filters.granularity = nextFilters.granularity || 'day';
  filters.workcenterGroups = Array.isArray(nextFilters.workcenterGroups)
    ? nextFilters.workcenterGroups
    : [];
  filters.families = Array.isArray(nextFilters.families) ? nextFilters.families : [];
  filters.isProduction = Boolean(nextFilters.isProduction);
  filters.isKey = Boolean(nextFilters.isKey);
  filters.isMonitor = Boolean(nextFilters.isMonitor);
}

function handleToggleRow(rowId) {
  hierarchyState[rowId] = !hierarchyState[rowId];
}

function handleToggleAllRows({ expand, rowIds }) {
  (rowIds || []).forEach((rowId) => {
    hierarchyState[rowId] = Boolean(expand);
  });
}

function exportCsv() {
  if (!filters.startDate || !filters.endDate) {
    queryError.value = '請先設定查詢條件';
    return;
  }

  const queryString = buildQueryString();
  const link = document.createElement('a');
  link.href = `/api/resource/history/export?${queryString}`;
  link.download = `resource_history_${filters.startDate}_to_${filters.endDate}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  exportMessage.value = 'CSV 匯出中...';
}

async function initPage() {
  setDefaultDates();
  try {
    await loadOptions();
  } catch (error) {
    queryError.value = error?.message || '載入篩選選項失敗';
  }
  await executeQuery();
}

void initPage();
</script>

<template>
  <div class="resource-page">
    <div class="dashboard">
      <header class="header-gradient history-header">
        <h1>設備歷史績效</h1>
      </header>

      <FilterBar
        :filters="filters"
        :options="options"
        :loading="loading.options || loading.querying"
        @update-filters="updateFilters"
        @query="executeQuery"
      />

      <p v-if="queryError" class="error-banner query-error">{{ queryError }}</p>
      <p v-if="detailWarning" class="filter-indicator active">{{ detailWarning }}</p>
      <p v-if="exportMessage" class="filter-indicator active">{{ exportMessage }}</p>

      <KpiCards :kpi="summaryData.kpi" />

      <section class="section-card">
        <div class="section-inner">
          <div class="chart-grid">
            <TrendChart :trend="summaryData.trend || []" />
            <StackedChart :trend="summaryData.trend || []" />
            <ComparisonChart :comparison="summaryData.workcenter_comparison || []" />
            <HeatmapChart :heatmap="summaryData.heatmap || []" />
          </div>
        </div>
      </section>

      <DetailSection
        :detail-data="detailData"
        :expanded-state="hierarchyState"
        :loading="loading.querying"
        @toggle-row="handleToggleRow"
        @toggle-all="handleToggleAllRows"
        @export-csv="exportCsv"
      />
    </div>

    <div class="loading-overlay" :class="{ hidden: !loading.initial && !loading.querying }">
      <div class="loading-spinner"></div>
    </div>
  </div>
</template>
