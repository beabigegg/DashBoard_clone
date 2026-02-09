<script setup>
import { computed, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { buildWipDetailQueryParams } from '../core/wip-derive.js';
import { useAutoRefresh } from '../wip-shared/composables/useAutoRefresh.js';

import FilterPanel from './components/FilterPanel.vue';
import LotDetailPanel from './components/LotDetailPanel.vue';
import LotTable from './components/LotTable.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 60000;
const PAGE_SIZE = 100;

const workcenter = ref('');
const page = ref(1);
const filters = reactive({
  workorder: '',
  lotid: '',
  package: '',
  type: '',
});
const activeStatusFilter = ref(null);

const detailData = ref(null);
const loading = ref(true);
const tableLoading = ref(false);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
const selectedLotId = ref('');

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

function getUrlParam(name) {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function updateUrlState() {
  if (!workcenter.value) {
    return;
  }

  const params = new URLSearchParams();
  params.set('workcenter', workcenter.value);

  if (filters.workorder) {
    params.set('workorder', filters.workorder);
  }
  if (filters.lotid) {
    params.set('lotid', filters.lotid);
  }
  if (filters.package) {
    params.set('package', filters.package);
  }
  if (filters.type) {
    params.set('type', filters.type);
  }

  window.history.replaceState({}, '', `/wip-detail?${params.toString()}`);
}

async function fetchWorkcenters(signal) {
  const result = await apiGet('/api/wip/meta/workcenters', {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch workcenters');
}

async function fetchDetail(signal) {
  if (!workcenter.value) {
    return null;
  }

  const params = buildWipDetailQueryParams({
    page: page.value,
    pageSize: PAGE_SIZE,
    filters,
    statusFilter: activeStatusFilter.value,
  });

  const result = await apiGet(`/api/wip/detail/${encodeURIComponent(workcenter.value)}`, {
    params,
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch detail');
}

function showRefreshSuccess() {
  refreshSuccess.value = true;
  setTimeout(() => {
    refreshSuccess.value = false;
  }, 1500);
}

const { createAbortSignal, triggerRefresh, startAutoRefresh, resetAutoRefresh } = useAutoRefresh({
  onRefresh: () => loadAllData(false),
  autoStart: false,
});

async function loadAllData(showOverlay = true) {
  if (!workcenter.value) {
    return;
  }

  const signal = createAbortSignal('wip-detail-all');

  if (showOverlay) {
    loading.value = true;
  }

  tableLoading.value = true;
  refreshing.value = true;
  refreshError.value = false;
  errorMessage.value = '';

  try {
    detailData.value = await fetchDetail(signal);
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    loading.value = false;
    tableLoading.value = false;
    refreshing.value = false;
  }
}

async function loadTableOnly() {
  if (!workcenter.value) {
    return;
  }

  const signal = createAbortSignal('wip-detail-table');
  tableLoading.value = true;
  refreshing.value = true;

  try {
    detailData.value = await fetchDetail(signal);
    showRefreshSuccess();
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message || '載入表格失敗';
  } finally {
    tableLoading.value = false;
    refreshing.value = false;
  }
}

const pageTitle = computed(() => {
  return workcenter.value ? `WIP Detail - ${workcenter.value}` : 'WIP Detail';
});

const lastUpdate = computed(() => {
  return detailData.value?.sys_date ? `Last Update: ${detailData.value.sys_date}` : '';
});

const summary = computed(() => detailData.value?.summary || null);
const tableData = computed(() => ({
  lots: detailData.value?.lots || [],
  specs: detailData.value?.specs || [],
  pagination: detailData.value?.pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 1 },
}));

function updateFilters(nextFilters) {
  filters.workorder = nextFilters.workorder || '';
  filters.lotid = nextFilters.lotid || '';
  filters.package = nextFilters.package || '';
  filters.type = nextFilters.type || '';
}

function applyFilters(nextFilters) {
  updateFilters(nextFilters);
  page.value = 1;
  updateUrlState();
  void loadAllData(false);
}

function clearFilters() {
  updateFilters({ workorder: '', lotid: '', package: '', type: '' });
  activeStatusFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadAllData(false);
}

function toggleStatusFilter(status) {
  activeStatusFilter.value = activeStatusFilter.value === status ? null : status;
  page.value = 1;
  selectedLotId.value = '';
  void loadTableOnly();
}

function prevPage() {
  if (page.value <= 1) {
    return;
  }
  page.value -= 1;
  selectedLotId.value = '';
  void loadAllData(false);
}

function nextPage() {
  const totalPages = Number(tableData.value.pagination?.total_pages || 1);
  if (page.value >= totalPages) {
    return;
  }
  page.value += 1;
  selectedLotId.value = '';
  void loadAllData(false);
}

function openLotDetail(lotId) {
  selectedLotId.value = lotId;
}

function closeLotDetail() {
  selectedLotId.value = '';
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

async function initializePage() {
  workcenter.value = getUrlParam('workcenter');

  filters.workorder = getUrlParam('workorder');
  filters.lotid = getUrlParam('lotid');
  filters.package = getUrlParam('package');
  filters.type = getUrlParam('type');

  if (!workcenter.value) {
    const signal = createAbortSignal('wip-detail-init');
    try {
      const workcenters = await fetchWorkcenters(signal);
      if (Array.isArray(workcenters) && workcenters.length > 0) {
        workcenter.value = workcenters[0].name;
        updateUrlState();
      }
    } catch (error) {
      if (error?.name !== 'AbortError') {
        errorMessage.value = error?.message || '無法取得工站列表';
      }
    }
  }

  if (!workcenter.value) {
    loading.value = false;
    errorMessage.value = errorMessage.value || 'No workcenter available';
    return;
  }

  await loadAllData(true);
  startAutoRefresh();
}

void initializePage();
</script>

<template>
  <div class="dashboard wip-detail-page">
    <header class="header">
      <div class="header-left">
        <a href="/wip-overview" class="btn btn-back">&larr; Overview</a>
        <h1>{{ pageTitle }}</h1>
      </div>
      <div class="header-right">
        <span class="last-update">
          <span class="refresh-indicator" :class="{ active: refreshing }"></span>
          <span class="refresh-success" :class="{ active: refreshSuccess }">&#10003;</span>
          <span class="refresh-error" :class="{ active: refreshError }"></span>
          <span>{{ lastUpdate }}</span>
        </span>
        <button type="button" class="btn btn-light" @click="manualRefresh">Refresh</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <FilterPanel :filters="filters" @apply="applyFilters" @clear="clearFilters" />

    <SummaryCards
      :summary="summary"
      :active-status="activeStatusFilter"
      @toggle="toggleStatusFilter"
    />

    <LotTable
      :data="tableData"
      :loading="tableLoading"
      :active-status="activeStatusFilter"
      :selected-lot-id="selectedLotId"
      @select-lot="openLotDetail"
      @prev-page="prevPage"
      @next-page="nextPage"
    />

    <LotDetailPanel :lot-id="selectedLotId" @close="closeLotDetail" />
  </div>

  <div v-if="loading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
