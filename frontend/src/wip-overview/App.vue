<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { apiPost } from '../core/api.js';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result.js';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation.js';
import { buildWipOverviewQueryParams } from '../core/wip-derive.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import FilterPanel from './components/FilterPanel.vue';
import MatrixTable from './components/MatrixTable.vue';
import StatusCards from './components/StatusCards.vue';

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

const activeStatusFilter = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
let filterOptionsDebounceTimer = null;
let filterOptionsRequestToken = 0;

// -- useFilterOrchestrator: status=immediate (matrix only), panel fields=draft-apply (summary+matrix) --
const filterOrchestrator = useFilterOrchestrator({
  fields: {
    workorder:  { trigger: 'draft-apply', initial: [] },
    lotid:      { trigger: 'draft-apply', initial: [] },
    package:    { trigger: 'draft-apply', initial: [] },
    type:       { trigger: 'draft-apply', initial: [] },
    firstname:  { trigger: 'draft-apply', initial: [] },
    waferdesc:  { trigger: 'draft-apply', initial: [] },
    status:     { trigger: 'immediate', initial: null },
  },
  pagination: { resetOn: ['*'] },
  onFetch(committed) {
    // Immediate trigger (status change) -> matrix only reload
    void loadMatrixOnly();
  },
});

// Keep a reactive proxy to the committed filters for building query params
const filters = reactive({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
});

// unwrapApiResult imported from ../core/unwrap-api-result.js (as unwrapApiData)

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
  const result = await apiPost('/api/wip/overview/summary', buildFilters(), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch summary');
}

async function fetchMatrix(signal) {
  const result = await apiPost('/api/wip/overview/matrix', buildFilters(activeStatusFilter.value), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch matrix');
}

async function loadFilterOptions(sourceFilters = filters) {
  const requestToken = ++filterOptionsRequestToken;

  try {
    const body = buildWipOverviewQueryParams(sourceFilters);
    const result = await apiPost('/api/wip/meta/filter-options', body, {
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
  return summary.value?.dataUpdateDate ?? '--';
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
  // Update orchestrator immediate field
  filterOrchestrator.updateField('status', activeStatusFilter.value);
  updateUrlState();
}

function updateFilters(nextFilters) {
  filters.workorder = normalizeArrayValues(nextFilters.workorder);
  filters.lotid = normalizeArrayValues(nextFilters.lotid);
  filters.package = normalizeArrayValues(nextFilters.package);
  filters.type = normalizeArrayValues(nextFilters.type);
  filters.firstname = normalizeArrayValues(nextFilters.firstname);
  filters.waferdesc = normalizeArrayValues(nextFilters.waferdesc);

  // Sync to orchestrator draft
  filterOrchestrator.draft.workorder = filters.workorder;
  filterOrchestrator.draft.lotid = filters.lotid;
  filterOrchestrator.draft.package = filters.package;
  filterOrchestrator.draft.type = filters.type;
  filterOrchestrator.draft.firstname = filters.firstname;
  filterOrchestrator.draft.waferdesc = filters.waferdesc;
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
  // Commit draft-apply fields via orchestrator
  filterOrchestrator.applyDraft();
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
  filterOrchestrator.resetAll();
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

  // Sync initial values to orchestrator
  filterOrchestrator.draft.status = activeStatusFilter.value;
  filterOrchestrator.committed.status = activeStatusFilter.value;

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
    <PageHeader
      title="WIP 即時概況"
      :last-update="lastUpdate"
      :refreshing="refreshing"
      :refresh-success="refreshSuccess"
      :refresh-error="refreshError"
      @refresh="manualRefresh"
    />

    <ErrorBanner :message="errorMessage" @dismiss="errorMessage = ''" />

    <FilterPanel
      :filters="filters"
      :options="filterOptions"
      :loading="refreshing"
      @apply="applyFilters"
      @clear="clearFilters"
      @draft-change="onFilterDraftChange"
    />

    <SummaryCardGroup :columns="2">
      <SummaryCard
        label="Total Lots"
        :value="summary?.totalLots"
        format="number"
        accent="brand"
      />
      <SummaryCard
        label="Total QTY"
        :value="summary?.totalQtyPcs"
        format="number"
        accent="info"
      />
    </SummaryCardGroup>

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
        <div class="card-body ui-card-body matrix-container ui-table-wrap" :class="{ 'is-loading': refreshing }">
          <MatrixTable :data="matrix" @drilldown="navigateToDetail" />
          <EmptyState v-if="!refreshing && !matrix" type="no-data" />
        </div>
      </section>

    </section>
  </div>

  <LoadingOverlay v-if="loading" tier="page" />
</template>
