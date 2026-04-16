<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result.js';
import { navigateToRuntimeRoute, replaceRuntimeHistory, toRuntimeRoute } from '../core/shell-navigation.js';
import { NON_QUALITY_HOLD_REASON_SET } from '../wip-shared/constants.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';
import { useRequestGuard } from '../shared-composables/useRequestGuard.js';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import HoldLotTable from '../wip-shared/components/HoldLotTable.vue';

import AgeDistribution from './components/AgeDistribution.vue';
import DistributionTable from './components/DistributionTable.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 60000;
const reason = ref('');

const summary = ref(null);
const distribution = ref(null);
const lots = ref([]);
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

async function fetchSummary(signal) {
  const result = await apiGet('/api/wip/hold-detail/summary', {
    params: { reason: reason.value },
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch summary');
}

async function fetchDistribution(signal) {
  const result = await apiGet('/api/wip/hold-detail/distribution', {
    params: { reason: reason.value },
    timeout: API_TIMEOUT,
    signal,
  });
  return unwrapApiResult(result, 'Failed to fetch distribution');
}

async function fetchLots(signal) {
  const params = {
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
  return unwrapApiResult(result, 'Failed to fetch lots');
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
  const parts = [];
  if (orchestrator.committed.workcenter) {
    parts.push(`Workcenter=${orchestrator.committed.workcenter}`);
  }
  if (orchestrator.committed.package) {
    parts.push(`Package=${orchestrator.committed.package}`);
  }
  if (orchestrator.committed.ageRange) {
    parts.push(`Age=${orchestrator.committed.ageRange}天`);
  }
  return parts.join(', ');
});

const hasActiveFilters = computed(() => Boolean(filterText.value));

function getUrlParam(name) {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function updateUrlState() {
  if (!reason.value) {
    return;
  }

  const params = new URLSearchParams();
  params.set('reason', reason.value);

  if (orchestrator.committed.workcenter) {
    params.set('workcenter', orchestrator.committed.workcenter);
  }
  if (orchestrator.committed.package) {
    params.set('package', orchestrator.committed.package);
  }
  if (orchestrator.committed.ageRange) {
    params.set('age_range', orchestrator.committed.ageRange);
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
      page: Number(result?.pagination?.page || 1),
      perPage: Number(result?.pagination?.perPage || 20),
      total: Number(result?.pagination?.total || 0),
      totalPages: Number(result?.pagination?.totalPages || 1),
    };
  } catch (error) {
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    lotsError.value = error?.message || '載入 Lot 資料失敗';
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
      page: Number(result?.pagination?.page || 1),
      perPage: Number(result?.pagination?.perPage || 20),
      total: Number(result?.pagination?.total || 0),
      totalPages: Number(result?.pagination?.totalPages || 1),
    };
  } catch (error) {
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    lotsError.value = error?.message || '載入 Lot 資料失敗';
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
      page: Number(lotsData?.pagination?.page || 1),
      perPage: Number(lotsData?.pagination?.perPage || 20),
      total: Number(lotsData?.pagination?.total || 0),
      totalPages: Number(lotsData?.pagination?.totalPages || 1),
    };

    refreshSuccess.value = true;
    setTimeout(() => { refreshSuccess.value = false; }, 1500);
  } catch (error) {
    if (error?.name === 'AbortError' || isStaleRequest(requestId)) {
      return;
    }
    loadError.value = error?.message || '載入資料失敗';
    refreshError.value = true;
  } finally {
    if (isStaleRequest(requestId)) {
      return;
    }
    refreshing.value = false;
    initialLoading.value = false;
  }
}

function toggleAgeFilter(range) {
  const next = orchestrator.committed.ageRange === range ? null : range;
  orchestrator.updateField('ageRange', next);
}

function toggleWorkcenterFilter(name) {
  const next = orchestrator.committed.workcenter === name ? null : name;
  orchestrator.updateField('workcenter', next);
}

function togglePackageFilter(name) {
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
    <PageHeader
      :title="`Hold Detail: ${reason}`"
      :last-update="lastUpdate"
      :refreshing="refreshing"
      :refresh-success="refreshSuccess"
      :refresh-error="refreshError"
      :style="headerStyle"
      @refresh="manualRefresh"
    >
      <template #header-left>
        <a
          :href="backToOverviewHref"
          class="ui-btn ui-btn--ghost btn-back"
          @click.prevent="goBackToOverview"
        >&larr; Hold Overview</a>
      </template>
      <template #header-left-after>
        <span class="hold-type-badge">{{ holdTypeLabel }}</span>
      </template>
    </PageHeader>

    <ErrorBanner :message="loadError" :dismissible="false" />

    <SummaryCards :summary="summary" />

    <section class="section-title">當站滯留天數分佈 (Age at Current Station)</section>
    <AgeDistribution
      :items="distribution?.byAge || []"
      :active-range="orchestrator.committed.ageRange"
      @toggle="toggleAgeFilter"
    />

    <section class="distribution-grid">
      <DistributionTable
        title="By Workcenter"
        :rows="distribution?.byWorkcenter || []"
        :active-name="orchestrator.committed.workcenter"
        @toggle="toggleWorkcenterFilter"
      />
      <DistributionTable
        title="By Package"
        :rows="distribution?.byPackage || []"
        :active-name="orchestrator.committed.package"
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
