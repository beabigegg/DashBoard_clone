<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation.js';
import { buildWipOverviewQueryParams } from '../core/wip-derive.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';

import FilterPanel from './components/FilterPanel.vue';
import MatrixTable from './components/MatrixTable.vue';
import StatusCards from './components/StatusCards.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 60000;
const FILTER_OPTION_DEBOUNCE_MS = 120;

const summary = ref(null);
const matrix = ref(null);
const filterOptions = ref({
  workorders: [],
  lotids: [],
  packages: [],
  types: [],
  firstnames: [],
  waferdescs: [],
});
const filters = reactive({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
});

const activeStatusFilter = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
let filterOptionsDebounceTimer = null;
let filterOptionsRequestToken = 0;

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

function parseCsvParam(name) {
  const raw = getUrlParam(name);
  if (!raw) {
    return [];
  }
  return raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function normalizeArrayValues(values) {
  if (!values) {
    return [];
  }
  if (Array.isArray(values)) {
    return values.map((value) => String(value).trim()).filter(Boolean);
  }
  return String(values)
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function serializeFilterValue(values) {
  const normalized = normalizeArrayValues(values);
  return normalized.join(',');
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

async function loadFilterOptions(sourceFilters = filters) {
  const requestToken = ++filterOptionsRequestToken;

  try {
    const params = buildWipOverviewQueryParams(sourceFilters);
    const result = await apiGet('/api/wip/meta/filter-options', {
      params,
      timeout: API_TIMEOUT,
      silent: true,
    });
    const data = unwrapApiResult(result, '載入篩選選項失敗');

    if (requestToken !== filterOptionsRequestToken) {
      return;
    }

    filterOptions.value = {
      workorders: Array.isArray(data?.workorders) ? data.workorders : [],
      lotids: Array.isArray(data?.lotids) ? data.lotids : [],
      packages: Array.isArray(data?.packages) ? data.packages : [],
      types: Array.isArray(data?.types) ? data.types : [],
      firstnames: Array.isArray(data?.firstnames) ? data.firstnames : [],
      waferdescs: Array.isArray(data?.waferdescs) ? data.waferdescs : [],
    };
  } catch (error) {
    if (error?.name !== 'AbortError') {
      console.warn('載入 WIP 篩選選項失敗:', error);
    }
  }
}

function scheduleFilterOptionsReload(nextDraftFilters) {
  if (filterOptionsDebounceTimer) {
    clearTimeout(filterOptionsDebounceTimer);
  }

  filterOptionsDebounceTimer = setTimeout(() => {
    void loadFilterOptions(nextDraftFilters);
  }, FILTER_OPTION_DEBOUNCE_MS);
}

function onFilterDraftChange(nextDraftFilters) {
  scheduleFilterOptionsReload(nextDraftFilters);
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

const { createAbortSignal, triggerRefresh } = useAutoRefresh({
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
    const [summaryData, matrixData] = await Promise.all([
      fetchSummary(signal),
      fetchMatrix(signal),
    ]);

    summary.value = summaryData;
    matrix.value = matrixData;
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
  if (status === 'quality-hold') {
    navigateToRuntimeRoute('/hold-overview?hold_type=quality');
    return;
  }
  if (status === 'non-quality-hold') {
    navigateToRuntimeRoute('/hold-overview?hold_type=non-quality');
    return;
  }

  activeStatusFilter.value = activeStatusFilter.value === status ? null : status;
  updateUrlState();
  void loadMatrixOnly();
}

function updateFilters(nextFilters) {
  filters.workorder = normalizeArrayValues(nextFilters.workorder);
  filters.lotid = normalizeArrayValues(nextFilters.lotid);
  filters.package = normalizeArrayValues(nextFilters.package);
  filters.type = normalizeArrayValues(nextFilters.type);
  filters.firstname = normalizeArrayValues(nextFilters.firstname);
  filters.waferdesc = normalizeArrayValues(nextFilters.waferdesc);
}

function updateUrlState() {
  const params = new URLSearchParams();

  const workorder = serializeFilterValue(filters.workorder);
  const lotid = serializeFilterValue(filters.lotid);
  const pkg = serializeFilterValue(filters.package);
  const type = serializeFilterValue(filters.type);
  const firstname = serializeFilterValue(filters.firstname);
  const waferdesc = serializeFilterValue(filters.waferdesc);

  if (workorder) {
    params.set('workorder', workorder);
  }
  if (lotid) {
    params.set('lotid', lotid);
  }
  if (pkg) {
    params.set('package', pkg);
  }
  if (type) {
    params.set('type', type);
  }
  if (firstname) {
    params.set('firstname', firstname);
  }
  if (waferdesc) {
    params.set('waferdesc', waferdesc);
  }
  if (activeStatusFilter.value) {
    params.set('status', activeStatusFilter.value);
  }

  const query = params.toString();
  const nextUrl = query ? `/wip-overview?${query}` : '/wip-overview';
  replaceRuntimeHistory(nextUrl);
}

function applyFilters(nextFilters) {
  updateFilters(nextFilters);
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function clearFilters() {
  updateFilters({
    workorder: [],
    lotid: [],
    package: [],
    type: [],
    firstname: [],
    waferdesc: [],
  });
  activeStatusFilter.value = null;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function navigateToDetail(workcenter) {
  const params = new URLSearchParams();
  params.append('workcenter', workcenter);

  const workorder = serializeFilterValue(filters.workorder);
  const lotid = serializeFilterValue(filters.lotid);
  const pkg = serializeFilterValue(filters.package);
  const type = serializeFilterValue(filters.type);
  const firstname = serializeFilterValue(filters.firstname);
  const waferdesc = serializeFilterValue(filters.waferdesc);

  if (workorder) {
    params.append('workorder', workorder);
  }
  if (lotid) {
    params.append('lotid', lotid);
  }
  if (pkg) {
    params.append('package', pkg);
  }
  if (type) {
    params.append('type', type);
  }
  if (firstname) {
    params.append('firstname', firstname);
  }
  if (waferdesc) {
    params.append('waferdesc', waferdesc);
  }
  if (activeStatusFilter.value) {
    params.append('status', activeStatusFilter.value);
  }

  navigateToRuntimeRoute(`/wip-detail?${params.toString()}`);
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

async function initializePage() {
  updateFilters({
    workorder: parseCsvParam('workorder'),
    lotid: parseCsvParam('lotid'),
    package: parseCsvParam('package'),
    type: parseCsvParam('type'),
    firstname: parseCsvParam('firstname'),
    waferdesc: parseCsvParam('waferdesc'),
  });
  activeStatusFilter.value = getUrlParam('status') || null;

  await Promise.all([
    loadFilterOptions(filters),
    loadAllData(true),
  ]);
}

onMounted(() => {
  void initializePage();
});

onBeforeUnmount(() => {
  if (filterOptionsDebounceTimer) {
    clearTimeout(filterOptionsDebounceTimer);
    filterOptionsDebounceTimer = null;
  }
});
</script>

<template>
  <div class="dashboard wip-overview-page theme-wip-overview">
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
      :options="filterOptions"
      :loading="refreshing"
      @apply="applyFilters"
      @clear="clearFilters"
      @draft-change="onFilterDraftChange"
    />

    <SummaryCards :summary="summary" />

    <StatusCards
      :summary="summary?.byWipStatus || {}"
      :active-status="activeStatusFilter"
      @toggle="toggleStatusFilter"
    />

    <section class="content-grid">
      <section class="card ui-card">
        <div class="card-header ui-card-header">
          <div class="card-title ui-card-title">{{ matrixTitle }}</div>
        </div>
        <div class="card-body ui-card-body matrix-container">
          <MatrixTable :data="matrix" @drilldown="navigateToDetail" />
        </div>
      </section>

    </section>
  </div>

  <div v-if="loading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
