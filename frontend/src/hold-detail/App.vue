<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet } from '../core/api.js';
import { navigateToRuntimeRoute, replaceRuntimeHistory, toRuntimeRoute } from '../core/shell-navigation.js';
import { NON_QUALITY_HOLD_REASON_SET } from '../wip-shared/constants.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
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

const filters = reactive({
  workcenter: null,
  package: null,
  ageRange: null,
});

const page = ref(1);
const initialLoading = ref(true);
const refreshing = ref(false);
const lotsLoading = ref(false);
const paginationLoading = ref(false);
const lotsError = ref('');
const loadError = ref('');
const lastUpdate = computed(() => {
  return summary.value?.dataUpdateDate ? `Last Update: ${summary.value.dataUpdateDate}` : '';
});

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

  if (filters.workcenter) {
    params.workcenter = filters.workcenter;
  }
  if (filters.package) {
    params.package = filters.package;
  }
  if (filters.ageRange) {
    params.age_range = filters.ageRange;
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
  if (filters.workcenter) {
    parts.push(`Workcenter=${filters.workcenter}`);
  }
  if (filters.package) {
    parts.push(`Package=${filters.package}`);
  }
  if (filters.ageRange) {
    parts.push(`Age=${filters.ageRange}天`);
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

  if (filters.workcenter) {
    params.set('workcenter', filters.workcenter);
  }
  if (filters.package) {
    params.set('package', filters.package);
  }
  if (filters.ageRange) {
    params.set('age_range', filters.ageRange);
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
  lotsLoading.value = true;
  paginationLoading.value = false;
  lotsError.value = '';
  loadError.value = '';
  refreshing.value = true;

  const signal = createAbortSignal('hold-detail-lots');

  try {
    const result = await fetchLots(signal);
    lots.value = Array.isArray(result?.lots) ? result.lots : [];
    pagination.value = {
      page: Number(result?.pagination?.page || 1),
      perPage: Number(result?.pagination?.perPage || 20),
      total: Number(result?.pagination?.total || 0),
      totalPages: Number(result?.pagination?.totalPages || 1),
    };
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    lotsError.value = error?.message || '載入 Lot 資料失敗';
  } finally {
    lotsLoading.value = false;
    refreshing.value = false;
  }
}

async function loadLotsPage() {
  const signal = createAbortSignal('hold-detail-lots');
  paginationLoading.value = true;
  lotsError.value = '';

  try {
    const result = await fetchLots(signal);
    lots.value = Array.isArray(result?.lots) ? result.lots : [];
    pagination.value = {
      page: Number(result?.pagination?.page || 1),
      perPage: Number(result?.pagination?.perPage || 20),
      total: Number(result?.pagination?.total || 0),
      totalPages: Number(result?.pagination?.totalPages || 1),
    };
  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    lotsError.value = error?.message || '載入 Lot 資料失敗';
  } finally {
    paginationLoading.value = false;
  }
}

async function loadAllData(showOverlay = true) {
  clearAbortController('hold-detail-lots');
  const signal = createAbortSignal('hold-detail-all');

  if (showOverlay) {
    initialLoading.value = true;
  }

  loadError.value = '';
  lotsError.value = '';
  refreshing.value = true;

  try {
    const [summaryData, distributionData, lotsData] = await Promise.all([
      fetchSummary(signal),
      fetchDistribution(signal),
      fetchLots(signal),
    ]);

    summary.value = summaryData;
    distribution.value = distributionData;
    lots.value = Array.isArray(lotsData?.lots) ? lotsData.lots : [];
    pagination.value = {
      page: Number(lotsData?.pagination?.page || 1),
      perPage: Number(lotsData?.pagination?.perPage || 20),
      total: Number(lotsData?.pagination?.total || 0),
      totalPages: Number(lotsData?.pagination?.totalPages || 1),
    };

  } catch (error) {
    if (error?.name === 'AbortError') {
      return;
    }
    loadError.value = error?.message || '載入資料失敗';
  } finally {
    refreshing.value = false;
    initialLoading.value = false;
  }
}

function toggleAgeFilter(range) {
  filters.ageRange = filters.ageRange === range ? null : range;
  page.value = 1;
  updateUrlState();
  void loadLots();
}

function toggleWorkcenterFilter(name) {
  filters.workcenter = filters.workcenter === name ? null : name;
  page.value = 1;
  updateUrlState();
  void loadLots();
}

function togglePackageFilter(name) {
  filters.package = filters.package === name ? null : name;
  page.value = 1;
  updateUrlState();
  void loadLots();
}

function clearFilters() {
  filters.ageRange = null;
  filters.workcenter = null;
  filters.package = null;
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
  filters.workcenter = getUrlParam('workcenter') || null;
  filters.package = getUrlParam('package') || null;
  filters.ageRange = getUrlParam('age_range') || null;
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
    <header class="header" :style="headerStyle">
      <div class="header-left">
        <a :href="backToOverviewHref" class="btn btn-back">&larr; Hold Overview</a>
        <h1>Hold Detail: {{ reason }}</h1>
        <span class="hold-type-badge">{{ holdTypeLabel }}</span>
      </div>
      <div class="header-right">
        <span class="last-update">
          <span class="refresh-indicator" :class="{ active: refreshing }"></span>
          <span>{{ lastUpdate }}</span>
        </span>
        <button type="button" class="btn btn-light" @click="manualRefresh">重新整理</button>
      </div>
    </header>

    <p v-if="loadError" class="error-banner">{{ loadError }}</p>

    <SummaryCards :summary="summary" />

    <section class="section-title">當站滯留天數分佈 (Age at Current Station)</section>
    <AgeDistribution
      :items="distribution?.byAge || []"
      :active-range="filters.ageRange"
      @toggle="toggleAgeFilter"
    />

    <section class="distribution-grid">
      <DistributionTable
        title="By Workcenter"
        :rows="distribution?.byWorkcenter || []"
        :active-name="filters.workcenter"
        @toggle="toggleWorkcenterFilter"
      />
      <DistributionTable
        title="By Package"
        :rows="distribution?.byPackage || []"
        :active-name="filters.package"
        @toggle="togglePackageFilter"
      />
    </section>

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

  <div v-if="initialLoading" class="loading-overlay">
    <span class="loading-spinner"></span>
    <span>Loading...</span>
  </div>
</template>
