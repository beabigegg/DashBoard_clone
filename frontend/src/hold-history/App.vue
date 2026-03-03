<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';

import DailyTrend from './components/DailyTrend.vue';
import DetailTable from './components/DetailTable.vue';
import DurationChart from './components/DurationChart.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import RecordTypeFilter from './components/RecordTypeFilter.vue';
import ReasonPareto from './components/ReasonPareto.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 50;

const filterBar = reactive({
  startDate: '',
  endDate: '',
  holdType: 'quality',
});

const queryId = ref('');
const reasonFilter = ref('');
const durationFilter = ref('');
const recordType = ref(['new']);

const trendData = ref({ days: [] });
const reasonParetoData = ref({ items: [] });
const durationData = ref({ items: [] });
const detailData = ref({
  items: [],
  pagination: {
    page: 1,
    perPage: DEFAULT_PER_PAGE,
    total: 0,
    totalPages: 1,
  },
});

const page = ref(1);
const initialLoading = ref(true);
const loading = reactive({
  global: false,
  list: false,
});

const errorMessage = ref('');
let activeRequestId = 0;

function toDateString(value) {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function getUrlParam(name) {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function normalizeHoldType(value) {
  const holdType = String(value || '').trim();
  if (holdType === 'quality' || holdType === 'non-quality' || holdType === 'all') {
    return holdType;
  }
  return 'quality';
}

function parseRecordTypeCsv(value) {
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length > 0 ? [...new Set(parsed)] : ['new'];
}

function setDefaultDateRange() {
  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth();

  if (now.getDate() === 1) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
  }

  const start = new Date(year, month, 1);
  const end = new Date(year, month + 1, 0);
  filterBar.startDate = toDateString(start);
  filterBar.endDate = toDateString(end);
}

function nextRequestId() {
  activeRequestId += 1;
  return activeRequestId;
}

function isStaleRequest(requestId) {
  return requestId !== activeRequestId;
}

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success) {
    return result.data;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  if (result?.data !== undefined) {
    return result.data;
  }
  return result;
}

function normalizeListPayload(payload) {
  const pagination = payload?.pagination || {};
  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    pagination: {
      page: Number(pagination.page || page.value || 1),
      perPage: Number(pagination.perPage || DEFAULT_PER_PAGE),
      total: Number(pagination.total || 0),
      totalPages: Number(pagination.totalPages || 1),
    },
  };
}

function updateUrlState() {
  const params = new URLSearchParams();

  if (filterBar.startDate) {
    params.set('start_date', filterBar.startDate);
  }
  if (filterBar.endDate) {
    params.set('end_date', filterBar.endDate);
  }
  if (filterBar.holdType) {
    params.set('hold_type', filterBar.holdType);
  }
  if (Array.isArray(recordType.value) && recordType.value.length > 0) {
    params.set('record_type', recordType.value.join(','));
  }
  if (reasonFilter.value) {
    params.set('reason', reasonFilter.value);
  }
  if (durationFilter.value) {
    params.set('duration_range', durationFilter.value);
  }
  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/hold-history?${params.toString()}`);
}

function recordTypeCsv() {
  const rt = Array.isArray(recordType.value) ? recordType.value : [recordType.value];
  return rt.join(',');
}

function applyViewResult(result, { listOnly = false } = {}) {
  if (!listOnly) {
    trendData.value = result.trend || trendData.value;
    reasonParetoData.value = result.reason_pareto || reasonParetoData.value;
    durationData.value = result.duration || durationData.value;
  }
  detailData.value = normalizeListPayload(result.list);
}

// ---- Primary query (POST /query -> Oracle -> cache) ----

async function executePrimaryQuery({ showOverlay = false } = {}) {
  const requestId = nextRequestId();

  if (showOverlay) {
    initialLoading.value = true;
  }

  loading.global = true;
  loading.list = true;
  errorMessage.value = '';

  try {
    const body = {
      start_date: filterBar.startDate,
      end_date: filterBar.endDate,
      hold_type: filterBar.holdType,
      record_type: recordTypeCsv(),
    };

    const resp = await apiPost('/api/hold-history/query', body, { timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    const result = unwrapApiResult(resp, '主查詢執行失敗');

    queryId.value = result.query_id;
    applyViewResult(result);

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
    loading.global = false;
    loading.list = false;
    initialLoading.value = false;
  }
}

// ---- View refresh (GET /view -> read cache -> filter) ----

async function refreshView({ listOnly = false } = {}) {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  if (!listOnly) {
    loading.global = true;
  }
  loading.list = true;
  errorMessage.value = '';

  try {
    const params = {
      query_id: queryId.value,
      hold_type: filterBar.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };

    if (reasonFilter.value) {
      params.reason = reasonFilter.value;
    }
    if (durationFilter.value) {
      params.duration_range = durationFilter.value;
    }

    const resp = await apiGet('/api/hold-history/view', {
      params,
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    // Cache expired -> auto re-execute primary query
    if (resp?.success === false && resp?.error === 'cache_expired') {
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '視圖查詢失敗');
    applyViewResult(result, { listOnly });
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.global = false;
    loading.list = false;
  }
}

// ---- Computed ----

function estimateAvgHoldHours(items) {
  const bucketHours = {
    '<4h': 2,
    '4-24h': 14,
    '1-3d': 48,
    '>3d': 96,
  };

  let weightedHours = 0;
  let totalCount = 0;

  (items || []).forEach((item) => {
    const count = Number(item?.count || 0);
    const range = String(item?.range || '').trim();
    const representative = Number(bucketHours[range] || 0);
    weightedHours += count * representative;
    totalCount += count;
  });

  if (totalCount <= 0) {
    return 0;
  }

  return weightedHours / totalCount;
}

const trendTypeKey = computed(() => (filterBar.holdType === 'non-quality' ? 'non_quality' : filterBar.holdType));

const selectedTrendDays = computed(() => {
  const days = Array.isArray(trendData.value?.days) ? trendData.value.days : [];
  return days.map((day) => {
    const section = day?.[trendTypeKey.value] || {};
    return {
      date: day?.date || '',
      holdQty: Number(section.holdQty || 0),
      newHoldQty: Number(section.newHoldQty || 0),
      releaseQty: Number(section.releaseQty || 0),
      futureHoldQty: Number(section.futureHoldQty || 0),
    };
  });
});

const summary = computed(() => {
  const days = selectedTrendDays.value;

  const releaseQty = days.reduce((total, item) => total + Number(item.releaseQty || 0), 0);
  const newHoldQty = days.reduce((total, item) => total + Number(item.newHoldQty || 0), 0);
  const futureHoldQty = days.reduce((total, item) => total + Number(item.futureHoldQty || 0), 0);
  const netChange = releaseQty - newHoldQty - futureHoldQty;
  const avgHoldHours = estimateAvgHoldHours(durationData.value?.items || []);

  const today = new Date().toISOString().slice(0, 10);
  const pastDays = days.filter((d) => d.date <= today);
  const lastDay = pastDays.length > 0 ? pastDays[pastDays.length - 1] : {};
  const stillOnHoldCount = Number(lastDay.holdQty || 0);
  const newHoldSnapshotCount = Number(lastDay.newHoldQty || 0);

  return {
    releaseQty,
    newHoldQty,
    futureHoldQty,
    stillOnHoldCount,
    newHoldSnapshotCount,
    netChange,
    avgHoldHours,
  };
});

const holdTypeLabel = computed(() => {
  if (filterBar.holdType === 'non-quality') {
    return '非品質異常';
  }
  if (filterBar.holdType === 'all') {
    return '全部';
  }
  return '品質異常';
});

// ---- Event handlers ----

function handleApply(next) {
  const nextStartDate = next?.startDate || '';
  const nextEndDate = next?.endDate || '';

  filterBar.startDate = nextStartDate;
  filterBar.endDate = nextEndDate;
  reasonFilter.value = '';
  durationFilter.value = '';
  recordType.value = ['new'];
  page.value = 1;
  updateUrlState();

  void executePrimaryQuery();
}

function handleHoldTypeChange(nextHoldType) {
  const holdType = nextHoldType || 'quality';
  if (filterBar.holdType === holdType) return;

  filterBar.holdType = holdType;
  reasonFilter.value = '';
  durationFilter.value = '';
  recordType.value = ['new'];
  page.value = 1;
  updateUrlState();

  // Hold type only → view refresh (cache read, no Oracle query)
  void refreshView();
}

function handleRecordTypeChange() {
  reasonFilter.value = '';
  durationFilter.value = '';
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function handleReasonToggle(reason) {
  const nextReason = String(reason || '').trim();
  if (!nextReason) {
    return;
  }

  reasonFilter.value = reasonFilter.value === nextReason ? '' : nextReason;
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function clearReasonFilter() {
  if (!reasonFilter.value) {
    return;
  }
  reasonFilter.value = '';
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function handleDurationToggle(range) {
  const nextRange = String(range || '').trim();
  if (!nextRange) {
    return;
  }

  durationFilter.value = durationFilter.value === nextRange ? '' : nextRange;
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function clearDurationFilter() {
  if (!durationFilter.value) {
    return;
  }
  durationFilter.value = '';
  page.value = 1;
  updateUrlState();
  void refreshView();
}

function prevPage() {
  if (page.value <= 1) {
    return;
  }
  page.value -= 1;
  updateUrlState();
  void refreshView({ listOnly: true });
}

function nextPage() {
  const totalPages = Number(detailData.value?.pagination?.totalPages || 1);
  if (page.value >= totalPages) {
    return;
  }
  page.value += 1;
  updateUrlState();
  void refreshView({ listOnly: true });
}

async function manualRefresh() {
  page.value = 1;
  reasonFilter.value = '';
  durationFilter.value = '';
  updateUrlState();
  await executePrimaryQuery();
}

onMounted(() => {
  const startDate = getUrlParam('start_date');
  const endDate = getUrlParam('end_date');
  if (startDate && endDate) {
    filterBar.startDate = startDate;
    filterBar.endDate = endDate;
  } else {
    setDefaultDateRange();
  }
  filterBar.holdType = normalizeHoldType(getUrlParam('hold_type'));
  reasonFilter.value = getUrlParam('reason');
  durationFilter.value = getUrlParam('duration_range');
  recordType.value = parseRecordTypeCsv(getUrlParam('record_type'));
  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }
  updateUrlState();
  void executePrimaryQuery({ showOverlay: true });
});
</script>

<template>
  <div class="dashboard hold-history-page">
    <header class="header hold-history-header">
      <div class="header-left">
        <h1>Hold 歷史績效</h1>
        <span class="hold-type-badge">{{ holdTypeLabel }}</span>
      </div>
      <div class="header-right">
        <button type="button" class="btn btn-light" @click="manualRefresh">重新整理</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <FilterBar
      :start-date="filterBar.startDate"
      :end-date="filterBar.endDate"
      :hold-type="filterBar.holdType"
      :disabled="loading.global"
      @apply="handleApply"
      @hold-type-change="handleHoldTypeChange"
    />

    <SummaryCards :summary="summary" />

    <DailyTrend :days="selectedTrendDays" />

    <RecordTypeFilter
      v-model="recordType"
      :disabled="loading.global"
      @update:model-value="handleRecordTypeChange"
    />

    <section class="hold-history-chart-grid">
      <ReasonPareto
        :items="reasonParetoData.items || []"
        :active-reason="reasonFilter"
        @toggle="handleReasonToggle"
      />
      <DurationChart
        :items="durationData.items || []"
        :active-range="durationFilter"
        @toggle="handleDurationToggle"
      />
    </section>

    <FilterIndicator
      :reason="reasonFilter"
      :duration-range="durationFilter"
      @clear-reason="clearReasonFilter"
      @clear-duration="clearDurationFilter"
    />

    <DetailTable
      :items="detailData.items || []"
      :pagination="detailData.pagination"
      :loading="loading.list"
      :error-message="errorMessage"
      @prev-page="prevPage"
      @next-page="nextPage"
    />
  </div>

  <div v-if="initialLoading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
