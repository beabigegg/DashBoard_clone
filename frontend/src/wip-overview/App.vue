<script setup>
import { computed, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import {
  buildWipOverviewQueryParams,
  splitHoldByType,
} from '../core/wip-derive.js';
import { useAutoRefresh } from '../wip-shared/composables/useAutoRefresh.js';

import FilterPanel from './components/FilterPanel.vue';
import MatrixTable from './components/MatrixTable.vue';
import ParetoSection from './components/ParetoSection.vue';
import StatusCards from './components/StatusCards.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 60000;

const summary = ref(null);
const matrix = ref(null);
const hold = ref(null);
const filters = reactive({
  workorder: '',
  lotid: '',
  package: '',
  type: '',
});

const activeStatusFilter = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');

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

function buildFilters(status = null) {
  return buildWipOverviewQueryParams(filters, status);
}

async function fetchSummary(signal) {
  const result = await apiGet('/api/wip/overview/summary', {
    params: buildFilters(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch summary');
}

async function fetchMatrix(signal) {
  const result = await apiGet('/api/wip/overview/matrix', {
    params: buildFilters(activeStatusFilter.value),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch matrix');
}

async function fetchHold(signal) {
  const result = await apiGet('/api/wip/overview/hold', {
    params: buildFilters(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold data');
}

const lastUpdate = computed(() => {
  return summary.value?.dataUpdateDate ? `Last Update: ${summary.value.dataUpdateDate}` : '';
});

const matrixTitle = computed(() => {
  const base = 'Workcenter x Package Matrix (QTY)';
  if (!activeStatusFilter.value) {
    return base;
  }

  if (activeStatusFilter.value === 'quality-hold') {
    return `${base} - 品質異常 Hold Only`;
  }
  if (activeStatusFilter.value === 'non-quality-hold') {
    return `${base} - 非品質異常 Hold Only`;
  }
  return `${base} - ${activeStatusFilter.value.toUpperCase()} Only`;
});

const splitHold = computed(() => splitHoldByType(hold.value));

const { createAbortSignal, resetAutoRefresh, triggerRefresh } = useAutoRefresh({
  onRefresh: () => loadAllData(false),
  autoStart: true,
});

function showRefreshSuccess() {
  refreshSuccess.value = true;
  setTimeout(() => {
    refreshSuccess.value = false;
  }, 1500);
}

async function loadAllData(showOverlay = true) {
  const signal = createAbortSignal('wip-overview-all');

  if (showOverlay) {
    loading.value = true;
  }

  refreshing.value = true;
  refreshError.value = false;
  errorMessage.value = '';

  try {
    const [summaryData, matrixData, holdData] = await Promise.all([
      fetchSummary(signal),
      fetchMatrix(signal),
      fetchHold(signal),
    ]);

    summary.value = summaryData;
    matrix.value = matrixData;
    hold.value = holdData;
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function loadMatrixOnly() {
  const signal = createAbortSignal('wip-overview-matrix');
  refreshing.value = true;
  refreshError.value = false;

  try {
    matrix.value = await fetchMatrix(signal);
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message || '載入 Matrix 失敗';
  } finally {
    refreshing.value = false;
  }
}

function toggleStatusFilter(status) {
  activeStatusFilter.value = activeStatusFilter.value === status ? null : status;
  void loadMatrixOnly();
}

function updateFilters(nextFilters) {
  filters.workorder = nextFilters.workorder || '';
  filters.lotid = nextFilters.lotid || '';
  filters.package = nextFilters.package || '';
  filters.type = nextFilters.type || '';
}

function applyFilters(nextFilters) {
  updateFilters(nextFilters);
  void loadAllData(false);
}

function clearFilters() {
  updateFilters({ workorder: '', lotid: '', package: '', type: '' });
  void loadAllData(false);
}

function removeFilter(field) {
  filters[field] = '';
  void loadAllData(false);
}

function navigateToDetail(workcenter) {
  const params = new URLSearchParams();
  params.append('workcenter', workcenter);

  if (filters.workorder) {
    params.append('workorder', filters.workorder);
  }
  if (filters.lotid) {
    params.append('lotid', filters.lotid);
  }
  if (filters.package) {
    params.append('package', filters.package);
  }
  if (filters.type) {
    params.append('type', filters.type);
  }

  window.location.href = `/wip-detail?${params.toString()}`;
}

function navigateToHoldDetail(reason) {
  if (!reason) {
    return;
  }
  window.location.href = `/hold-detail?reason=${encodeURIComponent(reason)}`;
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

void loadAllData(true);
</script>

<template>
  <div class="dashboard wip-overview-page">
    <header class="header">
      <h1>WIP 即時概況</h1>
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

    <FilterPanel
      :filters="filters"
      @apply="applyFilters"
      @clear="clearFilters"
      @remove="removeFilter"
    />

    <SummaryCards :summary="summary" />

    <StatusCards
      :summary="summary?.byWipStatus || {}"
      :active-status="activeStatusFilter"
      @toggle="toggleStatusFilter"
    />

    <section class="content-grid">
      <section class="card">
        <div class="card-header">
          <div class="card-title">{{ matrixTitle }}</div>
        </div>
        <div class="card-body matrix-container">
          <MatrixTable :data="matrix" @drilldown="navigateToDetail" />
        </div>
      </section>

      <section class="pareto-grid">
        <ParetoSection
          type="quality"
          title="品質異常 Hold"
          :items="splitHold.quality"
          @drilldown="navigateToHoldDetail"
        />
        <ParetoSection
          type="non-quality"
          title="非品質異常 Hold"
          :items="splitHold.nonQuality"
          @drilldown="navigateToHoldDetail"
        />
      </section>
    </section>
  </div>

  <div v-if="loading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
