<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { apiPost } from '../core/api';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation';
import { storeWipNavigationState, loadWipNavigationState } from '../core/wip-navigation-state';
import { buildWipOverviewQueryParams } from '../core/wip-derive';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh';
import { bindUpdateBadge } from '../shared-composables/usePageUpdateBadge';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import FilterPanel from './components/FilterPanel.vue';
import MatrixTable from './components/MatrixTable.vue';
import StatusCards from './components/StatusCards.vue';
import WipDistributionCharts from './components/WipDistributionCharts.vue';

// ── Local type aliases ──────────────────────────────────────────────────────
interface WipOverviewSummary {
  dataUpdateDate?: string;
  totalLots?: number;
  totalQtyPcs?: number;
  byWipStatus?: Record<string, unknown>;
  [key: string]: unknown;
}

interface WipOverviewMatrix {
  workcenters?: string[];
  packages?: string[];
  matrix?: Record<string, Record<string, unknown>>;
  workcenter_totals?: Record<string, unknown>;
  package_totals?: Record<string, unknown>;
  grand_total?: unknown;
  [key: string]: unknown;
}

const API_TIMEOUT = 60000;
const FILTER_OPTION_DEBOUNCE_MS = 120;

const summary = ref<WipOverviewSummary | null>(null);
const matrix = ref<WipOverviewMatrix | null>(null);
const filterOptions = ref<{
  workorders: string[];
  lotids: string[];
  packages: string[];
  types: string[];
  firstnames: string[];
  waferdescs: string[];
  workflows: string[];
  bops: string[];
  pjFunctions: string[];
}>({
  workorders: [],
  lotids: [],
  packages: [],
  types: [],
  firstnames: [],
  waferdescs: [],
  workflows: [],
  bops: [],
  pjFunctions: [],
});

const activeStatusFilter = ref<string | null>(null);
const loading = ref(true);
const refreshing = ref(false);
const refreshSuccess = ref(false);

const refreshError = ref(false);
const errorMessage = ref('');
let filterOptionsDebounceTimer: ReturnType<typeof setTimeout> | null = null;
let filterOptionsRequestToken = 0;

// -- useFilterOrchestrator: status=immediate (matrix only), panel fields=draft-apply (summary+matrix) --
const filterOrchestrator = useFilterOrchestrator({
  fields: {
    workorder:   { trigger: 'draft-apply', initial: [] },
    lotid:       { trigger: 'draft-apply', initial: [] },
    package:     { trigger: 'draft-apply', initial: [] },
    type:        { trigger: 'draft-apply', initial: [] },
    firstname:   { trigger: 'draft-apply', initial: [] },
    waferdesc:   { trigger: 'draft-apply', initial: [] },
    workflow:    { trigger: 'draft-apply', initial: [] },
    bop:         { trigger: 'draft-apply', initial: [] },
    pjFunction:  { trigger: 'draft-apply', initial: [] },
    status:      { trigger: 'immediate', initial: null },
  },
  pagination: { resetOn: ['*'] },
  onFetch(_committed) {
    // Immediate trigger (status change) -> matrix only reload
    void loadMatrixOnly();
  },
});

// Keep a reactive proxy to the committed filters for building query params
const filters = reactive<{
  workorder: string[];
  lotid: string[];
  package: string[];
  type: string[];
  firstname: string[];
  waferdesc: string[];
  workflow: string[];
  bop: string[];
  pjFunction: string[];
}>({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
  workflow: [],
  bop: [],
  pjFunction: [],
});

// Active matrix filter: { workcenter, package } for cell click, { workcenter } for row click
const activeMatrixFilter = ref<{ workcenter?: string | null; package?: string | null } | null>(null);

// Cross-filter state: set by chart interactions, drives matrix highlight + chart cross-context
const chartSelectedPackage = ref<string | null>(null);
const chartSelectedStation = ref<string | null>(null);

// unwrapApiResult imported from ../core/unwrap-api-result.js (as unwrapApiData)

function getUrlParam(name: string): string {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function parseCsvParam(name: string): string[] {
  const raw = getUrlParam(name);
  if (!raw) {
    return [];
  }
  return raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function normalizeArrayValues(values: string | string[] | null | undefined): string[] {
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

function serializeFilterValue(values: string | string[] | null | undefined): string {
  const normalized = normalizeArrayValues(values);
  return normalized.join(',');
}

function buildFilters(status: string | null = null) {
  return buildWipOverviewQueryParams(filters, status);
}

async function fetchSummary(signal: AbortSignal): Promise<WipOverviewSummary> {
  const result = await apiPost('/api/wip/overview/summary', buildFilters(), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch summary') as WipOverviewSummary;
}

async function fetchMatrix(signal: AbortSignal): Promise<WipOverviewMatrix> {
  const result = await apiPost('/api/wip/overview/matrix', buildFilters(activeStatusFilter.value), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch matrix') as WipOverviewMatrix;
}

async function loadFilterOptions(sourceFilters = filters): Promise<void> {
  const requestToken = ++filterOptionsRequestToken;

  try {
    const body = buildWipOverviewQueryParams(sourceFilters);
    const result = await apiPost('/api/wip/meta/filter-options', body, {
      timeout: API_TIMEOUT,
      silent: true,
    });
    const data = unwrapApiResult(result, '載入篩選選項失敗') as Record<string, unknown>;

    if (requestToken !== filterOptionsRequestToken) {
      return;
    }

    filterOptions.value = {
      workorders: Array.isArray(data?.workorders) ? (data.workorders as string[]) : [],
      lotids: Array.isArray(data?.lotids) ? (data.lotids as string[]) : [],
      packages: Array.isArray(data?.packages) ? (data.packages as string[]) : [],
      types: Array.isArray(data?.types) ? (data.types as string[]) : [],
      firstnames: Array.isArray(data?.firstnames) ? (data.firstnames as string[]) : [],
      waferdescs: Array.isArray(data?.waferdescs) ? (data.waferdescs as string[]) : [],
      workflows: Array.isArray(data?.workflows) ? (data.workflows as string[]) : [],
      bops: Array.isArray(data?.bops) ? (data.bops as string[]) : [],
      pjFunctions: Array.isArray(data?.pjFunctions) ? (data.pjFunctions as string[]) : [],
    };
  } catch (err: unknown) {
    const error = err as { name?: string };
    if (error?.name !== 'AbortError') {
      console.warn('載入 WIP 篩選選項失敗:', err);
    }
  }
}

function scheduleFilterOptionsReload(nextDraftFilters: typeof filters): void {
  if (filterOptionsDebounceTimer) {
    clearTimeout(filterOptionsDebounceTimer);
  }

  filterOptionsDebounceTimer = setTimeout(() => {
    void loadFilterOptions(nextDraftFilters);
  }, FILTER_OPTION_DEBOUNCE_MS);
}

function onFilterDraftChange(nextDraftFilters: typeof filters): void {
  scheduleFilterOptionsReload(nextDraftFilters);
}

const lastUpdate = computed(() => {
  return summary.value?.dataUpdateDate ?? '--';
});

bindUpdateBadge({ updateTime: lastUpdate, refreshing, refreshSuccess });

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
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message ?? '載入資料失敗';
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
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError') {
      return;
    }
    refreshError.value = true;
    errorMessage.value = error?.message ?? '載入 Matrix 失敗';
  } finally {
    refreshing.value = false;
  }
}

function toggleStatusFilter(status: string) {
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

function updateFilters(nextFilters: Partial<typeof filters>) {
  filters.workorder = normalizeArrayValues(nextFilters.workorder);
  filters.lotid = normalizeArrayValues(nextFilters.lotid);
  filters.package = normalizeArrayValues(nextFilters.package);
  filters.type = normalizeArrayValues(nextFilters.type);
  filters.firstname = normalizeArrayValues(nextFilters.firstname);
  filters.waferdesc = normalizeArrayValues(nextFilters.waferdesc);
  filters.workflow = normalizeArrayValues(nextFilters.workflow);
  filters.bop = normalizeArrayValues(nextFilters.bop);
  filters.pjFunction = normalizeArrayValues(nextFilters.pjFunction);

  // Sync to orchestrator draft
  filterOrchestrator.draft.workorder = filters.workorder;
  filterOrchestrator.draft.lotid = filters.lotid;
  filterOrchestrator.draft.package = filters.package;
  filterOrchestrator.draft.type = filters.type;
  filterOrchestrator.draft.firstname = filters.firstname;
  filterOrchestrator.draft.waferdesc = filters.waferdesc;
  filterOrchestrator.draft.workflow = filters.workflow;
  filterOrchestrator.draft.bop = filters.bop;
  filterOrchestrator.draft.pjFunction = filters.pjFunction;
}

function updateUrlState() {
  const params = new URLSearchParams();

  const workorder = serializeFilterValue(filters.workorder);
  const lotid = serializeFilterValue(filters.lotid);
  const pkg = serializeFilterValue(filters.package);
  const type = serializeFilterValue(filters.type);
  const firstname = serializeFilterValue(filters.firstname);
  const waferdesc = serializeFilterValue(filters.waferdesc);
  const workflow = serializeFilterValue(filters.workflow);
  const bop = serializeFilterValue(filters.bop);
  const pjFunction = serializeFilterValue(filters.pjFunction);

  if (workorder) params.set('workorder', workorder);
  if (lotid) params.set('lotid', lotid);
  if (pkg) params.set('package', pkg);
  if (type) params.set('type', type);
  if (firstname) params.set('firstname', firstname);
  if (waferdesc) params.set('waferdesc', waferdesc);
  if (workflow) params.set('workflow', workflow);
  if (bop) params.set('bop', bop);
  if (pjFunction) params.set('pj_function', pjFunction);
  if (activeStatusFilter.value) {
    params.set('status', activeStatusFilter.value);
  }

  const query = params.toString();
  const nextUrl = query ? `/wip-overview?${query}` : '/wip-overview';
  replaceRuntimeHistory(nextUrl);
}

function applyFilters(nextFilters: typeof filters) {
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
    workflow: [],
    bop: [],
    pjFunction: [],
  });
  activeStatusFilter.value = null;
  activeMatrixFilter.value = null;
  chartSelectedPackage.value = null;
  chartSelectedStation.value = null;
  filterOrchestrator.resetAll();
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function navigateToDetail(matrixPayload: { workcenter?: string | null; package?: string | null } | null) {
  if (!matrixPayload) {
    // Toggle-off: update activeMatrixFilter only, no navigation
    activeMatrixFilter.value = null;
    return;
  }

  const workcenter = String(matrixPayload.workcenter || '').trim();
  const pkg = String(matrixPayload.package || '').trim();

  if (!workcenter) {
    activeMatrixFilter.value = matrixPayload;
    return;
  }

  activeMatrixFilter.value = matrixPayload;

  storeWipNavigationState({
    ...filters,
    matrixPackage: pkg || undefined,
  }, activeStatusFilter.value);

  const params = new URLSearchParams();
  params.set('workcenter', workcenter);
  if (pkg) {
    params.set('package', pkg);
  }
  if (activeStatusFilter.value) {
    params.set('status', activeStatusFilter.value);
  }

  navigateToRuntimeRoute(`/wip-detail?${params.toString()}`);
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

async function initializePage() {
  // Prefer sessionStorage state (returning from wip-detail), fall back to URL params
  const navState = loadWipNavigationState();
  if (navState) {
    updateFilters({
      workorder: (navState.workorder || []) as string[],
      lotid: (navState.lotid || []) as string[],
      package: (navState.package || []) as string[],
      type: (navState.type || []) as string[],
      firstname: (navState.firstname || []) as string[],
      waferdesc: (navState.waferdesc || []) as string[],
      workflow: (navState.workflow || []) as string[],
      bop: (navState.bop || []) as string[],
      pjFunction: (navState.pjFunction || []) as string[],
    });
    activeStatusFilter.value = navState.status || null;
    if (navState.matrixPackage) {
      activeMatrixFilter.value = { package: navState.matrixPackage };
    }
  } else {
    updateFilters({
      workorder: parseCsvParam('workorder'),
      lotid: parseCsvParam('lotid'),
      package: parseCsvParam('package'),
      type: parseCsvParam('type'),
      firstname: parseCsvParam('firstname'),
      waferdesc: parseCsvParam('waferdesc'),
      workflow: parseCsvParam('workflow'),
      bop: parseCsvParam('bop'),
      pjFunction: parseCsvParam('pj_function'),
    });
    activeStatusFilter.value = getUrlParam('status') || null;
  }

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
    <ErrorBanner :message="errorMessage" @dismiss="errorMessage = ''" />

    <FilterPanel
      :filters="filters"
      :options="filterOptions"
      :loading="refreshing"
      :last-update="lastUpdate"
      :refreshing="refreshing"
      :refresh-success="refreshSuccess"
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
      :active-status="activeStatusFilter ?? undefined"
      @toggle="toggleStatusFilter"
    />

    <section class="content-grid">
      <section class="card ui-card">
        <div class="card-header ui-card-header">
          <div class="card-title ui-card-title">{{ matrixTitle }}</div>
        </div>
        <div class="card-body ui-card-body matrix-container ui-table-wrap" :class="{ 'is-loading': refreshing }">
          <MatrixTable
            :data="matrix ?? undefined"
            :active-filter="activeMatrixFilter ?? undefined"
            :highlighted-package="chartSelectedPackage ?? undefined"
            :highlighted-station="chartSelectedStation ?? undefined"
            @drilldown="navigateToDetail"
          />
          <EmptyState v-if="!refreshing && !matrix" type="no-data" />
        </div>
      </section>
    </section>

    <WipDistributionCharts
      :data="matrix ?? null"
      :selected-package="chartSelectedPackage"
      :selected-station="chartSelectedStation"
      @select-package="chartSelectedPackage = $event"
      @select-station="chartSelectedStation = $event"
    />
  </div>

  <LoadingOverlay v-if="loading" tier="page" />
</template>
