<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';

import SummaryCards from '../hold-detail/components/SummaryCards.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import HoldMatrix from './components/HoldMatrix.vue';
import LotTable from './components/LotTable.vue';

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 50;

const summary = ref(null);
const matrix = ref(null);
const lots = ref([]);

const filterBar = reactive({
  holdType: 'quality',
  reason: '',
});

const matrixFilter = ref(null);

const pagination = ref({
  page: 1,
  perPage: DEFAULT_PER_PAGE,
  total: 0,
  totalPages: 1,
});
const page = ref(1);

const initialLoading = ref(true);
const lotsLoading = ref(false);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
const lotsError = ref('');

let activeRequestId = 0;

const holdTypeLabel = computed(() => {
  if (filterBar.holdType === 'non-quality') {
    return '非品質異常';
  }
  if (filterBar.holdType === 'all') {
    return '全部';
  }
  return '品質異常';
});

const hasCascadeFilters = computed(() => Boolean(matrixFilter.value));

const lotFilterText = computed(() => {
  const parts = [];
  if (matrixFilter.value?.workcenter) {
    parts.push(`Workcenter=${matrixFilter.value.workcenter}`);
  }
  if (matrixFilter.value?.package) {
    parts.push(`Package=${matrixFilter.value.package}`);
  }
  return parts.join(', ');
});

const hasLotFilterText = computed(() => Boolean(lotFilterText.value));

const lastUpdate = computed(() => {
  const value = summary.value?.dataUpdateDate;
  return value ? `Last Update: ${value}` : '';
});

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

function buildFilterBarParams() {
  const params = {
    hold_type: filterBar.holdType || 'quality',
  };
  if (filterBar.reason) {
    params.reason = filterBar.reason;
  }
  return params;
}

function buildMatrixFilterParams() {
  const params = {};
  if (matrixFilter.value?.workcenter) {
    params.workcenter = matrixFilter.value.workcenter;
  }
  if (matrixFilter.value?.package) {
    params.package = matrixFilter.value.package;
  }
  return params;
}

function buildLotsParams() {
  return {
    ...buildFilterBarParams(),
    ...buildMatrixFilterParams(),
    page: page.value,
    per_page: Number(pagination.value?.perPage || DEFAULT_PER_PAGE),
  };
}

async function fetchSummary(signal) {
  const result = await apiGet('/api/hold-overview/summary', {
    params: buildFilterBarParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold summary');
}

async function fetchMatrix(signal) {
  const result = await apiGet('/api/hold-overview/matrix', {
    params: buildFilterBarParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold matrix');
}

async function fetchLots(signal) {
  const result = await apiGet('/api/hold-overview/lots', {
    params: buildLotsParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold lots');
}

function updateLotsState(payload) {
  lots.value = Array.isArray(payload?.lots) ? payload.lots : [];
  pagination.value = {
    page: Number(payload?.pagination?.page || page.value || 1),
    perPage: Number(payload?.pagination?.perPage || DEFAULT_PER_PAGE),
    total: Number(payload?.pagination?.total || 0),
    totalPages: Number(payload?.pagination?.totalPages || 1),
  };
  page.value = pagination.value.page;
}

function showRefreshSuccess() {
  refreshSuccess.value = true;
  window.setTimeout(() => {
    refreshSuccess.value = false;
  }, 1500);
}

const { createAbortSignal, clearAbortController, triggerRefresh } = useAutoRefresh({
  onRefresh: () => loadAllData(false),
  autoStart: true,
});

async function loadAllData(showOverlay = true) {
  const requestId = nextRequestId();
  clearAbortController('hold-overview-lots');
  const signal = createAbortSignal('hold-overview-all');

  if (showOverlay) {
    initialLoading.value = true;
  }
  lotsLoading.value = true;
  refreshing.value = true;
  refreshError.value = false;
  errorMessage.value = '';
  lotsError.value = '';

  try {
    const [summaryData, matrixData, lotsData] = await Promise.all([
      fetchSummary(signal),
      fetchMatrix(signal),
      fetchLots(signal),
    ]);
    if (isStaleRequest(requestId)) {
      return;
    }

    summary.value = summaryData;
    matrix.value = matrixData;
    updateLotsState(lotsData);
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    refreshError.value = true;
    const message = error?.message || '載入資料失敗';
    errorMessage.value = message;
    lotsError.value = message;
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    refreshing.value = false;
    lotsLoading.value = false;
    initialLoading.value = false;
  }
}

async function loadLots() {
  const requestId = nextRequestId();
  clearAbortController('hold-overview-all');
  const signal = createAbortSignal('hold-overview-lots');

  refreshing.value = true;
  lotsLoading.value = true;
  refreshError.value = false;
  errorMessage.value = '';
  lotsError.value = '';

  try {
    const lotsData = await fetchLots(signal);
    if (isStaleRequest(requestId)) {
      return;
    }
    updateLotsState(lotsData);
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    refreshError.value = true;
    const message = error?.message || '載入 Lot 資料失敗';
    errorMessage.value = message;
    lotsError.value = message;
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    refreshing.value = false;
    lotsLoading.value = false;
  }
}

function handleFilterChange(next) {
  const nextHoldType = next?.holdType || 'quality';
  const nextReason = next?.reason || '';
  if (filterBar.holdType === nextHoldType && filterBar.reason === nextReason) {
    return;
  }

  filterBar.holdType = nextHoldType;
  filterBar.reason = nextReason;
  matrixFilter.value = null;
  page.value = 1;
  void loadAllData(false);
}

function handleMatrixSelect(nextFilter) {
  matrixFilter.value = nextFilter;
  page.value = 1;
  void loadLots();
}

function clearMatrixFilter() {
  if (!matrixFilter.value) {
    return;
  }
  matrixFilter.value = null;
  page.value = 1;
  void loadLots();
}

function prevPage() {
  if (page.value <= 1) {
    return;
  }
  page.value -= 1;
  void loadLots();
}

function nextPage() {
  if (page.value >= Number(pagination.value?.totalPages || 1)) {
    return;
  }
  page.value += 1;
  void loadLots();
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

onMounted(() => {
  void loadAllData(true);
});
</script>

<template>
  <div class="dashboard hold-overview-page">
    <header class="header">
      <div class="header-left">
        <h1>Hold Lot Overview</h1>
        <span class="hold-type-badge">{{ holdTypeLabel }}</span>
      </div>
      <div class="header-right">
        <span class="last-update">
          <span class="refresh-indicator" :class="{ active: refreshing }"></span>
          <span class="refresh-success" :class="{ active: refreshSuccess }">&#10003;</span>
          <span class="refresh-error" :class="{ active: refreshError }"></span>
          <span>{{ lastUpdate }}</span>
        </span>
        <button type="button" class="btn btn-light" @click="manualRefresh">重新整理</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <FilterBar
      :hold-type="filterBar.holdType"
      :reason="filterBar.reason"
      :reasons="reasonOptions"
      :disabled="refreshing && initialLoading"
      @change="handleFilterChange"
    />

    <SummaryCards :summary="summary" />

    <section class="card">
      <div class="card-header">
        <div class="card-title">Workcenter x Package Matrix (QTY)</div>
      </div>
      <div class="card-body matrix-container">
        <HoldMatrix :data="matrix" :active-filter="matrixFilter" @select="handleMatrixSelect" />
      </div>
    </section>

    <FilterIndicator
      :matrix-filter="matrixFilter"
      :show-clear-all="true"
      @clear-matrix="clearMatrixFilter"
      @clear-all="clearMatrixFilter"
    />

    <LotTable
      :lots="lots"
      :pagination="pagination"
      :loading="lotsLoading"
      :error-message="lotsError"
      :has-active-filters="hasLotFilterText"
      :filter-text="lotFilterText"
      @clear-filters="clearMatrixFilter"
      @prev-page="prevPage"
      @next-page="nextPage"
    />
  </div>

  <div v-if="initialLoading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
