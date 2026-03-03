<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation.js';
import { buildWipOverviewQueryParams, splitHoldByType } from '../core/wip-derive.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import HoldLotTable from '../wip-shared/components/HoldLotTable.vue';
import ParetoSection from '../wip-shared/components/ParetoSection.vue';

import FilterPanel from '../wip-overview/components/FilterPanel.vue';
import SummaryCards from '../hold-detail/components/SummaryCards.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import HoldMatrix from './components/HoldMatrix.vue';

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 50;
const FILTER_OPTION_DEBOUNCE_MS = 120;

const summary = ref(null);
const matrix = ref(null);
const hold = ref(null);
const lots = ref([]);

const filterBar = reactive({
  holdType: 'all',
  reason: [],
});

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
let filterOptionsDebounceTimer = null;
let filterOptionsRequestToken = 0;

const holdTypeLabel = computed(() => {
  if (filterBar.holdType === 'non-quality') {
    return '非品質異常';
  }
  if (filterBar.holdType === 'all') {
    return '全部';
  }
  return '品質異常';
});

const showQualityPareto = computed(() => filterBar.holdType !== 'non-quality');
const showNonQualityPareto = computed(() => filterBar.holdType !== 'quality');

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

const reasonOptions = computed(() => {
  const source = summary.value || {};
  const candidates = [];

  if (Array.isArray(source.reason_options)) {
    candidates.push(...source.reason_options);
  }
  if (Array.isArray(source.reasonOptions)) {
    candidates.push(...source.reasonOptions);
  }
  if (Array.isArray(source.topReasons)) {
    candidates.push(...source.topReasons);
  }
  if (source.by_reason && typeof source.by_reason === 'object') {
    candidates.push(...Object.keys(source.by_reason));
  }
  if (source.byReason && typeof source.byReason === 'object') {
    candidates.push(...Object.keys(source.byReason));
  }

  return [...new Set(candidates.map((value) => String(value || '').trim()).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
});

const splitHold = computed(() => {
  const base = splitHoldByType(hold.value);
  const activeReasons = (filterBar.reason || []).map((v) => String(v).trim()).filter(Boolean);
  if (!activeReasons.length) {
    return base;
  }

  const reasonSet = new Set(activeReasons);
  return {
    quality: base.quality.filter((item) => reasonSet.has(String(item?.reason || '').trim())),
    nonQuality: base.nonQuality.filter((item) => reasonSet.has(String(item?.reason || '').trim())),
  };
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
  return normalizeArrayValues(values).join(',');
}

function normalizeHoldType(value) {
  const holdType = String(value || '').trim();
  if (holdType === 'quality' || holdType === 'non-quality' || holdType === 'all') {
    return holdType;
  }
  return 'all';
}

function updateFilters(nextFilters) {
  filters.workorder = normalizeArrayValues(nextFilters.workorder);
  filters.lotid = normalizeArrayValues(nextFilters.lotid);
  filters.package = normalizeArrayValues(nextFilters.package);
  filters.type = normalizeArrayValues(nextFilters.type);
  filters.firstname = normalizeArrayValues(nextFilters.firstname);
  filters.waferdesc = normalizeArrayValues(nextFilters.waferdesc);
}

function buildFilterBarParams() {
  const params = {
    hold_type: filterBar.holdType || 'all',
  };
  const reasonCsv = serializeFilterValue(filterBar.reason);
  if (reasonCsv) {
    params.reason = reasonCsv;
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

function buildAllFilterParams() {
  return {
    ...buildFilterBarParams(),
    ...buildWipOverviewQueryParams(filters),
  };
}

function buildLotsParams() {
  return {
    ...buildAllFilterParams(),
    ...buildMatrixFilterParams(),
    page: page.value,
    per_page: Number(pagination.value?.perPage || DEFAULT_PER_PAGE),
  };
}

function buildFilterOptionsParams(sourceFilters = filters) {
  const params = {
    ...buildWipOverviewQueryParams(sourceFilters),
    status: 'HOLD',
  };

  if (filterBar.holdType && filterBar.holdType !== 'all') {
    params.hold_type = filterBar.holdType;
  }

  return params;
}

async function fetchSummary(signal) {
  const result = await apiGet('/api/hold-overview/summary', {
    params: buildAllFilterParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold summary');
}

async function fetchMatrix(signal) {
  const result = await apiGet('/api/hold-overview/matrix', {
    params: buildAllFilterParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold matrix');
}

async function fetchHold(signal) {
  const result = await apiGet('/api/wip/overview/hold', {
    params: buildAllFilterParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold data');
}

async function fetchLots(signal) {
  const result = await apiGet('/api/hold-overview/lots', {
    params: buildLotsParams(),
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold lots');
}

async function loadFilterOptions(sourceFilters = filters) {
  const requestToken = ++filterOptionsRequestToken;

  try {
    const result = await apiGet('/api/wip/meta/filter-options', {
      params: buildFilterOptionsParams(sourceFilters),
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

function updateUrlState() {
  const params = new URLSearchParams();

  if (filterBar.holdType) {
    params.set('hold_type', filterBar.holdType);
  }
  const reasonCsv = serializeFilterValue(filterBar.reason);
  if (reasonCsv) {
    params.set('reason', reasonCsv);
  }
  if (matrixFilter.value?.workcenter) {
    params.set('workcenter', matrixFilter.value.workcenter);
  }
  if (matrixFilter.value?.package) {
    params.set('matrix_package', matrixFilter.value.package);
  }

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
  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  const query = params.toString();
  const nextUrl = query ? `/hold-overview?${query}` : '/hold-overview';
  replaceRuntimeHistory(nextUrl);
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
    const [summaryData, matrixData, holdData, lotsData] = await Promise.all([
      fetchSummary(signal),
      fetchMatrix(signal),
      fetchHold(signal),
      fetchLots(signal),
    ]);
    if (isStaleRequest(requestId)) {
      return;
    }

    summary.value = summaryData;
    matrix.value = matrixData;
    hold.value = holdData;
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

function navigateToHoldDetail(reason) {
  if (!reason) {
    return;
  }
  navigateToRuntimeRoute(`/hold-detail?reason=${encodeURIComponent(reason)}`);
}

function handleFilterChange(next) {
  const nextHoldType = normalizeHoldType(next?.holdType || 'all');
  const nextReason = normalizeArrayValues(next?.reason);

  const currentReasonCsv = serializeFilterValue(filterBar.reason);
  const nextReasonCsv = serializeFilterValue(nextReason);
  if (filterBar.holdType === nextHoldType && currentReasonCsv === nextReasonCsv) {
    return;
  }

  filterBar.holdType = nextHoldType;
  filterBar.reason = nextReason;
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function handleMatrixSelect(nextFilter) {
  matrixFilter.value = nextFilter;
  page.value = 1;
  updateUrlState();
  void loadLots();
}

function clearMatrixFilter() {
  if (!matrixFilter.value) {
    return;
  }
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadLots();
}

function applyFilters(nextFilters) {
  updateFilters(nextFilters);
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function clearAllFilters() {
  updateFilters({
    workorder: [],
    lotid: [],
    package: [],
    type: [],
    firstname: [],
    waferdesc: [],
  });
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function prevPage() {
  if (page.value <= 1) {
    return;
  }
  page.value -= 1;
  updateUrlState();
  void loadLots();
}

function nextPage() {
  if (page.value >= Number(pagination.value?.totalPages || 1)) {
    return;
  }
  page.value += 1;
  updateUrlState();
  void loadLots();
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

async function initializePage() {
  filterBar.holdType = normalizeHoldType(getUrlParam('hold_type') || 'all');
  filterBar.reason = parseCsvParam('reason');

  updateFilters({
    workorder: parseCsvParam('workorder'),
    lotid: parseCsvParam('lotid'),
    package: parseCsvParam('package'),
    type: parseCsvParam('type'),
    firstname: parseCsvParam('firstname'),
    waferdesc: parseCsvParam('waferdesc'),
  });

  const workcenter = getUrlParam('workcenter');
  const matrixPkg = getUrlParam('matrix_package');
  if (workcenter || matrixPkg) {
    matrixFilter.value = {
      workcenter: workcenter || null,
      package: matrixPkg || null,
    };
  }

  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }

  updateUrlState();

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
  <div class="dashboard hold-overview-page">
    <header class="header">
      <div class="header-left">
        <h1>Hold 即時概況</h1>
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

    <FilterPanel
      :filters="filters"
      :options="filterOptions"
      :loading="refreshing"
      @apply="applyFilters"
      @clear="clearAllFilters"
      @draft-change="onFilterDraftChange"
    />

    <FilterBar
      :hold-type="filterBar.holdType"
      :reason="filterBar.reason"
      :reasons="reasonOptions"
      :disabled="refreshing && initialLoading"
      @change="handleFilterChange"
    />

    <SummaryCards :summary="summary" />

    <section class="content-grid">
      <section class="card">
        <div class="card-header">
          <div class="card-title">Workcenter x Package Matrix (QTY)</div>
        </div>
        <div class="card-body matrix-container">
          <HoldMatrix :data="matrix" :active-filter="matrixFilter" @select="handleMatrixSelect" />
        </div>
      </section>

      <section class="pareto-grid">
        <ParetoSection
          v-if="showQualityPareto"
          type="quality"
          title="品質異常 Hold"
          :items="splitHold.quality"
          @drilldown="navigateToHoldDetail"
        />
        <ParetoSection
          v-if="showNonQualityPareto"
          type="non-quality"
          title="非品質異常 Hold"
          :items="splitHold.nonQuality"
          @drilldown="navigateToHoldDetail"
        />
      </section>

      <FilterIndicator
        :matrix-filter="matrixFilter"
        :show-clear-all="true"
        @clear-matrix="clearMatrixFilter"
        @clear-all="clearMatrixFilter"
      />

      <HoldLotTable
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
    </section>
  </div>

  <div v-if="initialLoading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
