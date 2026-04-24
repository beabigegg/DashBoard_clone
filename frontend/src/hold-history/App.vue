<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result.js';
import { checkLocalComputeEligibility } from '../core/duckdb-activation-policy.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';
import { useRequestGuard } from '../shared-composables/useRequestGuard.js';
import { useHoldHistoryDuckDB } from './useHoldHistoryDuckDB.js';
import { useAutoRefresh } from './useAutoRefresh.js';
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

// ── Feature flags (loaded from /api/hold-history/config) ─────────────────────
const todayModeEnabled = ref(true);
const autoRefreshSeconds = ref(60);

// ── Mode ──────────────────────────────────────────────────────────────────────
const mode = ref('range'); // 'range' | 'today' | 'current'

// ── Today-mode state ──────────────────────────────────────────────────────────
const todaySnapshotData = ref(null);
const todayRecordType = ref('on_hold');
const todayLoading = ref(false);
const todayError = ref('');

// ── Current-mode state ────────────────────────────────────────────────────────
const currentSnapshotData = ref(null);
const currentRecordType = ref('on_hold');
const currentLoading = ref(false);
const currentError = ref('');

// ── Range-mode state ──────────────────────────────────────────────────────────
const queryId = ref('');
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

// ── Auto-refresh (today / current mode) ───────────────────────────────────────
const autoRefresh = useAutoRefresh({
  get intervalMs() { return autoRefreshSeconds.value * 1000; },
  fetchFn: () => {
    if (mode.value === 'current') return executeCurrentSnapshot({ silent: true });
    if (mode.value === 'today') return executeTodaySnapshot({ silent: true });
    return Promise.resolve();
  },
});

// ── Filter orchestrator (range mode) ─────────────────────────────────────────
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
    { when: 'holdType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
    { when: 'holdType', then: ['recordType'], action: 'reset', value: ['new'] },
    { when: 'recordType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
  ],
  pagination: { resetOn: ['*'] },
  urlSync: { enabled: false },
  onFetch: (_committed) => {
    page.value = 1;
    updateUrlState();
    void refreshView();
  },
  onPrimaryQuery: (_committed) => {
    page.value = 1;
    updateUrlState();
    void executePrimaryQuery();
  },
});

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function parseTodayRecordTypeCsv(value) {
  const valid = new Set(['on_hold', 'new', 'release']);
  const parsed = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => valid.has(item));
  return parsed.length > 0 ? [...new Set(parsed)] : ['on_hold'];
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

  params.set('mode', mode.value);

  if (mode.value === 'range') {
    if (orchestrator.committed.startDate) params.set('start_date', orchestrator.committed.startDate);
    if (orchestrator.committed.endDate) params.set('end_date', orchestrator.committed.endDate);
    if (orchestrator.committed.holdType) params.set('hold_type', orchestrator.committed.holdType);
    if (orchestrator.committed.reasonFilter) params.set('reason', orchestrator.committed.reasonFilter);
    if (orchestrator.committed.durationFilter) params.set('duration_range', orchestrator.committed.durationFilter);
    if (page.value > 1) params.set('page', String(page.value));
  } else {
    if (orchestrator.committed.holdType) params.set('hold_type', orchestrator.committed.holdType);
    const rt = mode.value === 'current' ? currentRecordType.value : todayRecordType.value;
    if (rt) params.set('record_type', rt);
    if (orchestrator.committed.reasonFilter) params.set('reason', orchestrator.committed.reasonFilter);
    if (orchestrator.committed.durationFilter) params.set('duration_range', orchestrator.committed.durationFilter);
    if (page.value > 1) params.set('page', String(page.value));
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

// ── Today mode API ────────────────────────────────────────────────────────────

async function executeTodaySnapshot({ silent = false } = {}) {
  if (!silent) {
    todayLoading.value = true;
    todayError.value = '';
  }

  try {
    const body = {
      snapshot_mode: 'today',
      hold_type: orchestrator.committed.holdType,
      record_type: todayRecordType.value,
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };
    if (orchestrator.committed.reasonFilter) body.reason = orchestrator.committed.reasonFilter;
    if (orchestrator.committed.durationFilter) body.duration_range = orchestrator.committed.durationFilter;

    const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
    const result = unwrapApiResult(resp, '當日快照取得失敗');
    todaySnapshotData.value = result;
  } catch (error) {
    if (!silent) {
      todayError.value = error?.message || '當日快照取得失敗';
    }
    throw error;
  } finally {
    if (!silent) {
      todayLoading.value = false;
    }
  }
}

// ── Current mode API ──────────────────────────────────────────────────────────

async function executeCurrentSnapshot({ silent = false } = {}) {
  if (!silent) {
    currentLoading.value = true;
    currentError.value = '';
  }

  try {
    const body = {
      snapshot_mode: 'current',
      hold_type: orchestrator.committed.holdType || 'quality',
      record_type: currentRecordType.value,
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };
    if (orchestrator.committed.reasonFilter) body.reason = orchestrator.committed.reasonFilter;
    if (orchestrator.committed.durationFilter) body.duration_range = orchestrator.committed.durationFilter;

    const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
    const result = unwrapApiResult(resp, '現況快照取得失敗');
    currentSnapshotData.value = result;
  } catch (error) {
    if (!silent) {
      currentError.value = error?.message || '現況快照取得失敗';
    }
    throw error;
  } finally {
    if (!silent) {
      currentLoading.value = false;
    }
  }
}

// ── Range mode API ────────────────────────────────────────────────────────────

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

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: result.spool_download_url,
      totalRowCount: result.total_row_count,
    });
    if (eligible) {
      try {
        await duckdb.activate(result.spool_download_url, result.workcenter_mapping || {});
      } catch (_) {
        // Activation failed — remain in server-view mode
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

async function refreshView({ listOnly = false } = {}) {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  if (!listOnly) {
    loading.global = true;
  }
  loading.list = true;
  errorMessage.value = '';

  try {
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
        console.warn('[hold-history] Local compute error, falling back to server:', localErr);
        duckdb.deactivate();
      }
    }

    const params = {
      query_id: queryId.value,
      hold_type: orchestrator.committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };

    if (orchestrator.committed.reasonFilter) params.reason = orchestrator.committed.reasonFilter;
    if (orchestrator.committed.durationFilter) params.duration_range = orchestrator.committed.durationFilter;

    const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT });
    if (isStaleRequest(requestId)) return;

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

async function refreshViewPage() {
  if (!queryId.value) return;

  const requestId = nextRequestId();
  paginationLoading.value = true;
  errorMessage.value = '';

  try {
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

    const params = {
      query_id: queryId.value,
      hold_type: orchestrator.committed.holdType,
      record_type: recordTypeCsv(),
      page: page.value,
      per_page: DEFAULT_PER_PAGE,
    };

    if (orchestrator.committed.reasonFilter) params.reason = orchestrator.committed.reasonFilter;
    if (orchestrator.committed.durationFilter) params.duration_range = orchestrator.committed.durationFilter;

    const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT });
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

// ── Mode switch ───────────────────────────────────────────────────────────────

function handleModeChange(newMode) {
  if (newMode === mode.value) return;

  autoRefresh.stop();

  if (newMode === 'today') {
    // Switch to today: clear date params, reset todayRecordType
    todayRecordType.value = 'on_hold';
    orchestrator.committed.reasonFilter = '';
    orchestrator.draft.reasonFilter = '';
    orchestrator.committed.durationFilter = '';
    orchestrator.draft.durationFilter = '';
    page.value = 1;
    mode.value = 'today';
    todaySnapshotData.value = null;
    updateUrlState();
    void executeTodaySnapshot().then(() => {
      autoRefresh.start();
    });
  } else if (newMode === 'current') {
    // Switch to current: reset currentRecordType, clear filters
    currentRecordType.value = 'on_hold';
    orchestrator.committed.reasonFilter = '';
    orchestrator.draft.reasonFilter = '';
    orchestrator.committed.durationFilter = '';
    orchestrator.draft.durationFilter = '';
    page.value = 1;
    mode.value = 'current';
    currentSnapshotData.value = null;
    updateUrlState();
    void executeCurrentSnapshot().then(() => {
      autoRefresh.start();
    });
  } else {
    // Switch to range: restore default date range, clear record_type from URL
    mode.value = 'range';
    orchestrator.committed.recordType = ['new'];
    orchestrator.draft.recordType = ['new'];
    orchestrator.committed.reasonFilter = '';
    orchestrator.draft.reasonFilter = '';
    orchestrator.committed.durationFilter = '';
    orchestrator.draft.durationFilter = '';
    page.value = 1;
    if (!orchestrator.committed.startDate || !orchestrator.committed.endDate) {
      setDefaultDateRange();
    }
    updateUrlState();
    void executePrimaryQuery({ showOverlay: true });
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────

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
  if (mode.value === 'today') {
    return todaySnapshotData.value?.summary || {};
  }
  if (mode.value === 'current') {
    return currentSnapshotData.value?.summary || {};
  }

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

  const dur = durationData.value || {};

  return {
    releaseQty,
    newHoldQty,
    futureHoldQty,
    repeatQualityHoldQty,
    stillOnHoldCount,
    netChange,
    avgReleasedHours: Number(dur.avgReleasedHours || 0),
    avgOnHoldHours: Number(dur.avgOnHoldHours || 0),
    maxReleasedHours: Number(dur.maxReleasedHours || 0),
    maxOnHoldHours: Number(dur.maxOnHoldHours || 0),
  };
});

const activeReasonParetoItems = computed(() => {
  if (mode.value === 'today') {
    return todaySnapshotData.value?.reason_pareto?.items || [];
  }
  if (mode.value === 'current') {
    return currentSnapshotData.value?.reason_pareto?.items || [];
  }
  return reasonParetoData.value?.items || [];
});

const activeDurationData = computed(() => {
  if (mode.value === 'today') {
    return todaySnapshotData.value?.duration || { items: [] };
  }
  if (mode.value === 'current') {
    return currentSnapshotData.value?.duration || { items: [] };
  }
  return durationData.value || { items: [] };
});

const activeDetailData = computed(() => {
  if (mode.value === 'today') {
    return normalizeListPayload(todaySnapshotData.value?.list);
  }
  if (mode.value === 'current') {
    return normalizeListPayload(currentSnapshotData.value?.list);
  }
  return detailData.value;
});

const activeLoading = computed(() => {
  if (mode.value === 'today') return todayLoading.value;
  if (mode.value === 'current') return currentLoading.value;
  return loading.list;
});

const activeGlobalLoading = computed(() => {
  if (mode.value === 'today') return todayLoading.value;
  if (mode.value === 'current') return currentLoading.value;
  return loading.global;
});

const todayEmptyState = computed(() => {
  if (mode.value !== 'today') return false;
  if (todayLoading.value) return false;
  return (todaySnapshotData.value?.list?.items?.length ?? 0) === 0;
});

const currentEmptyState = computed(() => {
  if (mode.value !== 'current') return false;
  if (currentLoading.value) return false;
  return (currentSnapshotData.value?.list?.items?.length ?? 0) === 0;
});

const holdTypeLabel = computed(() => {
  if (orchestrator.committed.holdType === 'non-quality') return '非品質異常';
  if (orchestrator.committed.holdType === 'all') return '全部';
  return '品質異常';
});

const staleLabel = computed(() => {
  if (!autoRefresh.isStale.value) return '';
  if (mode.value !== 'today' && mode.value !== 'current') return '';
  if (!autoRefresh.lastRefreshAt.value) return '⚠ 自動更新已暫停';
  const diff = Math.round((Date.now() - autoRefresh.lastRefreshAt.value.getTime()) / 1000);
  return `⚠ 資料可能過期（${diff}s 前更新）`;
});

const recordTypeModel = computed({
  get: () => {
    if (mode.value === 'today') return todayRecordType.value;
    if (mode.value === 'current') return currentRecordType.value;
    return orchestrator.committed.recordType;
  },
  set: (val) => {
    if (mode.value === 'today') {
      todayRecordType.value = val;
    } else if (mode.value === 'current') {
      currentRecordType.value = val;
    } else {
      orchestrator.updateField('recordType', val);
    }
  },
});

// ── Event handlers ────────────────────────────────────────────────────────────

function handleApply(next) {
  const nextStartDate = next?.startDate || '';
  const nextEndDate = next?.endDate || '';
  orchestrator.draft.startDate = nextStartDate;
  orchestrator.draft.endDate = nextEndDate;
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
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleRecordTypeChange() {
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleReasonToggle(reason) {
  const nextReason = String(reason || '').trim();
  if (!nextReason) return;
  const current = orchestrator.committed.reasonFilter;
  orchestrator.updateField('reasonFilter', current === nextReason ? '' : nextReason);
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function clearReasonFilter() {
  if (!orchestrator.committed.reasonFilter) return;
  orchestrator.updateField('reasonFilter', '');
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function handleDurationToggle(range) {
  const nextRange = String(range || '').trim();
  if (!nextRange) return;
  const current = orchestrator.committed.durationFilter;
  orchestrator.updateField('durationFilter', current === nextRange ? '' : nextRange);
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function clearDurationFilter() {
  if (!orchestrator.committed.durationFilter) return;
  orchestrator.updateField('durationFilter', '');
  if (mode.value === 'today') {
    page.value = 1;
    updateUrlState();
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    page.value = 1;
    updateUrlState();
    void executeCurrentSnapshot();
  }
}

function prevPage() {
  if (paginationLoading.value || page.value <= 1) return;
  page.value -= 1;
  updateUrlState();
  if (mode.value === 'today') {
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    void executeCurrentSnapshot();
  } else {
    void refreshViewPage();
  }
}

function nextPage() {
  if (paginationLoading.value) return;
  const totalPages = Number(activeDetailData.value?.pagination?.totalPages || 1);
  if (page.value >= totalPages) return;
  page.value += 1;
  updateUrlState();
  if (mode.value === 'today') {
    void executeTodaySnapshot();
  } else if (mode.value === 'current') {
    void executeCurrentSnapshot();
  } else {
    void refreshViewPage();
  }
}

// ── CSV export ────────────────────────────────────────────────────────────────

const exportLoading = ref(false);

function _toCsvField(value) {
  const s = String(value ?? '');
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

function _buildCsv(items) {
  const headers = [
    'Lot ID', 'WorkOrder', 'Product', '站別', 'Hold Reason',
    '數量', 'Hold 時間', 'Hold 人員', 'Hold Comment',
    'Release 時間', 'Release 人員', 'Release Comment',
    '時長(hr)', 'NCR', 'Future Hold Comment',
  ];
  const rows = items.map((r) => [
    r.lotId, r.workorder, r.product, r.workcenter, r.holdReason,
    r.qty, r.holdDate, r.holdEmp, r.holdComment,
    r.releaseDate, r.releaseEmp, r.releaseComment,
    r.holdHours, r.ncr, r.futureHoldComment,
  ].map(_toCsvField).join(','));
  return [headers.join(','), ...rows].join('\n');
}

function _downloadCsv(content, filename) {
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function handleExport() {
  if (exportLoading.value) return;
  exportLoading.value = true;
  try {
    let items = [];

    if (mode.value === 'today' || mode.value === 'current') {
      const body = {
        snapshot_mode: mode.value === 'current' ? 'current' : 'today',
        hold_type: orchestrator.committed.holdType,
        record_type: mode.value === 'current' ? currentRecordType.value : todayRecordType.value,
        export: true,
      };
      const resp = await apiPost('/api/hold-history/today-snapshot', body, { timeout: API_TIMEOUT });
      const result = unwrapApiResult(resp, '匯出失敗');
      items = result?.list?.items || [];
    } else {
      const params = {
        query_id: queryId.value,
        hold_type: orchestrator.committed.holdType,
        record_type: recordTypeCsv(),
        export: 1,
      };
      const resp = await apiGet('/api/hold-history/view', { params, timeout: API_TIMEOUT });
      const result = unwrapApiResult(resp, '匯出失敗');
      items = result?.list?.items || [];
    }

    if (!items.length) return;
    const dateStr = new Date().toISOString().slice(0, 10);
    _downloadCsv(_buildCsv(items), `hold-history-${dateStr}.csv`);
  } catch (err) {
    console.error('[hold-history] CSV export failed:', err);
  } finally {
    exportLoading.value = false;
  }
}

async function manualRefresh() {
  page.value = 1;
  orchestrator.committed.reasonFilter = '';
  orchestrator.draft.reasonFilter = '';
  orchestrator.committed.durationFilter = '';
  orchestrator.draft.durationFilter = '';
  updateUrlState();
  if (mode.value === 'today') {
    await executeTodaySnapshot();
  } else if (mode.value === 'current') {
    await executeCurrentSnapshot();
  } else {
    await executePrimaryQuery();
  }
}

// ── Watch todayRecordType / currentRecordType (update URL only; actual fetch triggered by handler) ─
watch(todayRecordType, () => {
  if (mode.value === 'today') updateUrlState();
});

watch(currentRecordType, () => {
  if (mode.value === 'current') updateUrlState();
});

// ── Mount ─────────────────────────────────────────────────────────────────────

onMounted(async () => {
  // Load feature flags
  try {
    const resp = await apiGet('/api/hold-history/config');
    if (resp?.data) {
      todayModeEnabled.value = resp.data.today_mode_enabled !== false;
      if (resp.data.auto_refresh_seconds) {
        autoRefreshSeconds.value = Number(resp.data.auto_refresh_seconds) || 60;
      }
    }
  } catch {
    // default values already set
  }

  // Read URL params
  const urlMode = getUrlParam('mode');
  const initMode = (urlMode === 'today' && todayModeEnabled.value) ? 'today'
                 : (urlMode === 'current' && todayModeEnabled.value) ? 'current'
                 : 'range';
  mode.value = initMode;

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

  const parsedPage = Number.parseInt(getUrlParam('page'), 10);
  if (Number.isFinite(parsedPage) && parsedPage > 0) {
    page.value = parsedPage;
  }

  if (initMode === 'today') {
    const initTodayRt = parseTodayRecordTypeCsv(getUrlParam('record_type'));
    todayRecordType.value = Array.isArray(initTodayRt) ? (initTodayRt[0] || 'on_hold') : (initTodayRt || 'on_hold');
    updateUrlState();
    await executeTodaySnapshot({ showOverlay: false });
    initialLoading.value = false;
    autoRefresh.start();
  } else if (initMode === 'current') {
    const initCurrentRt = parseTodayRecordTypeCsv(getUrlParam('record_type'));
    currentRecordType.value = Array.isArray(initCurrentRt) ? (initCurrentRt[0] || 'on_hold') : (initCurrentRt || 'on_hold');
    updateUrlState();
    await executeCurrentSnapshot({ showOverlay: false });
    initialLoading.value = false;
    autoRefresh.start();
  } else {
    const initRecordType = parseRecordTypeCsv(getUrlParam('record_type'));
    orchestrator.committed.recordType = initRecordType;
    orchestrator.draft.recordType = initRecordType;
    updateUrlState();
    void executePrimaryQuery({ showOverlay: true });
  }
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
        <span v-if="staleLabel" class="stale-indicator" aria-live="polite">{{ staleLabel }}</span>
      </template>
    </PageHeader>

    <ErrorBanner :message="errorMessage || todayError || currentError" :dismissible="false" />

    <FilterBar
      :start-date="orchestrator.committed.startDate"
      :end-date="orchestrator.committed.endDate"
      :hold-type="orchestrator.committed.holdType"
      :mode="mode"
      :today-mode-enabled="todayModeEnabled"
      :disabled="activeGlobalLoading"
      @apply="handleApply"
      @hold-type-change="handleHoldTypeChange"
      @mode-change="handleModeChange"
    />

    <SummaryCards :summary="summary" :mode="mode" />

    <!-- DailyTrend hidden in today mode -->
    <DailyTrend v-if="mode === 'range'" :days="selectedTrendDays" />

    <RecordTypeFilter
      v-model="recordTypeModel"
      :mode="mode"
      :disabled="activeGlobalLoading"
      @update:model-value="handleRecordTypeChange"
    />

    <section class="hold-history-chart-grid">
      <ReasonPareto
        :items="activeReasonParetoItems"
        :active-reason="orchestrator.committed.reasonFilter"
        @toggle="handleReasonToggle"
      />
      <DurationChart
        :items="activeDurationData.items || []"
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

    <EmptyState
      v-if="todayEmptyState"
      message="今日無符合條件的 lot"
    />
    <EmptyState
      v-else-if="currentEmptyState"
      message="現況無符合條件的 lot"
    />

    <div v-else class="ui-table-wrap">
      <DetailTable
        :items="activeDetailData.items || []"
        :pagination="activeDetailData.pagination"
        :loading="activeLoading"
        :paginating="paginationLoading"
        :exporting="exportLoading"
        :error-message="errorMessage || todayError || currentError"
        @prev-page="prevPage"
        @next-page="nextPage"
        @export="handleExport"
      />
    </div>
  </div>

  <LoadingOverlay v-if="initialLoading || loading.primaryQuery" tier="page" />
</template>
