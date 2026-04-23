<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result.js';
import { checkLocalComputeEligibility } from '../core/duckdb-activation-policy.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';
import { useRequestGuard } from '../shared-composables/useRequestGuard.js';
import { useHoldHistoryDuckDB } from './useHoldHistoryDuckDB.js';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';

import DailyTrend from './components/DailyTrend.vue';
import DetailTable from './components/DetailTable.vue';
import DurationChart from './components/DurationChart.vue';
import FilterBar from './components/FilterBar.vue';
import FilterIndicator from './components/FilterIndicator.vue';
import RecordTypeFilter from './components/RecordTypeFilter.vue';
import ReasonPareto from './components/ReasonPareto.vue';
import SummaryCards from './components/SummaryCards.vue';

const API_TIMEOUT = 360000;
const DEFAULT_PER_PAGE = 20;

const queryId = ref('');

// ── DuckDB local compute (Tasks 4.2–4.4) ─────────────────────────────────────
const duckdb = useHoldHistoryDuckDB();

const trendData = ref({ days: [] });
const reasonParetoData = ref({ items: [] });
const durationData = ref({ items: [] });
const detailData = ref({
  items: [],
  pagination: {
    page: 1,
    perPage: DEFAULT_PER_PAGE,
    total: 0,
    totalPages: 1,
  },
});

const page = ref(1);
const initialLoading = ref(true);
const paginationLoading = ref(false);
const refreshSuccess = ref(false);
const refreshError = ref(false);
const loading = reactive({
  global: false,
  primaryQuery: false,
  list: false,
});

const errorMessage = ref('');
const { nextRequestId, isStaleRequest } = useRequestGuard();

// --- useFilterOrchestrator for two-phase query ---
// Date fields: draft-apply -> executePrimaryQuery
// holdType: immediate -> refreshView
// recordType, reasonFilter, durationFilter: immediate -> refreshView
const orchestrator = useFilterOrchestrator({
  fields: {
    startDate: { trigger: 'draft-apply', initial: '' },
    endDate: { trigger: 'draft-apply', initial: '' },
    holdType: { trigger: 'immediate', initial: 'quality' },
    recordType: { trigger: 'immediate', initial: ['new'] },
    reasonFilter: { trigger: 'immediate', initial: '' },
    durationFilter: { trigger: 'immediate', initial: '' },
  },
  dependencies: [
    // holdType change -> clear reason and duration, reset recordType to ['new']
    { when: 'holdType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
    { when: 'holdType', then: ['recordType'], action: 'reset', value: ['new'] },
    // recordType change -> clear reason and duration
    { when: 'recordType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
  ],
  pagination: { resetOn: ['*'] },
  urlSync: { enabled: false },
  onFetch: (_committed) => {
    // Immediate field changed -> view refresh (supplementary, reads from cache)
    page.value = 1;
    updateUrlState();
    void refreshView();
  },
  onPrimaryQuery: (_committed) => {
    // Date apply -> primary query
    page.value = 1;
    updateUrlState();
    void executePrimaryQuery();
  },
});

function toDateString(value) {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function getUrlParam(name) {
  return new URLSearchParams(window.location.search).get(name)?.trim() || '';
}

function normalizeHoldType(value) {
  const holdType = String(value || '').trim();
  if (holdType === 'quality' || holdType === 'non-quality' || holdType === 'all') {
    return holdType;
  }
  return 'quality';
}

function parseRecordTypeCsv(value) {
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length > 0 ? [...new Set(parsed)] : ['new'];
}

function setDefaultDateRange() {
  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth();

  if (now.getDate() === 1) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
  }

  const start = new Date(year, month, 1);
  const end = new Date(year, month + 1, 0);
  orchestrator.committed.startDate = toDateString(start);
  orchestrator.draft.startDate = toDateString(start);
  orchestrator.committed.endDate = toDateString(end);
  orchestrator.draft.endDate = toDateString(end);
}

// unwrapApiResult imported from ../core/unwrap-api-result.js (as unwrapApiData)

function normalizeListPayload(payload) {
  const pagination = payload?.pagination || {};
  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    pagination: {
      page: Number(pagination.page || page.value || 1),
      perPage: Number(pagination.perPage || DEFAULT_PER_PAGE),
      total: Number(pagination.total || 0),
      totalPages: Number(pagination.totalPages || 1),
    },
  };
}

function updateUrlState() {
  const params = new URLSearchParams();

  if (orchestrator.committed.startDate) {
    params.set('start_date', orchestrator.committed.startDate);
  }
  if (orchestrator.committed.endDate) {
    params.set('end_date', orchestrator.committed.endDate);
  }
  if (orchestrator.committed.holdType) {
    params.set('hold_type', orchestrator.committed.holdType);
  }
  const rt = orchestrator.committed.recordType;
  if (Array.isArray(rt) && rt.length > 0) {
    params.set('record_type', rt.join(','));
  }
  if (orchestrator.committed.reasonFilter) {
    params.set('reason', orchestrator.committed.reasonFilter);
  }
  if (orchestrator.committed.durationFilter) {
    params.set('duration_range', orchestrator.committed.durationFilter);
  }
  if (page.value > 1) {
    params.set('page', String(page.value));
  }

  replaceRuntimeHistory(`/hold-history?${params.toString()}`);
}

function recordTypeCsv() {
  const rt = Array.isArray(orchestrator.committed.recordType) ? orchestrator.committed.recordType : [orchestrator.committed.recordType];
  return rt.join(',');
}

function applyViewResult(result, { listOnly = false } = {}) {
  if (!listOnly) {
    trendData.value = result.trend || trendData.value;
    reasonParetoData.value = result.reason_pareto || reasonParetoData.value;
    durationData.value = result.duration || durationData.value;
  }
  detailData.value = normalizeListPayload(result.list);
}

// ---- Primary query (POST /query -> Oracle -> cache) ----

async function executePrimaryQuery({ showOverlay = false } = {}) {
  const requestId = nextRequestId();

  if (showOverlay) {
    initialLoading.value = true;
  }

  loading.global = true;
  loading.primaryQuery = true;
  loading.list = true;
  errorMessage.value = '';
  refreshError.value = false;

  // Discard any previous local-compute state before evaluating new response (Task 4.4)
  duckdb.deactivate();

  try {
    const body = {
      start_date: orchestrator.committed.startDate,
      end_date: orchestrator.committed.endDate,
      hold_type: orchestrator.committed.holdType,
      record_type: recordTypeCsv(),
    };

    const resp = await apiPost('/api/hold-history/query', body, { timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

    const result = unwrapApiResult(resp, '主查詢執行失敗');

    queryId.value = result.query_id;
    applyViewResult(result);
    updateUrlState();

    // Attempt to activate local compute (Task 4.2)
    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: result.spool_download_url,
      totalRowCount: result.total_row_count,
    });
    if (eligible) {
      try {
        await duckdb.activate(result.spool_download_url, result.workcenter_mapping || {});
      } catch (_) {
        // Activation failed — remain in server-view mode (Task 4.3)
      }
    }

    refreshSuccess.value = true;
    setTimeout(() => { refreshSuccess.value = false; }, 1500);
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    if (error?.name === 'AbortError') {
      errorMessage.value = '查詢逾時，請縮短日期範圍後重試';
    } else {
      errorMessage.value = error?.message || '主查詢執行失敗';
    }
    refreshError.value = true;
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.global = false;
    loading.primaryQuery = false;
    loading.list = false;
    initialLoading.value = false;
  }
}

// ---- View refresh (GET /view -> read cache -> filter) ----

async function refreshView({ listOnly = false } = {}) {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  if (!listOnly) {
    loading.global = true;
  }
  loading.list = true;
  errorMessage.value = '';

  try {
    // Task 4.2: Use local compute when active; skip /view request
    if (duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          startDate: orchestrator.committed.startDate,
          endDate: orchestrator.committed.endDate,
          holdType: orchestrator.committed.holdType,
          recordTypes: Array.isArray(orchestrator.committed.recordType)
            ? orchestrator.committed.recordType
            : [orchestrator.committed.recordType || 'new'],
          reason: orchestrator.committed.reasonFilter || null,
          durationRange: orchestrator.committed.durationFilter || null,
          page: page.value,
          perPage: DEFAULT_PER_PAGE,
        });
        applyViewResult(result, { listOnly });
        return;
      } catch (localErr) {
        // Task 4.3: Local compute failed — fall through to server /view
        console.warn('[hold-history] Local compute error, falling back to server:', localErr);
        duckdb.deactivate();
      }
    }

    // Server-side /view fallback (Task 4.3)
    const params = {
      query_id: queryId.value,
      hold_type: orchestrator.committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };

    if (orchestrator.committed.reasonFilter) {
      params.reason = orchestrator.committed.reasonFilter;
    }
    if (orchestrator.committed.durationFilter) {
      params.duration_range = orchestrator.committed.durationFilter;
    }

    const resp = await apiGet('/api/hold-history/view', {
      params,
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    // Cache expired -> auto re-execute primary query (Task 4.3)
    if (resp?.success === false && resp?.error === 'cache_expired') {
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }

    const result = unwrapApiResult(resp, '視圖查詢失敗');
    applyViewResult(result, { listOnly });
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) return;
    loading.global = false;
    loading.list = false;
  }
}

// ---- Pagination-only refresh (preserves scroll position) ----

async function refreshViewPage() {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  paginationLoading.value = true;
  errorMessage.value = '';

  try {
    // Task 4.4: Use local compute pagination when active (list-only, no chart refresh)
    if (duckdb.isActive.value) {
      try {
        const result = await duckdb.computeView({
          startDate: orchestrator.committed.startDate,
          endDate: orchestrator.committed.endDate,
          holdType: orchestrator.committed.holdType,
          recordTypes: Array.isArray(orchestrator.committed.recordType)
            ? orchestrator.committed.recordType
            : [orchestrator.committed.recordType || 'new'],
          reason: orchestrator.committed.reasonFilter || null,
          durationRange: orchestrator.committed.durationFilter || null,
          page: page.value,
          perPage: DEFAULT_PER_PAGE,
        });
        detailData.value = normalizeListPayload(result.list);
        return;
      } catch (localErr) {
        console.warn('[hold-history] Local compute pagination error, falling back:', localErr);
        duckdb.deactivate();
      }
    }

    // Server-side fallback (Task 4.3)
    const params = {
      query_id: queryId.value,
      hold_type: orchestrator.committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };

    if (orchestrator.committed.reasonFilter) {
      params.reason = orchestrator.committed.reasonFilter;
    }
    if (orchestrator.committed.durationFilter) {
      params.duration_range = orchestrator.committed.durationFilter;
    }

    const resp = await apiGet('/api/hold-history/view', {
      params,
      timeout: API_TIMEOUT,
    });
    if (isStaleRequest(requestId)) return;

    const result = unwrapApiResult(resp, '視圖查詢失敗');
    detailData.value = normalizeListPayload(result.list);
  } catch (error) {
    if (isStaleRequest(requestId)) return;
    if (error?.errorCode === 'CACHE_EXPIRED' || error?.status === 410) {
      paginationLoading.value = false;
      duckdb.deactivate();
      await executePrimaryQuery();
      return;
    }
    errorMessage.value = error?.message || '載入資料失敗';
  } finally {
    if (isStaleRequest(requestId)) return;
    paginationLoading.value = false;
  }
}

// ---- Computed ----

const trendTypeKey = computed(() => (orchestrator.committed.holdType === 'non-quality' ? 'non_quality' : orchestrator.committed.holdType));

const selectedTrendDays = computed(() => {
  const days = Array.isArray(trendData.value?.days) ? trendData.value.days : [];
  return days.map((day) => {
    const section = day?.[trendTypeKey.value] || {};
    return {
      date: day?.date || '',
      holdQty: Number(section.holdQty || 0),
      newHoldQty: Number(section.newHoldQty || 0),
      releaseQty: Number(section.releaseQty || 0),
      futureHoldQty: Number(section.futureHoldQty || 0),
      repeatQualityHoldQty: Number(section.repeatQualityHoldQty || 0),
    };
  });
});

const summary = computed(() => {
  const days = selectedTrendDays.value;

  const releaseQty = days.reduce((total, item) => total + Number(item.releaseQty || 0), 0);
  const newHoldQty = days.reduce((total, item) => total + Number(item.newHoldQty || 0), 0);
  const futureHoldQty = days.reduce((total, item) => total + Number(item.futureHoldQty || 0), 0);
  const repeatQualityHoldQty = days.reduce((total, item) => total + Number(item.repeatQualityHoldQty || 0), 0);
  const netChange = releaseQty - newHoldQty - futureHoldQty;

  const today = new Date().toISOString().slice(0, 10);
  const pastDays = days.filter((d) => d.date <= today);
  const lastDay = pastDays.length > 0 ? pastDays[pastDays.length - 1] : {};
  const stillOnHoldCount = Number(lastDay.holdQty || 0);
  const newHoldSnapshotCount = Number(lastDay.newHoldQty || 0);

  const dur = durationData.value || {};

  return {
    releaseQty,
    newHoldQty,
    futureHoldQty,
    repeatQualityHoldQty,
    stillOnHoldCount,
    newHoldSnapshotCount,
    netChange,
    avgReleasedHours: Number(dur.avgReleasedHours || 0),
    avgOnHoldHours: Number(dur.avgOnHoldHours || 0),
    maxReleasedHours: Number(dur.maxReleasedHours || 0),
    maxOnHoldHours: Number(dur.maxOnHoldHours || 0),
  };
});

const holdTypeLabel = computed(() => {
  if (orchestrator.committed.holdType === 'non-quality') {
    return '非品質異常';
  }
  if (orchestrator.committed.holdType === 'all') {
    return '全部';
  }
  return '品質異常';
});

// Provide a local computed ref for RecordTypeFilter v-model
const recordTypeModel = computed({
  get: () => orchestrator.committed.recordType,
  set: (val) => {
    orchestrator.updateField('recordType', val);
  },
});

// ---- Event handlers ----

function handleApply(next) {
  const nextStartDate = next?.startDate || '';
  const nextEndDate = next?.endDate || '';

  // Update date drafts and apply
  orchestrator.draft.startDate = nextStartDate;
  orchestrator.draft.endDate = nextEndDate;
  // Reset supplementary filters before apply
  orchestrator.committed.reasonFilter = '';
  orchestrator.draft.reasonFilter = '';
  orchestrator.committed.durationFilter = '';
  orchestrator.draft.durationFilter = '';
  orchestrator.committed.recordType = ['new'];
  orchestrator.draft.recordType = ['new'];

  orchestrator.applyDraft();
}

function handleHoldTypeChange(nextHoldType) {
  const holdType = nextHoldType || 'quality';
  if (orchestrator.committed.holdType === holdType) return;

  orchestrator.updateField('holdType', holdType);
}

function handleRecordTypeChange() {
  // recordType is already updated via v-model computed setter
  // Dependencies (clear reason/duration) are handled by orchestrator
  // onFetch triggers refreshView
}

function handleReasonToggle(reason) {
  const nextReason = String(reason || '').trim();
  if (!nextReason) {
    return;
  }

  const current = orchestrator.committed.reasonFilter;
  orchestrator.updateField('reasonFilter', current === nextReason ? '' : nextReason);
}

function clearReasonFilter() {
  if (!orchestrator.committed.reasonFilter) {
    return;
  }
  orchestrator.updateField('reasonFilter', '');
}

function handleDurationToggle(range) {
  const nextRange = String(range || '').trim();
  if (!nextRange) {
    return;
  }

  const current = orchestrator.committed.durationFilter;
  orchestrator.updateField('durationFilter', current === nextRange ? '' : nextRange);
}

function clearDurationFilter() {
  if (!orchestrator.committed.durationFilter) {
    return;
  }
  orchestrator.updateField('durationFilter', '');
}

function prevPage() {
  if (paginationLoading.value || page.value <= 1) {
    return;
  }
  page.value -= 1;
  updateUrlState();
  void refreshViewPage();
}

function nextPage() {
  if (paginationLoading.value) {
    return;
  }
  const totalPages = Number(detailData.value?.pagination?.totalPages || 1);
  if (page.value >= totalPages) {
    return;
  }
  page.value += 1;
  updateUrlState();
  void refreshViewPage();
}

async function manualRefresh() {
  page.value = 1;
  orchestrator.committed.reasonFilter = '';
  orchestrator.draft.reasonFilter = '';
  orchestrator.committed.durationFilter = '';
  orchestrator.draft.durationFilter = '';
  updateUrlState();
  await executePrimaryQuery();
}

onMounted(() => {
  const startDate = getUrlParam('start_date');
  const endDate = getUrlParam('end_date');
  if (startDate && endDate) {
    orchestrator.committed.startDate = startDate;
    orchestrator.draft.startDate = startDate;
    orchestrator.committed.endDate = endDate;
    orchestrator.draft.endDate = endDate;
  } else {
    setDefaultDateRange();
  }
  const initHoldType = normalizeHoldType(getUrlParam('hold_type'));
  orchestrator.committed.holdType = initHoldType;
  orchestrator.draft.holdType = initHoldType;

  const initReason = getUrlParam('reason');
  orchestrator.committed.reasonFilter = initReason;
  orchestrator.draft.reasonFilter = initReason;

  const initDuration = getUrlParam('duration_range');
  orchestrator.committed.durationFilter = initDuration;
  orchestrator.draft.durationFilter = initDuration;

  const initRecordType = parseRecordTypeCsv(getUrlParam('record_type'));
  orchestrator.committed.recordType = initRecordType;
  orchestrator.draft.recordType = initRecordType;

  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }
  updateUrlState();
  void executePrimaryQuery({ showOverlay: true });
});
</script>

<template>
  <div class="dashboard hold-history-page theme-hold-history">
    <PageHeader
      title="Hold 歷史績效"
      :show-refresh="false"
    >
      <template #header-left />
      <template #header-left-after>
        <span class="hold-type-badge">{{ holdTypeLabel }}</span>
      </template>
    </PageHeader>

    <ErrorBanner :message="errorMessage" :dismissible="false" />

    <FilterBar
      :start-date="orchestrator.committed.startDate"
      :end-date="orchestrator.committed.endDate"
      :hold-type="orchestrator.committed.holdType"
      :disabled="loading.global"
      @apply="handleApply"
      @hold-type-change="handleHoldTypeChange"
    />

    <SummaryCards :summary="summary" />

    <DailyTrend :days="selectedTrendDays" />

    <RecordTypeFilter
      v-model="recordTypeModel"
      :disabled="loading.global"
      @update:model-value="handleRecordTypeChange"
    />

    <section class="hold-history-chart-grid">
      <ReasonPareto
        :items="reasonParetoData.items || []"
        :active-reason="orchestrator.committed.reasonFilter"
        @toggle="handleReasonToggle"
      />
      <DurationChart
        :items="durationData.items || []"
        :active-range="orchestrator.committed.durationFilter"
        @toggle="handleDurationToggle"
      />
    </section>

    <FilterIndicator
      :reason="orchestrator.committed.reasonFilter"
      :duration-range="orchestrator.committed.durationFilter"
      @clear-reason="clearReasonFilter"
      @clear-duration="clearDurationFilter"
    />

    <div class="ui-table-wrap">
      <DetailTable
        :items="detailData.items || []"
        :pagination="detailData.pagination"
        :loading="loading.list"
        :paginating="paginationLoading"
        :error-message="errorMessage"
        @prev-page="prevPage"
        @next-page="nextPage"
      />
    </div>
  </div>

  <LoadingOverlay v-if="initialLoading || loading.primaryQuery" tier="page" />
</template>
