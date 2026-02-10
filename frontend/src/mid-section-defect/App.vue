<script setup>
import { reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api.js';
import { useAutoRefresh } from '../wip-shared/composables/useAutoRefresh.js';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import ParetoChart from './components/ParetoChart.vue';
import TrendChart from './components/TrendChart.vue';
import DetailTable from './components/DetailTable.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 120000; // 2min (genealogy can be slow)
const PAGE_SIZE = 200;

const filters = reactive({
  startDate: '',
  endDate: '',
  lossReasons: [],
});

const availableLossReasons = ref([]);

const analysisData = ref({
  kpi: {},
  charts: {},
  daily_trend: [],
  genealogy_status: 'ready',
  detail_total_count: 0,
});

const detailData = ref([]);
const detailPagination = ref({
  page: 1,
  page_size: PAGE_SIZE,
  total_count: 0,
  total_pages: 1,
});
const detailLoading = ref(false);

const loading = reactive({
  initial: false,
  querying: false,
});

const hasQueried = ref(false);
const queryError = ref('');

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
  throw new Error(result?.error || fallbackMessage);
}

function buildFilterParams() {
  const params = {
    start_date: filters.startDate,
    end_date: filters.endDate,
  };
  if (filters.lossReasons.length) {
    params.loss_reasons = filters.lossReasons.join(',');
  }
  return params;
}

async function loadLossReasons() {
  try {
    const result = await apiGet('/api/mid-section-defect/loss-reasons');
    const unwrapped = unwrapApiResult(result, '載入不良原因失敗');
    availableLossReasons.value = unwrapped.data?.loss_reasons || [];
  } catch {
    // Non-blocking — dropdown will be empty until first query
  }
}

async function loadDetail(page = 1) {
  detailLoading.value = true;
  try {
    const params = {
      ...buildFilterParams(),
      page,
      page_size: PAGE_SIZE,
    };
    const result = await apiGet('/api/mid-section-defect/analysis/detail', {
      params,
      timeout: API_TIMEOUT,
    });
    const unwrapped = unwrapApiResult(result, '載入明細失敗');
    detailData.value = unwrapped.data?.detail || [];
    detailPagination.value = unwrapped.data?.pagination || {
      page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 1,
    };
  } catch (err) {
    console.error('Detail load failed:', err.message);
    detailData.value = [];
  } finally {
    detailLoading.value = false;
  }
}

async function loadAnalysis() {
  queryError.value = '';
  loading.querying = true;

  try {
    const params = buildFilterParams();

    // Fire summary and detail page 1 in parallel
    const [summaryResult] = await Promise.all([
      apiGet('/api/mid-section-defect/analysis', {
        params,
        timeout: API_TIMEOUT,
      }),
      loadDetail(1),
    ]);

    const unwrapped = unwrapApiResult(summaryResult, '查詢失敗');
    analysisData.value = unwrapped.data;
    hasQueried.value = true;

    // Start auto-refresh after first successful query
    if (!autoRefreshStarted) {
      autoRefreshStarted = true;
      startAutoRefresh();
    }
  } catch (err) {
    queryError.value = err.message || '查詢失敗，請稍後再試';
  } finally {
    loading.querying = false;
  }
}

function handleUpdateFilters(updated) {
  Object.assign(filters, updated);
}

function handleQuery() {
  loadAnalysis();
}

function prevPage() {
  if (detailPagination.value.page <= 1) return;
  loadDetail(detailPagination.value.page - 1);
}

function nextPage() {
  if (detailPagination.value.page >= detailPagination.value.total_pages) return;
  loadDetail(detailPagination.value.page + 1);
}

function exportCsv() {
  const params = new URLSearchParams({
    start_date: filters.startDate,
    end_date: filters.endDate,
  });
  if (filters.lossReasons.length) {
    params.set('loss_reasons', filters.lossReasons.join(','));
  }

  const link = document.createElement('a');
  link.href = `/api/mid-section-defect/export?${params}`;
  link.download = `mid_section_defect_${filters.startDate}_to_${filters.endDate}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

let autoRefreshStarted = false;
const { startAutoRefresh } = useAutoRefresh({
  onRefresh: () => loadAnalysis(),
  intervalMs: 5 * 60 * 1000,
  autoStart: false,
  refreshOnVisible: true,
});

function initPage() {
  setDefaultDates();
  loadLossReasons();
}

void initPage();
</script>

<template>
  <div class="page-container">
    <header class="page-header">
      <h1>中段製程不良追溯分析</h1>
      <p class="header-desc">TMTT 測試站不良回溯至上游機台 / 站點 / 製程</p>
    </header>

    <FilterBar
      :filters="filters"
      :loading="loading.querying"
      :available-loss-reasons="availableLossReasons"
      @update-filters="handleUpdateFilters"
      @query="handleQuery"
    />

    <div v-if="queryError" class="error-banner">{{ queryError }}</div>

    <template v-if="hasQueried">
      <div v-if="analysisData.genealogy_status === 'error'" class="warning-banner">
        追溯分析未完成（genealogy 查詢失敗），圖表僅顯示 TMTT 站點數據。
      </div>

      <KpiCards :kpi="analysisData.kpi" :loading="loading.querying" />

      <div class="charts-section">
        <div class="charts-row">
          <ParetoChart title="依站點歸因" :data="analysisData.charts?.by_station" />
          <ParetoChart title="依不良原因" :data="analysisData.charts?.by_loss_reason" />
        </div>
        <div class="charts-row">
          <ParetoChart title="依上游機台歸因" :data="analysisData.charts?.by_machine" />
          <ParetoChart title="依 TMTT 機台" :data="analysisData.charts?.by_tmtt_machine" />
        </div>
        <div class="charts-row">
          <ParetoChart title="依製程 (WORKFLOW)" :data="analysisData.charts?.by_workflow" />
          <ParetoChart title="依封裝 (PACKAGE)" :data="analysisData.charts?.by_package" />
        </div>
        <div class="charts-row charts-row-full">
          <TrendChart :data="analysisData.daily_trend" />
        </div>
      </div>

      <DetailTable
        :data="detailData"
        :loading="detailLoading"
        :pagination="detailPagination"
        @export-csv="exportCsv"
        @prev-page="prevPage"
        @next-page="nextPage"
      />
    </template>

    <div v-else-if="!loading.querying" class="empty-state">
      <p>請選擇日期範圍與不良原因，點擊「查詢」開始分析。</p>
    </div>

    <div class="loading-overlay" :class="{ hidden: !loading.querying }">
      <div class="loading-spinner"></div>
    </div>
  </div>
</template>
