<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result';
import { navigateToRuntimeRoute, replaceRuntimeHistory, toRuntimeRoute } from '../core/shell-navigation';
import { NON_QUALITY_HOLD_REASON_SET } from '../wip-shared/constants';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useRequestGuard } from '../shared-composables/useRequestGuard';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import HoldLotTable from '../wip-shared/components/HoldLotTable.vue';

import AgeDistribution from './components/AgeDistribution.vue';
import DistributionTable from './components/DistributionTable.vue';
import SummaryCards from './components/SummaryCards.vue';

// ── Local type aliases ──────────────────────────────────────────────────────
interface HoldDetailSummary {
  dataUpdateDate?: string;
  totalLots?: number;
  totalQty?: number;
  avgAge?: number;
  maxAge?: number;
  workcenterCount?: number;
  [key: string]: unknown;
}

interface AgeItem { range: string; lots: number; qty: number; percentage: number; }
interface DistributionRow { name: string; lots: number; qty: number; percentage: number; }
interface DistributionData {
  byAge?: AgeItem[];
  byWorkcenter?: DistributionRow[];
  byPackage?: DistributionRow[];
  [key: string]: unknown;
}

interface LotRecord { [key: string]: unknown; }
interface PaginationData {
  page?: number;
  perPage?: number;
  total?: number;
  totalPages?: number;
}
interface LotsResult {
  lots?: LotRecord[];
  pagination?: PaginationData;
}

const API_TIMEOUT = 60000;
const reason = ref('');

const summary = ref<HoldDetailSummary | null>(null);
const distribution = ref<DistributionData | null>(null);
const lots = ref<LotRecord[]>([]);
const pagination = ref({
  page: 1,
  perPage: 20,
  total: 0,
  totalPages: 1,
});

const page = ref(1);
const initialLoading = ref(true);
const refreshing = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const lotsLoading = ref(false);
const paginationLoading = ref(false);
const lotsError = ref('');
const loadError = ref('');

const { nextRequestId, isStaleRequest } = useRequestGuard();

// Three mutual-exclusive toggle filters via orchestrator
const orchestrator = useFilterOrchestrator({
  fields: {
    workcenter: { trigger: 'immediate', initial: null },
    package: { trigger: 'immediate', initial: null },
    ageRange: { trigger: 'immediate', initial: null },
  },
  dependencies: [
    { when: 'workcenter', then: ['package', 'ageRange'], action: 'clear' },
    { when: 'package', then: ['workcenter', 'ageRange'], action: 'clear' },
    { when: 'ageRange', then: ['workcenter', 'package'], action: 'clear' },
  ],
  pagination: { resetOn: ['*'] },
  urlSync: { enabled: false },
  onFetch: (_committed) => {
    page.value = 1;
    updateUrlState();
    void loadLots();
  },
});

const lastUpdate = computed(() => {
  return summary.value?.dataUpdateDate ?? '--';
});

function goBackToOverview() {
  navigateToRuntimeRoute('/hold-overview');
}

// unwrapApiResult imported from ../core/unwrap-api-result.js (as unwrapApiData)

async function fetchSummary(signal: AbortSignal): Promise<HoldDetailSummary> {
  const result = await apiGet('/api/wip/hold-detail/summary', {
    params: { reason: reason.value },
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch summary') as HoldDetailSummary;
}

async function fetchDistribution(signal: AbortSignal): Promise<DistributionData> {
  const result = await apiGet('/api/wip/hold-detail/distribution', {
    params: { reason: reason.value },
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch distribution') as DistributionData;
}

async function fetchLots(signal: AbortSignal): Promise<LotsResult> {
  const params: Record<string, unknown> = {
    reason: reason.value,
    page: page.value,
    per_page: pagination.value.perPage || 20,
  };

  if (orchestrator.committed.workcenter) {
    params.workcenter = orchestrator.committed.workcenter;
  }
  if (orchestrator.committed.package) {
    params.package = orchestrator.committed.package;
  }
  if (orchestrator.committed.ageRange) {
    params.age_range = orchestrator.committed.ageRange;
  }

  const result = await apiGet('/api/wip/hold-detail/lots', {
    params,
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch lots') as LotsResult;
}

const holdType = computed(() => {
  if (!reason.value) {
    return 'quality';
  }
  return NON_QUALITY_HOLD_REASON_SET.has(reason.value) ? 'non-quality' : 'quality';
});

const holdTypeLabel = computed(() => (holdType.value === 'quality' ? '品質異常' : '非品質異常'));
const backToOverviewHref = toRuntimeRoute('/hold-overview');

const headerStyle = computed(() => ({
  '--header-gradient': holdType.value === 'quality'
    ? 'linear-gradient(135deg, var(--color-token-hef4444) 0%, var(--color-token-hdc2626) 100%)'
    : 'linear-gradient(135deg, var(--color-token-hf97316) 0%, var(--color-token-hea580c) 100%)',
}));

const filterText = computed(() => {
  const parts: string[] = [];
  if (orchestrator.committed.workcenter) {
    parts.push(`Workcenter=${String(orchestrator.committed.workcenter)}`);
  }
  if (orchestrator.committed.package) {
    parts.push(`Package=${String(orchestrator.committed.package)}`);
  }
  if (orchestrator.committed.ageRange) {
    parts.push(`Age=${String(orchestrator.committed.ageRange)}天`);
  }
  return parts.join(', ');
});

const hasActiveFilters = computed(() => Boolean(filterText.value));

// Template-safe accessors for orchestrator.committed (typed as Record<string, unknown>)
const committedAgeRange = computed<string | undefined>(() => {
  const v = orchestrator.committed.ageRange;
  return v != null ? String(v) : undefined;
});
const committedWorkcenter = computed<string | undefined>(() => {
  const v = orchestrator.committed.workcenter;
  return v != null ? String(v) : undefined;
});
const committedPackage = computed<string | undefined>(() => {
  const v = orchestrator.committed.package;
  return v != null ? String(v) : undefined;
});

function getUrlParam(name: string): string {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function updateUrlState() {
  if (!reason.value) {
    return;
  }

  const params = new URLSearchParams();
  params.set('reason', reason.value);

  if (orchestrator.committed.workcenter) {
    params.set('workcenter', String(orchestrator.committed.workcenter));
  }
  if (orchestrator.committed.package) {
    params.set('package', String(orchestrator.committed.package));
  }
  if (orchestrator.committed.ageRange) {
    params.set('age_range', String(orchestrator.committed.ageRange));
  }
  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/hold-detail?${params.toString()}`);
}

const { createAbortSignal, clearAbortController, resetAutoRefresh, triggerRefresh } = useAutoRefresh({
  onRefresh: () => loadAllData(false),
  autoStart: true,
});

async function loadLots() {
  const requestId = nextRequestId();
  lotsLoading.value = true;
  paginationLoading.value = false;
  lotsError.value = '';
  loadError.value = '';
  refreshing.value = true;

  const signal = createAbortSignal('hold-detail-lots');

  try {
    const result = await fetchLots(signal);
    if (isStaleRequest(requestId)) {
      return;
    }
    lots.value = Array.isArray(result?.lots) ? result.lots : [];
    pagination.value = {
      page: Number(result?.pagination?.page ?? 1),
      perPage: Number(result?.pagination?.perPage ?? 20),
      total: Number(result?.pagination?.total ?? 0),
      totalPages: Number(result?.pagination?.totalPages ?? 1),
    };
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
    lotsLoading.value = false;
    refreshing.value = false;
  }
}

async function loadLotsPage() {
  const requestId = nextRequestId();
  const signal = createAbortSignal('hold-detail-lots');
  paginationLoading.value = true;
  lotsError.value = '';

  try {
    const result = await fetchLots(signal);
    if (isStaleRequest(requestId)) {
      return;
    }
    lots.value = Array.isArray(result?.lots) ? result.lots : [];
    pagination.value = {
      page: Number(result?.pagination?.page ?? 1),
      perPage: Number(result?.pagination?.perPage ?? 20),
      total: Number(result?.pagination?.total ?? 0),
      totalPages: Number(result?.pagination?.totalPages ?? 1),
    };
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

async function loadAllData(showOverlay = true) {
  const requestId = nextRequestId();
  clearAbortController('hold-detail-lots');
  const signal = createAbortSignal('hold-detail-all');

  if (showOverlay) {
    initialLoading.value = true;
  }

  loadError.value = '';
  lotsError.value = '';
  refreshing.value = true;
  refreshError.value = false;

  try {
    const [summaryData, distributionData, lotsData] = await Promise.all([
      fetchSummary(signal),
      fetchDistribution(signal),
      fetchLots(signal),
    ]);
    if (isStaleRequest(requestId)) {
      return;
    }

    summary.value = summaryData;
    distribution.value = distributionData;
    lots.value = Array.isArray(lotsData?.lots) ? lotsData.lots : [];
    pagination.value = {
      page: Number(lotsData?.pagination?.page ?? 1),
      perPage: Number(lotsData?.pagination?.perPage ?? 20),
      total: Number(lotsData?.pagination?.total ?? 0),
      totalPages: Number(lotsData?.pagination?.totalPages ?? 1),
    };

    refreshSuccess.value = true;
    setTimeout(() => { refreshSuccess.value = false; }, 1500);
  } catch (err: unknown) {
    const error = err as { name?: string; message?: string };
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    loadError.value = error?.message ?? '載入資料失敗';
    refreshError.value = true;
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    refreshing.value = false;
    initialLoading.value = false;
  }
}

function toggleAgeFilter(range: string) {
  const next = orchestrator.committed.ageRange === range ? null : range;
  orchestrator.updateField('ageRange', next);
}

function toggleWorkcenterFilter(name: string) {
  const next = orchestrator.committed.workcenter === name ? null : name;
  orchestrator.updateField('workcenter', next);
}

function togglePackageFilter(name: string) {
  const next = orchestrator.committed.package === name ? null : name;
  orchestrator.updateField('package', next);
}

function clearFilters() {
  orchestrator.resetAll();
  page.value = 1;
  updateUrlState();
  void loadLots();
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
  if (paginationLoading.value || page.value >= pagination.value.totalPages) {
    return;
  }
  page.value += 1;
  updateUrlState();
  void loadLotsPage();
}

async function manualRefresh() {
  await triggerRefresh({ resetTimer: true, force: true });
}

onMounted(() => {
  reason.value = getUrlParam('reason');

  // Initialize orchestrator committed state directly (no fetch during init)
  const initWorkcenter = getUrlParam('workcenter') || null;
  const initPackage = getUrlParam('package') || null;
  const initAgeRange = getUrlParam('age_range') || null;
  orchestrator.committed.workcenter = initWorkcenter;
  orchestrator.draft.workcenter = initWorkcenter;
  orchestrator.committed.package = initPackage;
  orchestrator.draft.package = initPackage;
  orchestrator.committed.ageRange = initAgeRange;
  orchestrator.draft.ageRange = initAgeRange;

  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }

  if (!reason.value) {
    navigateToRuntimeRoute('/hold-overview', { replace: true });
    return;
  }
  updateUrlState();
  void loadAllData(true);
});
</script>

<template>
  <div class="dashboard hold-detail-page theme-hold-detail">
    <div class="hold-detail-nav">
      <div class="hold-detail-nav-left">
        <a
          :href="backToOverviewHref"
          class="ui-btn ui-btn--ghost ui-btn--sm hold-detail-back-btn"
          @click.prevent="goBackToOverview"
        >&larr; Hold Overview</a>
        <h1 class="hold-detail-title">Hold Detail: <span class="hold-detail-reason">{{ reason }}</span></h1>
        <span class="hold-type-badge" :class="holdType">{{ holdTypeLabel }}</span>
      </div>
      <div class="hold-detail-nav-right">
        <span v-if="refreshing" class="refresh-indicator active"></span>
        <span v-else-if="refreshSuccess" class="refresh-success active">&#10003;</span>
        <span class="hold-detail-last-update">更新: {{ lastUpdate }}</span>
        <button
          type="button"
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :disabled="refreshing"
          @click="manualRefresh"
        >&#8635; 更新</button>
      </div>
    </div>

    <ErrorBanner :message="loadError" :dismissible="false" />

    <SummaryCards :summary="summary ?? undefined" />

    <section class="section-title">當站滯留天數分佈 (Age at Current Station)</section>
    <AgeDistribution
      :items="distribution?.byAge || []"
      :active-range="committedAgeRange"
      @toggle="toggleAgeFilter"
    />

    <section class="distribution-grid">
      <DistributionTable
        title="By Workcenter"
        :rows="distribution?.byWorkcenter || []"
        :active-name="committedWorkcenter"
        @toggle="toggleWorkcenterFilter"
      />
      <DistributionTable
        title="By Package"
        :rows="distribution?.byPackage || []"
        :active-name="committedPackage"
        @toggle="togglePackageFilter"
      />
    </section>

    <div class="ui-table-wrap" :class="{ 'is-loading': lotsLoading }">
      <HoldLotTable
        :lots="lots"
        :pagination="pagination"
        :loading="lotsLoading"
        :paginating="paginationLoading"
        :error-message="lotsError"
        :has-active-filters="hasActiveFilters"
        :filter-text="filterText"
        title="Lot Details"
        @clear-filters="clearFilters"
        @prev-page="prevPage"
        @next-page="nextPage"
      />
    </div>
  </div>

  <LoadingOverlay v-if="initialLoading || refreshing" tier="page" />
</template>
