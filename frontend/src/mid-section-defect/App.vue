<script setup>
import { computed, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { useTraceProgress } from '../shared-composables/useTraceProgress.js';
import TraceProgressBar from '../shared-composables/TraceProgressBar.vue';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import ParetoChart from './components/ParetoChart.vue';
import TrendChart from './components/TrendChart.vue';
import DetailTable from './components/DetailTable.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 120000;
const PAGE_SIZE = 200;

const filters = reactive({
  startDate: '',
  endDate: '',
  lossReasons: [],
});
const committedFilters = ref({
  startDate: '',
  endDate: '',
  lossReasons: [],
});

const availableLossReasons = ref([]);
const trace = useTraceProgress({ profile: 'mid_section_defect' });

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
  querying: false,
});

const hasQueried = ref(false);
const queryError = ref('');

const hasTraceError = computed(() => (
  Boolean(trace.stage_errors.seed)
  || Boolean(trace.stage_errors.lineage)
  || Boolean(trace.stage_errors.events)
));
const showTraceProgress = computed(() => (
  loading.querying
  || trace.completed_stages.value.length > 0
  || hasTraceError.value
));
const eventsAggregation = computed(() => trace.stage_results.events?.aggregation || null);
const showAnalysisSkeleton = computed(() => hasQueried.value && loading.querying && !eventsAggregation.value);
const showAnalysisCharts = computed(() => hasQueried.value && Boolean(eventsAggregation.value));

function emptyAnalysisData() {
  return {
    kpi: {},
    charts: {},
    daily_trend: [],
    genealogy_status: 'ready',
    detail_total_count: 0,
  };
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
  throw new Error(result?.error || fallbackMessage);
}

function buildFilterParams() {
  const snapshot = committedFilters.value;
  const params = {
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons;
  }
  return params;
}

function buildDetailParams() {
  const snapshot = committedFilters.value;
  const params = {
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons.join(',');
  }
  return params;
}

function snapshotFilters() {
  committedFilters.value = {
    startDate: filters.startDate,
    endDate: filters.endDate,
    lossReasons: [...filters.lossReasons],
  };
}

function firstStageErrorMessage() {
  const stageError = trace.stage_errors.seed || trace.stage_errors.lineage || trace.stage_errors.events;
  return stageError?.message || '';
}

async function loadLossReasons() {
  try {
    const result = await apiGet('/api/mid-section-defect/loss-reasons');
    const unwrapped = unwrapApiResult(result, '載入不良原因失敗');
    availableLossReasons.value = unwrapped.data?.loss_reasons || [];
  } catch {
    // Non-blocking, dropdown remains empty.
  }
}

async function loadDetail(page = 1, signal = null) {
  detailLoading.value = true;
  try {
    const params = {
      ...buildDetailParams(),
      page,
      page_size: PAGE_SIZE,
    };
    const result = await apiGet('/api/mid-section-defect/analysis/detail', {
      params,
      timeout: API_TIMEOUT,
      signal,
    });
    const unwrapped = unwrapApiResult(result, '載入明細失敗');
    detailData.value = unwrapped.data?.detail || [];
    detailPagination.value = unwrapped.data?.pagination || {
      page: 1,
      page_size: PAGE_SIZE,
      total_count: 0,
      total_pages: 1,
    };
  } catch (err) {
    if (err?.name === 'AbortError') {
      return;
    }
    console.error('Detail load failed:', err.message);
    detailData.value = [];
  } finally {
    detailLoading.value = false;
  }
}

async function loadAnalysis() {
  queryError.value = '';
  trace.abort();
  trace.reset();
  loading.querying = true;
  hasQueried.value = true;
  analysisData.value = emptyAnalysisData();

  try {
    const params = buildFilterParams();
    await trace.execute(params);

    if (eventsAggregation.value) {
      analysisData.value = {
        ...analysisData.value,
        ...eventsAggregation.value,
      };
    }

    const stageError = firstStageErrorMessage();
    if (stageError) {
      queryError.value = stageError;
    }

    if (!stageError || trace.completed_stages.value.includes('events')) {
      await loadDetail(1, createAbortSignal('msd-detail'));
    }

    if (!autoRefreshStarted) {
      autoRefreshStarted = true;
      startAutoRefresh();
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      return;
    }
    queryError.value = err.message || '查詢失敗，請稍後再試';
  } finally {
    loading.querying = false;
  }
}

function handleUpdateFilters(updated) {
  Object.assign(filters, updated);
}

function handleQuery() {
  snapshotFilters();
  void loadAnalysis();
}

function prevPage() {
  if (detailPagination.value.page <= 1) return;
  void loadDetail(detailPagination.value.page - 1, createAbortSignal('msd-detail'));
}

function nextPage() {
  if (detailPagination.value.page >= detailPagination.value.total_pages) return;
  void loadDetail(detailPagination.value.page + 1, createAbortSignal('msd-detail'));
}

function exportCsv() {
  const snapshot = committedFilters.value;
  const params = new URLSearchParams({
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
  });
  if (snapshot.lossReasons.length) {
    params.set('loss_reasons', snapshot.lossReasons.join(','));
  }

  const link = document.createElement('a');
  link.href = `/api/mid-section-defect/export?${params.toString()}`;
  link.download = `mid_section_defect_${snapshot.startDate}_to_${snapshot.endDate}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

let autoRefreshStarted = false;
const { createAbortSignal, startAutoRefresh } = useAutoRefresh({
  onRefresh: async () => {
    trace.abort();
    await loadAnalysis();
  },
  intervalMs: 5 * 60 * 1000,
  autoStart: false,
  refreshOnVisible: true,
});

function initPage() {
  setDefaultDates();
  snapshotFilters();
  void loadLossReasons();
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

    <TraceProgressBar
      v-if="showTraceProgress"
      :current_stage="trace.current_stage.value"
      :completed_stages="trace.completed_stages.value"
      :stage_errors="trace.stage_errors"
    />

    <div v-if="queryError" class="error-banner">{{ queryError }}</div>

    <template v-if="hasQueried">
      <div v-if="analysisData.genealogy_status === 'error'" class="warning-banner">
        追溯分析未完成（genealogy 查詢失敗），圖表僅顯示 TMTT 站點數據。
      </div>

      <div v-if="showAnalysisSkeleton" class="trace-skeleton-section">
        <div class="trace-skeleton-kpi-grid">
          <div v-for="index in 6" :key="`kpi-${index}`" class="trace-skeleton-card trace-skeleton-pulse"></div>
        </div>
        <div class="trace-skeleton-chart-grid">
          <div v-for="index in 6" :key="`chart-${index}`" class="trace-skeleton-chart trace-skeleton-pulse"></div>
          <div class="trace-skeleton-chart trace-skeleton-trend trace-skeleton-pulse"></div>
        </div>
      </div>

      <transition name="trace-fade">
        <div v-if="showAnalysisCharts">
          <KpiCards :kpi="analysisData.kpi" :loading="false" />

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
        </div>
      </transition>

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
  </div>
</template>
