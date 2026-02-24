<script setup>
import { computed, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { useTraceProgress } from '../shared-composables/useTraceProgress.js';
import TraceProgressBar from '../shared-composables/TraceProgressBar.vue';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import MultiSelect from './components/MultiSelect.vue';
import ParetoChart from './components/ParetoChart.vue';
import TrendChart from './components/TrendChart.vue';
import DetailTable from './components/DetailTable.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 120000;
const PAGE_SIZE = 200;
const SESSION_CACHE_KEY = 'msd:cache';
const SESSION_CACHE_TTL = 5 * 60 * 1000; // 5 min, matches backend Redis TTL
const CHART_TOP_N = 10;

function buildMachineChartFromAttribution(records) {
  if (!records || records.length === 0) return [];
  const agg = {};
  for (const rec of records) {
    const key = rec.EQUIPMENT_NAME || '(未知)';
    if (!agg[key]) agg[key] = { input_qty: 0, defect_qty: 0, lot_count: 0 };
    agg[key].input_qty += rec.INPUT_QTY;
    agg[key].defect_qty += rec.DEFECT_QTY;
    agg[key].lot_count += rec.DETECTION_LOT_COUNT;
  }
  const sorted = Object.entries(agg).sort((a, b) => b[1].defect_qty - a[1].defect_qty);
  const items = [];
  const other = { input_qty: 0, defect_qty: 0, lot_count: 0 };
  for (let i = 0; i < sorted.length; i++) {
    const [name, data] = sorted[i];
    if (i < CHART_TOP_N) {
      const rate = data.input_qty > 0 ? Math.round((data.defect_qty / data.input_qty) * 1e6) / 1e4 : 0;
      items.push({ name, input_qty: data.input_qty, defect_qty: data.defect_qty, defect_rate: rate, lot_count: data.lot_count });
    } else {
      other.input_qty += data.input_qty;
      other.defect_qty += data.defect_qty;
      other.lot_count += data.lot_count;
    }
  }
  if (other.defect_qty > 0 || other.input_qty > 0) {
    const rate = other.input_qty > 0 ? Math.round((other.defect_qty / other.input_qty) * 1e6) / 1e4 : 0;
    items.push({ name: '其他', ...other, defect_rate: rate });
  }
  const totalDefects = items.reduce((s, d) => s + d.defect_qty, 0);
  let cumsum = 0;
  for (const item of items) {
    cumsum += item.defect_qty;
    item.cumulative_pct = totalDefects > 0 ? Math.round((cumsum / totalDefects) * 1e4) / 100 : 0;
  }
  return items;
}

const stationOptions = ref([]);
(async () => {
  try {
    const result = await apiGet('/api/mid-section-defect/station-options');
    if (result?.success && Array.isArray(result.data)) {
      stationOptions.value = result.data;
    }
  } catch { /* non-blocking */ }
})();
const stationLabelMap = computed(() => {
  const m = {};
  for (const opt of stationOptions.value) {
    m[opt.name] = opt.label || opt.name;
  }
  return m;
});

const filters = reactive({
  startDate: '',
  endDate: '',
  lossReasons: [],
  station: '測試',
  direction: 'backward',
});
const committedFilters = ref({
  startDate: '',
  endDate: '',
  lossReasons: [],
  station: '測試',
  direction: 'backward',
});

const queryMode = ref('date_range');
const containerInputType = ref('lot');
const containerInput = ref('');
const resolutionInfo = ref(null);

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
const restoredFromCache = ref(false);

const upstreamStationFilter = ref([]);
const upstreamSpecFilter = ref([]);
const upstreamStationOptions = computed(() => {
  const attribution = analysisData.value?.attribution;
  if (!Array.isArray(attribution) || attribution.length === 0) return [];
  const seen = new Set();
  const options = [];
  for (const rec of attribution) {
    const group = rec.WORKCENTER_GROUP;
    if (group && !seen.has(group)) {
      seen.add(group);
      options.push({ value: group, label: stationLabelMap.value[group] || group });
    }
  }
  return options.sort((a, b) => a.label.localeCompare(b.label, 'zh-TW'));
});
const upstreamSpecOptions = computed(() => {
  const attribution = analysisData.value?.attribution;
  if (!Array.isArray(attribution) || attribution.length === 0) return [];
  // Apply station filter first so spec options are contextual
  const base = upstreamStationFilter.value.length > 0
    ? attribution.filter(rec => upstreamStationFilter.value.includes(rec.WORKCENTER_GROUP))
    : attribution;
  const seen = new Set();
  const options = [];
  for (const rec of base) {
    const family = rec.RESOURCEFAMILYNAME;
    if (family && family !== '(未知)' && !seen.has(family)) {
      seen.add(family);
      options.push(family);
    }
  }
  return options.sort((a, b) => a.localeCompare(b, 'zh-TW'));
});
const filteredByMachineData = computed(() => {
  const attribution = analysisData.value?.attribution;
  const hasFilter = upstreamStationFilter.value.length > 0 || upstreamSpecFilter.value.length > 0;
  if (!hasFilter || !Array.isArray(attribution) || attribution.length === 0) {
    return analysisData.value?.charts?.by_machine ?? [];
  }
  const filtered = attribution.filter(rec => {
    if (upstreamStationFilter.value.length > 0 && !upstreamStationFilter.value.includes(rec.WORKCENTER_GROUP)) return false;
    if (upstreamSpecFilter.value.length > 0 && !upstreamSpecFilter.value.includes(rec.RESOURCEFAMILYNAME)) return false;
    return true;
  });
  return filtered.length > 0 ? buildMachineChartFromAttribution(filtered) : [];
});

const isForward = computed(() => committedFilters.value.direction === 'forward');
const committedStation = computed(() => {
  const key = committedFilters.value.station || '測試';
  return stationLabelMap.value[key] || key;
});

const headerSubtitle = computed(() => {
  const station = committedStation.value;
  if (isForward.value) {
    return `${station}站不良批次 → 追蹤倖存批次下游表現`;
  }
  return `${station}站不良 → 回溯上游機台歸因`;
});

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
const showAnalysisCharts = computed(() => hasQueried.value && (Boolean(eventsAggregation.value) || restoredFromCache.value));

const skeletonChartCount = computed(() => (isForward.value ? 4 : 6));

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
    station: snapshot.station,
    direction: snapshot.direction,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons;
  }
  if (snapshot.queryMode === 'container') {
    params.mode = 'container';
    params.resolve_type = snapshot.containerInputType === 'lot' ? 'lot_id' : snapshot.containerInputType;
    params.values = snapshot.containerValues;
  } else {
    params.start_date = snapshot.startDate;
    params.end_date = snapshot.endDate;
  }
  return params;
}

function buildDetailParams() {
  const snapshot = committedFilters.value;
  const params = {
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
    station: snapshot.station,
    direction: snapshot.direction,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons.join(',');
  }
  return params;
}

function parseContainerValues() {
  return containerInput.value
    .split(/[\n,;]+/)
    .map((v) => v.trim().replace(/\*/g, '%'))
    .filter(Boolean);
}

function snapshotFilters() {
  committedFilters.value = {
    startDate: filters.startDate,
    endDate: filters.endDate,
    lossReasons: [...filters.lossReasons],
    station: filters.station,
    direction: filters.direction,
    queryMode: queryMode.value,
    containerInputType: containerInputType.value,
    containerValues: parseContainerValues(),
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
  restoredFromCache.value = false;
  resolutionInfo.value = null;
  upstreamStationFilter.value = [];
  upstreamSpecFilter.value = [];
  trace.abort();
  trace.reset();
  loading.querying = true;
  hasQueried.value = true;
  analysisData.value = emptyAnalysisData();

  const isContainerMode = committedFilters.value.queryMode === 'container';

  try {
    const params = buildFilterParams();
    await trace.execute(params);

    // Extract resolution info for container mode
    if (isContainerMode && trace.stage_results.seed) {
      resolutionInfo.value = {
        resolved_count: trace.stage_results.seed.seed_count || 0,
        not_found: trace.stage_results.seed.not_found || [],
      };
    }

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
      // Container mode: no detail/export (no date range for legacy API)
      if (!isContainerMode) {
        await loadDetail(1, createAbortSignal('msd-detail'));
      }
      saveSession();
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
    station: snapshot.station,
    direction: snapshot.direction,
  });
  if (snapshot.lossReasons.length) {
    params.set('loss_reasons', snapshot.lossReasons.join(','));
  }

  const link = document.createElement('a');
  link.href = `/api/mid-section-defect/export?${params.toString()}`;
  link.download = `mid_section_defect_${snapshot.station}_${snapshot.direction}_${snapshot.startDate}_to_${snapshot.endDate}.csv`;
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

function saveSession() {
  try {
    sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify({
      ts: Date.now(),
      committedFilters: committedFilters.value,
      filters: { ...filters },
      analysisData: analysisData.value,
      detailData: detailData.value,
      detailPagination: detailPagination.value,
      availableLossReasons: availableLossReasons.value,
      queryMode: queryMode.value,
      containerInputType: containerInputType.value,
      containerInput: containerInput.value,
      resolutionInfo: resolutionInfo.value,
    }));
  } catch { /* quota exceeded or unavailable */ }
}

function restoreSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) return false;
    const data = JSON.parse(raw);
    if (Date.now() - data.ts > SESSION_CACHE_TTL) {
      sessionStorage.removeItem(SESSION_CACHE_KEY);
      return false;
    }
    Object.assign(filters, data.filters);
    committedFilters.value = data.committedFilters;
    analysisData.value = data.analysisData;
    detailData.value = data.detailData || [];
    detailPagination.value = data.detailPagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 1 };
    availableLossReasons.value = data.availableLossReasons || [];
    queryMode.value = data.queryMode || 'date_range';
    containerInputType.value = data.containerInputType || 'lot';
    containerInput.value = data.containerInput || '';
    resolutionInfo.value = data.resolutionInfo || null;
    hasQueried.value = true;
    restoredFromCache.value = true;
    return true;
  } catch {
    return false;
  }
}

function initPage() {
  if (restoreSession()) return;
  setDefaultDates();
  snapshotFilters();
  void loadLossReasons();
}

void initPage();
</script>

<template>
  <div class="page-container">
    <header class="page-header">
      <h1>製程不良追溯分析</h1>
      <p class="header-desc">{{ headerSubtitle }}</p>
    </header>

    <FilterBar
      :filters="filters"
      :loading="loading.querying"
      :available-loss-reasons="availableLossReasons"
      :station-options="stationOptions"
      :query-mode="queryMode"
      :container-input-type="containerInputType"
      :container-input="containerInput"
      :resolution-info="resolutionInfo"
      @update-filters="handleUpdateFilters"
      @query="handleQuery"
      @update:query-mode="queryMode = $event"
      @update:container-input-type="containerInputType = $event"
      @update:container-input="containerInput = $event"
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
        追溯分析未完成（genealogy 查詢失敗），圖表僅顯示偵測站數據。
      </div>

      <div v-if="showAnalysisSkeleton" class="trace-skeleton-section">
        <div class="trace-skeleton-kpi-grid">
          <div v-for="index in 6" :key="`kpi-${index}`" class="trace-skeleton-card trace-skeleton-pulse"></div>
        </div>
        <div class="trace-skeleton-chart-grid">
          <div v-for="index in skeletonChartCount" :key="`chart-${index}`" class="trace-skeleton-chart trace-skeleton-pulse"></div>
          <div class="trace-skeleton-chart trace-skeleton-trend trace-skeleton-pulse"></div>
        </div>
      </div>

      <transition name="trace-fade">
        <div v-if="showAnalysisCharts">
          <KpiCards
            :kpi="analysisData.kpi"
            :loading="false"
            :direction="committedFilters.direction"
            :station-label="committedStation"
          />

          <div class="charts-section">
            <template v-if="!isForward">
              <div class="charts-row">
                <ParetoChart title="依上游機台歸因" :data="filteredByMachineData">
                  <template #header-extra>
                    <div class="chart-inline-filters">
                      <MultiSelect
                        v-if="upstreamStationOptions.length > 1"
                        :model-value="upstreamStationFilter"
                        :options="upstreamStationOptions"
                        placeholder="全部站點"
                        @update:model-value="upstreamStationFilter = $event; upstreamSpecFilter = []"
                      />
                      <MultiSelect
                        v-if="upstreamSpecOptions.length > 1"
                        :model-value="upstreamSpecFilter"
                        :options="upstreamSpecOptions"
                        placeholder="全部型號"
                        @update:model-value="upstreamSpecFilter = $event"
                      />
                    </div>
                  </template>
                </ParetoChart>
                <ParetoChart title="依不良原因" :data="analysisData.charts?.by_loss_reason" />
              </div>
              <div class="charts-row">
                <ParetoChart title="依偵測機台" :data="analysisData.charts?.by_detection_machine" />
                <ParetoChart title="依製程 (WORKFLOW)" :data="analysisData.charts?.by_workflow" />
              </div>
              <div class="charts-row">
                <ParetoChart title="依封裝 (PACKAGE)" :data="analysisData.charts?.by_package" />
                <ParetoChart title="依 TYPE" :data="analysisData.charts?.by_pj_type" />
              </div>
            </template>
            <template v-else>
              <div class="charts-row">
                <ParetoChart title="依下游站點" :data="analysisData.charts?.by_downstream_station" />
                <ParetoChart title="依下游不良原因" :data="analysisData.charts?.by_downstream_loss_reason" />
              </div>
              <div class="charts-row">
                <ParetoChart title="依下游機台" :data="analysisData.charts?.by_downstream_machine" />
                <ParetoChart title="依偵測機台" :data="analysisData.charts?.by_detection_machine" />
              </div>
            </template>
            <div v-if="committedFilters.queryMode !== 'container'" class="charts-row charts-row-full">
              <TrendChart :data="analysisData.daily_trend" />
            </div>
          </div>
        </div>
      </transition>

      <DetailTable
        v-if="committedFilters.queryMode !== 'container'"
        :data="detailData"
        :loading="detailLoading"
        :pagination="detailPagination"
        :direction="committedFilters.direction"
        @export-csv="exportCsv"
        @prev-page="prevPage"
        @next-page="nextPage"
      />
    </template>

    <div v-else-if="!loading.querying" class="empty-state">
      <p>請選擇偵測站與查詢條件，點擊「查詢」開始分析。</p>
    </div>
  </div>
</template>
