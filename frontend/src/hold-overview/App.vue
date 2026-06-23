<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation';
import { storeHoldNavigationState, loadHoldNavigationState } from '../core/hold-navigation-state';
import { buildWipOverviewQueryParams, splitHoldByType } from '../core/wip-derive';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh';
import { bindUpdateBadge } from '../shared-composables/usePageUpdateBadge';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useRequestGuard } from '../shared-composables/useRequestGuard';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import SkeletonLoader from '../shared-ui/components/SkeletonLoader.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import ParetoSection from '../wip-shared/components/ParetoSection.vue';

import FilterPanel from '../wip-overview/components/FilterPanel.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import HoldMatrix from './components/HoldMatrix.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import { _buildCsv, _downloadCsv } from './csvExport';

// ── Local type aliases ──────────────────────────────────────────────────────
interface HoldOverviewSummary {
  dataUpdateDate?: string;
  totalLots?: number;
  totalQty?: number;
  avgAge?: number;
  maxAge?: number;
  workcenterCount?: number;
  reason_options?: string[];
  reasonOptions?: string[];
  topReasons?: string[];
  by_reason?: Record<string, unknown>;
  byReason?: Record<string, unknown>;
  [key: string]: unknown;
}

interface MatrixFilter {
  workcenter?: string | null;
  package?: string | null;
}

interface LotRecord { [key: string]: unknown; }
interface PaginationState { page: number; perPage: number; total: number; totalPages: number; }
interface LotsResult { lots?: LotRecord[]; pagination?: Partial<PaginationState>; }

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 20;

const summary = ref<HoldOverviewSummary | null>(null);
const matrix = ref<Record<string, unknown> | null>(null);
const hold = ref<unknown>(null);
const lots = ref<LotRecord[]>([]);

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

const matrixFilter = ref<MatrixFilter | null>(null);

const pagination = ref({
  page: 1,
  perPage: DEFAULT_PER_PAGE,
  total: 0,
  totalPages: 1,
});
const page = ref(1);

const initialLoading = ref(true);
const lotsLoading = ref(false);
const paginationLoading = ref(false);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const errorMessage = ref('');
const lotsError = ref('');
const exportLoading = ref(false);

const { nextRequestId, isStaleRequest } = useRequestGuard();

// Panel filters kept as reactive for FilterPanel compatibility
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

// --- useFilterOrchestrator for holdType + reason (FilterBar) ---
const orchestrator = useFilterOrchestrator({
  fields: {
    holdType: { trigger: 'immediate', initial: 'quality' },
    reason: { trigger: 'immediate', initial: [] },
  },
  dependencies: [
    { when: 'holdType', then: ['reason'], action: 'reload-options' },
  ],
  pagination: { resetOn: ['*'] },
  urlSync: { enabled: false },
  onFetch: (_committed) => {
    matrixFilter.value = null;
    page.value = 1;
    updateUrlState();
    void loadFilterOptions(filters);
    void loadAllData(false);
  },
  onLoadOptions: async (_fieldName: string, _committed: Record<string, unknown>) => {
    // reason options are derived from summary, reload via summary fetch
    return [];
  },
});

const holdTypeLabel = computed(() => {
  const ht = orchestrator.committed.holdType;
  if (ht === 'non-quality') {
    return '非品質異常';
  }
  if (ht === 'all') {
    return '全部';
  }
  return '品質異常';
});

const showQualityPareto = computed(() => orchestrator.committed.holdType !== 'non-quality');
const showNonQualityPareto = computed(() => orchestrator.committed.holdType !== 'quality');

const lotFilterText = computed(() => {
  const parts: string[] = [];
  if (matrixFilter.value?.workcenter) {
    parts.push(`Workcenter=${matrixFilter.value.workcenter}`);
  }
  if (matrixFilter.value?.package) {
    parts.push(`Package=${matrixFilter.value.package}`);
  }
  return parts.join(', ');
});


const hasLotFilterText = computed(() => Boolean(lotFilterText.value));

const tablePagination = computed(() => {
  const pg = pagination.value;
  const p = Number(pg?.page || 1);
  const perPage = Number(pg?.perPage || DEFAULT_PER_PAGE);
  const total = Number(pg?.total || 0);
  const totalPages = Number(pg?.totalPages || 1);
  const start = total > 0 ? (p - 1) * perPage + 1 : 0;
  const end = Math.min(p * perPage, total);
  const infoText = total > 0 ? `${start} - ${end} / ${total.toLocaleString('zh-TW')}` : 'No data';
  return { page: p, totalPages, infoText };
});

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '-') return '-';
  return Number(value).toLocaleString('zh-TW');
}

function formatAge(value: unknown): string {
  if (value === null || value === undefined || value === '-') return '-';
  return `${value}天`;
}

function handleLotPageChange(nextPage: number) {
  if (paginationLoading.value) return;
  if (nextPage < 1 || nextPage > Number(pagination.value?.totalPages || 1)) return;
  page.value = nextPage;
  updateUrlState();
  void loadLotsPage();
}

const lastUpdate = computed(() => {
  return summary.value?.dataUpdateDate ?? '--';
});

bindUpdateBadge({ updateTime: lastUpdate, refreshing, refreshSuccess });

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

const splitHold = computed(() => splitHoldByType(hold.value as Record<string, unknown> | null));

// Template-safe accessors for orchestrator.committed (typed as Record<string, unknown>)
const committedHoldType = computed<string>(() => String(orchestrator.committed.holdType || 'all'));
const committedReason = computed<string[]>(() => {
  const r = orchestrator.committed.reason;
  return Array.isArray(r) ? (r as string[]) : [];
});

let filterOptionsDebounceTimer: ReturnType<typeof setTimeout> | null = null;
let filterOptionsRequestToken = 0;

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
  return normalizeArrayValues(values).join(',');
}

function normalizeHoldType(value: unknown): string {
  const holdType = String(value || '').trim();
  if (holdType === 'quality' || holdType === 'non-quality' || holdType === 'all') {
    return holdType;
  }
  return 'all';
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
}

function buildFilterBarParams(): Record<string, unknown> {
  const params: Record<string, unknown> = {
    hold_type: orchestrator.committed.holdType || 'all',
  };
  const reasonCsv = serializeFilterValue(orchestrator.committed.reason as string | string[] | undefined);
  if (reasonCsv) {
    params.reason = reasonCsv;
  }
  return params;
}

function buildMatrixFilterParams(): Record<string, unknown> {
  const params: Record<string, unknown> = {};
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

function buildFilterOptionsParams(sourceFilters = filters): Record<string, unknown> {
  const params: Record<string, unknown> = {
    ...buildWipOverviewQueryParams(sourceFilters),
    status: 'HOLD',
  };

  const ht = orchestrator.committed.holdType;
  if (ht && ht !== 'all') {
    params.hold_type = ht;
  }

  return params;
}

async function fetchSummary(signal: AbortSignal): Promise<HoldOverviewSummary> {
  const result = await apiPost('/api/hold-overview/summary', buildAllFilterParams(), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold summary') as HoldOverviewSummary;
}

async function fetchMatrix(signal: AbortSignal): Promise<Record<string, unknown>> {
  const result = await apiPost('/api/hold-overview/matrix', buildAllFilterParams(), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold matrix') as Record<string, unknown>;
}

async function fetchHold(signal: AbortSignal, extraParams: Record<string, unknown> = {}): Promise<unknown> {
  const result = await apiPost('/api/wip/overview/hold', { ...buildAllFilterParams(), ...extraParams }, {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold data');
}

async function fetchLots(signal: AbortSignal): Promise<LotsResult> {
  const result = await apiPost('/api/hold-overview/lots', buildLotsParams(), {
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch hold lots') as LotsResult;
}

async function loadFilterOptions(sourceFilters = filters): Promise<void> {
  const requestToken = ++filterOptionsRequestToken;

  try {
    const result = await apiGet('/api/wip/meta/filter-options', {
      params: buildFilterOptionsParams(sourceFilters),
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
  }, 120);
}

function onFilterDraftChange(nextDraftFilters: typeof filters): void {
  scheduleFilterOptionsReload(nextDraftFilters);
}

function updateLotsState(payload: LotsResult): void {
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

  const ht = orchestrator.committed.holdType;
  if (ht) {
    params.set('hold_type', String(ht));
  }
  const reasonCsv = serializeFilterValue(orchestrator.committed.reason as string[] | undefined);
  if (reasonCsv) {
    params.set('reason', reasonCsv);
  }
  if (matrixFilter.value?.workcenter) {
    params.set('workcenter', matrixFilter.value.workcenter ?? '');
  }
  if (matrixFilter.value?.package) {
    params.set('matrix_package', matrixFilter.value.package ?? '');
  }

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
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    refreshError.value = true;
    const message = error?.message ?? '載入資料失敗';
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
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    refreshError.value = true;
    const message = error?.message ?? '載入 Lot 資料失敗';
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

async function loadLotsPage() {
  const requestId = nextRequestId();
  clearAbortController('hold-overview-all');
  const signal = createAbortSignal('hold-overview-lots');

  paginationLoading.value = true;
  lotsError.value = '';

  try {
    const lotsData = await fetchLots(signal);
    if (isStaleRequest(requestId)) {
      return;
    }
    updateLotsState(lotsData);
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    lotsError.value = error?.message ?? '載入 Lot 資料失敗';
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    paginationLoading.value = false;
  }
}

function navigateToHoldDetail(reason: string) {
  if (!reason) {
    return;
  }
  storeHoldNavigationState(
    (orchestrator.committed.holdType as string) || 'quality',
    (orchestrator.committed.reason as string[]) || [],
    matrixFilter.value?.workcenter ?? null,
    matrixFilter.value?.package ?? null,
    {
      workorder: filters.workorder,
      lotid: filters.lotid,
      package: filters.package,
      type: filters.type,
      firstname: filters.firstname,
      waferdesc: filters.waferdesc,
      workflow: filters.workflow,
      bop: filters.bop,
      pjFunction: filters.pjFunction,
    },
  );
  const urlParams = new URLSearchParams();
  urlParams.set('reason', reason);
  if (matrixFilter.value?.workcenter) {
    urlParams.set('workcenter', matrixFilter.value.workcenter);
  }
  if (matrixFilter.value?.package) {
    urlParams.set('package', matrixFilter.value.package);
  }
  navigateToRuntimeRoute(`/hold-detail?${urlParams.toString()}`);
}

function handleFilterChange(next: { holdType?: string; reason?: string[] }) {
  const nextHoldType = normalizeHoldType(next?.holdType || 'all');
  const nextReason = normalizeArrayValues(next?.reason);

  const currentReasonCsv = serializeFilterValue(orchestrator.committed.reason as string[] | undefined);
  const nextReasonCsv = serializeFilterValue(nextReason);
  if (orchestrator.committed.holdType === nextHoldType && currentReasonCsv === nextReasonCsv) {
    return;
  }

  // Batch both fields before triggering a single fetch to avoid double API calls
  orchestrator.committed.holdType = nextHoldType;
  orchestrator.committed.reason = nextReason;
  orchestrator.draft.holdType = nextHoldType;
  orchestrator.draft.reason = nextReason;

  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function handleMatrixSelect(nextFilter: MatrixFilter | null) {
  matrixFilter.value = nextFilter;
  page.value = 1;
  updateUrlState();
  void loadLotsAndHold();
}

function clearMatrixFilter() {
  if (!matrixFilter.value) {
    return;
  }
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadLotsAndHold();
}

async function loadLotsAndHold() {
  const requestId = nextRequestId();
  clearAbortController('hold-overview-all');
  const signal = createAbortSignal('hold-overview-lots');

  refreshing.value = true;
  lotsLoading.value = true;
  refreshError.value = false;
  errorMessage.value = '';
  lotsError.value = '';

  try {
    const [lotsData, holdData] = await Promise.all([
      fetchLots(signal),
      fetchHold(signal, buildMatrixFilterParams()),
    ]);
    if (isStaleRequest(requestId)) return;
    updateLotsState(lotsData);
    hold.value = holdData;
    showRefreshSuccess();
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) return;
    refreshError.value = true;
    const message = error?.message ?? '載入資料失敗';
    errorMessage.value = message;
    lotsError.value = message;
  } finally {
    if (isStaleRequest(requestId)) return;
    refreshing.value = false;
    lotsLoading.value = false;
  }
}

function applyFilters(nextFilters: typeof filters) {
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
    workflow: [],
    bop: [],
    pjFunction: [],
  });
  matrixFilter.value = null;
  page.value = 1;
  updateUrlState();
  void loadFilterOptions(filters);
  void loadAllData(false);
}

function prevPage() {
  if (paginationLoading.value || page.value <= 1) {
    return;
  }
  page.value -= 1;
  updateUrlState();
  void loadLotsPage();
}

function nextPage() {
  if (paginationLoading.value || page.value >= Number(pagination.value?.totalPages || 1)) {
    return;
  }
  page.value += 1;
  updateUrlState();
  void loadLotsPage();
}

async function exportLots(): Promise<void> {
  if (exportLoading.value) return;
  exportLoading.value = true;
  try {
    const params = {
      ...buildAllFilterParams(),
      ...buildMatrixFilterParams(),
      export: true,
    };
    const result = await apiPost('/api/hold-overview/lots', params, { timeout: API_TIMEOUT });
    const data = unwrapApiResult(result, '匯出失敗') as { lots?: Record<string, unknown>[] };
    const rows = Array.isArray(data?.lots) ? data.lots : [];
    const dateStr = new Date().toISOString().slice(0, 10);
    _downloadCsv(_buildCsv(rows), `hold-overview-${dateStr}.csv`);
  } catch (err: unknown) {
    console.error('[hold-overview] CSV export failed:', err);
    lotsError.value = 'CSV 匯出失敗，請稍後再試';
  } finally {
    exportLoading.value = false;
  }
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

async function initializePage() {
  // Prefer sessionStorage state (returning from hold-detail), fall back to URL params
  const navState = loadHoldNavigationState();

  let initialHoldType: string;
  let initialReason: string[];

  if (navState) {
    initialHoldType = normalizeHoldType(navState.holdType || 'quality');
    initialReason = navState.reason || [];
    if (navState.workcenter || navState.matrixPackage) {
      matrixFilter.value = {
        workcenter: navState.workcenter || null,
        package: navState.matrixPackage || null,
      };
    }
  } else {
    initialHoldType = normalizeHoldType(getUrlParam('hold_type') || 'quality');
    initialReason = parseCsvParam('reason');
    const workcenter = getUrlParam('workcenter');
    const matrixPkg = getUrlParam('matrix_package');
    if (workcenter || matrixPkg) {
      matrixFilter.value = {
        workcenter: workcenter || null,
        package: matrixPkg || null,
      };
    }
  }

  // Set orchestrator committed state directly (no fetch triggered during init)
  orchestrator.committed.holdType = initialHoldType;
  orchestrator.draft.holdType = initialHoldType;
  orchestrator.committed.reason = initialReason;
  orchestrator.draft.reason = initialReason;

  if (navState) {
    // Restore FilterPanel state from sessionStorage (panel filters not in URL on return)
    updateFilters({
      workorder: navState.workorder || [],
      lotid: navState.lotid || [],
      package: navState.package || [],
      type: navState.type || [],
      firstname: navState.firstname || [],
      waferdesc: navState.waferdesc || [],
      workflow: navState.workflow || [],
      bop: navState.bop || [],
      pjFunction: navState.pjFunction || [],
    });
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
  <div class="dashboard hold-overview-page theme-hold-overview">
    <ErrorBanner :message="errorMessage" @dismiss="errorMessage = ''" />

    <FilterPanel
      :filters="filters"
      :options="filterOptions"
      :loading="refreshing"
      :last-update="lastUpdate"
      :refreshing="refreshing"
      :refresh-success="refreshSuccess"
      @apply="applyFilters"
      @clear="clearAllFilters"
      @draft-change="onFilterDraftChange"
    />

    <FilterBar
      :hold-type="committedHoldType"
      :reason="committedReason"
      :reasons="reasonOptions"
      :disabled="refreshing && initialLoading"
      @change="handleFilterChange"
    />

    <template v-if="initialLoading">
      <div class="space-y-4">
        <SkeletonLoader type="card" :rows="4" />
        <SkeletonLoader type="table" :rows="6" />
      </div>
    </template>
    <template v-else>
      <SummaryCardGroup :columns="5">
        <SummaryCard
          label="Total Lots"
          :value="summary?.totalLots"
          format="number"
          accent="brand"
        />
        <SummaryCard
          label="Total QTY"
          :value="summary?.totalQty"
          format="number"
          accent="info"
        />
        <SummaryCard
          label="平均當站滯留"
          :value="summary?.avgAge"
          format="duration"
          accent="warning"
        >
          <template #sub>天</template>
        </SummaryCard>
        <SummaryCard
          label="最久當站滯留"
          :value="summary?.maxAge"
          format="duration"
          accent="danger"
        >
          <template #sub>天</template>
        </SummaryCard>
        <SummaryCard
          label="影響站群"
          :value="summary?.workcenterCount"
          format="number"
          accent="neutral"
        />
      </SummaryCardGroup>

      <section class="content-grid">
      <section class="card ui-card">
        <div class="card-header ui-card-header">
          <div class="card-title ui-card-title">Workcenter x Package Matrix (QTY)</div>
        </div>
        <div class="card-body ui-card-body matrix-container">
          <HoldMatrix :data="matrix ?? undefined" :active-filter="matrixFilter ?? undefined" @select="handleMatrixSelect" />
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
        :matrix-filter="matrixFilter ?? undefined"
        :show-clear-all="true"
        @clear-matrix="clearMatrixFilter"
        @clear-all="clearMatrixFilter"
      />

      <section class="card ui-card">
        <div class="card-header ui-card-header">
          <div class="card-title ui-card-title">Hold Lot Details</div>
          <div class="flex items-center gap-3 ml-auto">
            <button
              v-if="hasLotFilterText"
              type="button"
              class="hold-filter-chip"
              @click="clearMatrixFilter"
            >
              <span class="hold-filter-chip__text">{{ lotFilterText }}</span>
              <span class="hold-filter-chip__x" aria-hidden="true">✕</span>
            </button>
            <button
              type="button"
              class="ui-btn ui-btn--secondary ui-btn--sm"
              :class="{ 'is-loading': exportLoading }"
              :disabled="exportLoading || lotsLoading || pagination.total === 0"
              @click="exportLots"
            >
              <LoadingSpinner v-if="exportLoading" size="sm" aria-hidden="true" />
              {{ exportLoading ? '匯出中...' : '↓ 匯出 CSV' }}
            </button>
          </div>
        </div>
        <div class="card-body ui-card-body lots-card-body">
          <ErrorBanner :message="lotsError" @dismiss="lotsError = ''" />
          <DataTable
            :data="lots"
            :loading="lotsLoading"
            :pagination="tablePagination"
            @page-change="handleLotPageChange"
          >
            <DataTableColumn column-key="lotId" label="LOTID" sortable />
            <DataTableColumn column-key="workorder" label="WORKORDER" sortable />
            <DataTableColumn column-key="qty" label="QTY" sortable align="right" />
            <DataTableColumn column-key="product" label="Product" sortable />
            <DataTableColumn column-key="package" label="Package" sortable />
            <DataTableColumn column-key="workcenter" label="Workcenter" sortable />
            <DataTableColumn column-key="holdReason" label="Hold Reason" sortable />
            <DataTableColumn column-key="spec" label="Spec" sortable />
            <DataTableColumn column-key="age" label="Age" sortable align="right" />
            <DataTableColumn column-key="holdBy" label="Hold By" sortable />
            <DataTableColumn column-key="dept" label="Dept" sortable />
            <DataTableColumn column-key="holdComment" label="Hold Comment" sortable />
            <DataTableColumn column-key="futureHoldComment" label="Future Hold Comment" sortable />
            <template #cell="{ columnKey, row, value }">
              <template v-if="columnKey === 'qty'">{{ formatNumber(value) }}</template>
              <template v-else-if="columnKey === 'age'">{{ formatAge(value) }}</template>
              <template v-else>{{ value || '-' }}</template>
            </template>
          </DataTable>
        </div>
      </section>
      </section>
    </template>
  </div>

  <LoadingOverlay v-if="refreshing && !initialLoading" tier="page" />
</template>
