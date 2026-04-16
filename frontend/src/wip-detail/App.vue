<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result.js';
import { replaceRuntimeHistory, toRuntimeRoute } from '../core/shell-navigation.js';
import { buildWipDetailQueryParams, buildWipOverviewQueryParams } from '../core/wip-derive.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';

import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import FilterPanel from './components/FilterPanel.vue';
import LotDetailPanel from './components/LotDetailPanel.vue';
import LotTable from './components/LotTable.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 60000;
const PAGE_SIZE = 20;
const FILTER_OPTION_DEBOUNCE_MS = 120;

const workcenter = ref('');
const page = ref(1);
const filters = reactive({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
});
const filterOptions = ref({
  workorders: [],
  lotids: [],
  packages: [],
  types: [],
  firstnames: [],
  waferdescs: [],
});

const activeStatusFilter = ref(null);

const detailData = ref(null);
const loading = ref(true);
const tableLoading = ref(false);
const paginationLoading = ref(false);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
const selectedLotId = ref('');

let filterOptionsDebounceTimer = null;
let filterOptionsRequestToken = 0;

// -- useFilterOrchestrator: status=immediate (page+lot clear+table reload), panel=draft-apply (status clear+page+lot clear+full reload) --
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
  onFetch(_committed) {
    // Immediate trigger (status change) -> page reset + lot clear + table reload
    page.value = 1;
    selectedLotId.value = '';
    void loadTableOnly();
  },
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

function updateUrlState() {
  if (!workcenter.value) {
    return;
  }

  const params = new URLSearchParams();
  params.set('workcenter', workcenter.value);

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

  replaceRuntimeHistory(`/wip-detail?${params.toString()}`);
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

  const body = buildWipDetailQueryParams({
    page: page.value,
    pageSize: PAGE_SIZE,
    filters,
    statusFilter: activeStatusFilter.value,
  });

  const result = await apiPost(`/api/wip/detail/${encodeURIComponent(workcenter.value)}`, body, {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch detail');
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
      console.warn('載入 WIP Detail 篩選選項失敗:', error);
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

function showRefreshSuccess() {
  refreshSuccess.value = true;
  setTimeout(() => {
    refreshSuccess.value = false;
  }, 1500);
}

const { createAbortSignal, triggerRefresh, startAutoRefresh } = useAutoRefresh({
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
  return detailData.value?.sys_date ?? '--';
});

const summary = computed(() => detailData.value?.summary || null);
const tableData = computed(() => ({
  lots: detailData.value?.lots || [],
  specs: detailData.value?.specs || [],
  pagination: detailData.value?.pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 1 },
}));
const backUrl = computed(() => {
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
  return toRuntimeRoute(query ? `/wip-overview?${query}` : '/wip-overview');
});

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

function applyFilters(nextFilters) {
  updateFilters(nextFilters);
  // Apply draft fields via orchestrator; status clear + page + lot clear
  activeStatusFilter.value = null;
  filterOrchestrator.applyDraft();
  page.value = 1;
  selectedLotId.value = '';
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
  page.value = 1;
  selectedLotId.value = '';
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function toggleStatusFilter(status) {
  activeStatusFilter.value = activeStatusFilter.value === status ? null : status;
  // Delegate to orchestrator immediate field; onFetch handles page/lot/table reload
  filterOrchestrator.updateField('status', activeStatusFilter.value);
  updateUrlState();
}

async function loadPageData() {
  if (!workcenter.value) {
    return;
  }

  const signal = createAbortSignal('wip-detail-page');
  paginationLoading.value = true;

  try {
    detailData.value = await fetchDetail(signal);
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    errorMessage.value = error?.message || '載入表格失敗';
  } finally {
    paginationLoading.value = false;
  }
}

function prevPage() {
  if (page.value <= 1) {
    return;
  }
  page.value -= 1;
  selectedLotId.value = '';
  void loadPageData();
}

function nextPage() {
  const totalPages = Number(tableData.value.pagination?.total_pages || 1);
  if (page.value >= totalPages) {
    return;
  }
  page.value += 1;
  selectedLotId.value = '';
  void loadPageData();
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

  updateFilters({
    workorder: parseCsvParam('workorder'),
    lotid: parseCsvParam('lotid'),
    package: parseCsvParam('package'),
    type: parseCsvParam('type'),
    firstname: parseCsvParam('firstname'),
    waferdesc: parseCsvParam('waferdesc'),
  });
  activeStatusFilter.value = getUrlParam('status') || null;

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

  await Promise.all([
    loadFilterOptions(filters),
    loadAllData(true),
  ]);
  startAutoRefresh();
}

void initializePage();

onBeforeUnmount(() => {
  if (filterOptionsDebounceTimer) {
    clearTimeout(filterOptionsDebounceTimer);
    filterOptionsDebounceTimer = null;
  }
});
</script>

<template>
  <div class="dashboard wip-detail-page theme-wip-detail">
    <PageHeader
      :title="pageTitle"
      :last-update="lastUpdate"
      :refreshing="refreshing"
      :refresh-success="refreshSuccess"
      :refresh-error="refreshError"
      @refresh="manualRefresh"
    >
      <template #header-left>
        <a :href="backUrl" class="ui-btn ui-btn--ghost ui-btn--sm">&larr; Overview</a>
      </template>
    </PageHeader>

    <ErrorBanner :message="errorMessage" :dismissible="false" />

    <FilterPanel
      :filters="filters"
      :options="filterOptions"
      :loading="refreshing"
      @apply="applyFilters"
      @clear="clearFilters"
      @draft-change="onFilterDraftChange"
    />

    <SummaryCards
      :summary="summary"
      :active-status="activeStatusFilter"
      @toggle="toggleStatusFilter"
    />

    <LotTable
      :data="tableData"
      :loading="tableLoading"
      :paginating="paginationLoading"
      :active-status="activeStatusFilter"
      :selected-lot-id="selectedLotId"
      @select-lot="openLotDetail"
      @prev-page="prevPage"
      @next-page="nextPage"
    />

    <LotDetailPanel :lot-id="selectedLotId" @close="closeLotDetail" />
  </div>

  <LoadingOverlay v-if="loading" tier="page" />
</template>
