<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../core/api.js';
import { buildResourceKpiFromHours } from '../core/compute.js';
import {
  buildResourceHistoryQueryParams,
  deriveResourceFamilyOptions,
  deriveResourceMachineOptions,
  pruneResourceFilterSelections,
  toResourceFilterSnapshot,
} from '../core/resource-history-filters.js';
import { replaceRuntimeHistory } from '../core/shell-navigation.js';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator.js';

import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';

import ComparisonChart from './components/ComparisonChart.vue';
import DetailSection from './components/DetailSection.vue';
import FilterBar from './components/FilterBar.vue';
import HeatmapChart from './components/HeatmapChart.vue';
import KpiCards from './components/KpiCards.vue';
import StackedChart from './components/StackedChart.vue';
import TrendChart from './components/TrendChart.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 360000;
const MAX_QUERY_DAYS = 730;

function createDefaultFilters() {
  return toResourceFilterSnapshot({
    granularity: 'day',
    workcenterGroups: [],
    families: [],
    machines: [],
    isProduction: false,
    isKey: false,
    isMonitor: false,
  });
}

const {
  committed: committedFilters,
  draft: draftFilters,
  updateField: updateOrchestratorField,
} = useFilterOrchestrator({
  fields: {
    startDate:       { trigger: 'immediate', initial: '' },
    endDate:         { trigger: 'immediate', initial: '' },
    granularity:     { trigger: 'immediate', initial: 'day' },
    workcenterGroups:{ trigger: 'immediate', initial: [] },
    families:        { trigger: 'immediate', initial: [] },
    machines:        { trigger: 'immediate', initial: [] },
    isProduction:    { trigger: 'immediate', initial: false },
    isKey:           { trigger: 'immediate', initial: false },
    isMonitor:       { trigger: 'immediate', initial: false },
  },
  dependencies: [],
});

const options = reactive({
  workcenterGroups: [],
  families: [],
  resources: [],
});

const summaryData = ref({
  kpi: {},
  trend: [],
  heatmap: [],
  workcenter_comparison: [],
});
const detailData = ref([]);
const hierarchyState = reactive({});

const loading = reactive({
  initial: true,
  querying: false,
  options: false,
});

const queryError = ref('');
const detailWarning = ref('');
const exportMessage = ref('');
const autoPruneHint = ref('');

const queryId = ref('');
const lastPrimarySnapshot = ref('');

const draftWatchReady = ref(false);
let suppressDraftPrune = false;

function runWithDraftPruneSuppressed(callback) {
  suppressDraftPrune = true;
  try {
    callback();
  } finally {
    suppressDraftPrune = false;
  }
}

function resetHierarchyState() {
  Object.keys(hierarchyState).forEach((key) => {
    delete hierarchyState[key];
  });
}

function toDateString(value) {
  return value.toISOString().slice(0, 10);
}

function setDefaultDates(target) {
  const today = new Date();
  const endDate = new Date(today);
  endDate.setDate(endDate.getDate() - 1);

  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 6);

  target.startDate = toDateString(startDate);
  target.endDate = toDateString(endDate);
}

function assignFilterState(target, source) {
  const snapshot = toResourceFilterSnapshot(source);
  target.startDate = snapshot.startDate;
  target.endDate = snapshot.endDate;
  target.granularity = snapshot.granularity;
  target.workcenterGroups = [...snapshot.workcenterGroups];
  target.families = [...snapshot.families];
  target.machines = [...snapshot.machines];
  target.isProduction = snapshot.isProduction;
  target.isKey = snapshot.isKey;
  target.isMonitor = snapshot.isMonitor;
}

function resetToDefaultFilters(target) {
  const defaults = createDefaultFilters();
  setDefaultDates(defaults);
  assignFilterState(target, defaults);
}

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success === true) {
    return result;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  return result;
}

function mergeComputedKpi(source) {
  return {
    ...source,
    ...buildResourceKpiFromHours(source),
  };
}

function appendArrayParams(params, key, values) {
  for (const value of values || []) {
    params.append(key, value);
  }
}

function buildQueryStringFromFilters(filters) {
  const queryParams = buildResourceHistoryQueryParams(filters);
  const params = new URLSearchParams();

  params.append('start_date', queryParams.start_date);
  params.append('end_date', queryParams.end_date);
  params.append('granularity', queryParams.granularity);
  appendArrayParams(params, 'workcenter_groups', queryParams.workcenter_groups || []);
  appendArrayParams(params, 'families', queryParams.families || []);
  appendArrayParams(params, 'resource_ids', queryParams.resource_ids || []);

  if (queryParams.is_production) {
    params.append('is_production', queryParams.is_production);
  }
  if (queryParams.is_key) {
    params.append('is_key', queryParams.is_key);
  }
  if (queryParams.is_monitor) {
    params.append('is_monitor', queryParams.is_monitor);
  }

  return params.toString();
}

function readArrayParam(params, key) {
  const repeated = params.getAll(key).map((value) => String(value || '').trim()).filter(Boolean);
  if (repeated.length > 0) {
    return repeated;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

function readBooleanParam(params, key) {
  const value = String(params.get(key) || '').trim().toLowerCase();
  return value === '1' || value === 'true' || value === 'yes';
}

function restoreCommittedFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const next = {
    startDate: String(params.get('start_date') || '').trim(),
    endDate: String(params.get('end_date') || '').trim(),
    granularity: String(params.get('granularity') || '').trim(),
    workcenterGroups: readArrayParam(params, 'workcenter_groups'),
    families: readArrayParam(params, 'families'),
    machines: readArrayParam(params, 'resource_ids'),
    isProduction: readBooleanParam(params, 'is_production'),
    isKey: readBooleanParam(params, 'is_key'),
    isMonitor: readBooleanParam(params, 'is_monitor'),
  };

  if (next.startDate) {
    committedFilters.startDate = next.startDate;
  }
  if (next.endDate) {
    committedFilters.endDate = next.endDate;
  }
  if (next.granularity) {
    committedFilters.granularity = next.granularity;
  }
  if (next.workcenterGroups.length > 0) {
    committedFilters.workcenterGroups = next.workcenterGroups;
  }
  if (next.families.length > 0) {
    committedFilters.families = next.families;
  }
  if (next.machines.length > 0) {
    committedFilters.machines = next.machines;
  }
  committedFilters.isProduction = next.isProduction;
  committedFilters.isKey = next.isKey;
  committedFilters.isMonitor = next.isMonitor;
}

function updateUrlState() {
  const queryString = buildQueryStringFromFilters(committedFilters);
  const nextUrl = queryString ? `/resource-history?${queryString}` : '/resource-history';
  replaceRuntimeHistory(nextUrl);
}

function validateDateRange(filters) {
  if (!filters.startDate || !filters.endDate) {
    return '請先設定開始與結束日期';
  }

  const start = new Date(filters.startDate);
  const end = new Date(filters.endDate);
  const diffDays = (end - start) / (1000 * 60 * 60 * 24);

  if (diffDays < 0) {
    return '結束日期必須大於起始日期';
  }
  if (diffDays > MAX_QUERY_DAYS) {
    return '查詢範圍不可超過兩年';
  }

  return '';
}

async function loadOptions() {
  loading.options = true;

  try {
    const response = await apiGet('/api/resource/history/options', {
      timeout: API_TIMEOUT,
      silent: true,
    });

    const payload = unwrapApiResult(response, '載入篩選選項失敗');
    const data = payload.data || {};

    options.workcenterGroups = Array.isArray(data.workcenter_groups) ? data.workcenter_groups : [];
    options.families = Array.isArray(data.families) ? data.families : [];
    options.resources = Array.isArray(data.resources) ? data.resources : [];
  } finally {
    loading.options = false;
  }
}

const familyOptions = computed(() => {
  return deriveResourceFamilyOptions(options.resources, draftFilters);
});

const machineOptions = computed(() => {
  return deriveResourceMachineOptions(options.resources, draftFilters);
});

const filterBarOptions = computed(() => {
  return {
    workcenterGroups: options.workcenterGroups,
    families: familyOptions.value,
  };
});

function formatPruneHint(removed) {
  const parts = [];
  if (removed.families.length > 0) {
    parts.push(`型號: ${removed.families.join(', ')}`);
  }
  if (removed.machines.length > 0) {
    parts.push(`機台: ${removed.machines.join(', ')}`);
  }
  if (parts.length === 0) {
    return '';
  }
  return `已自動清除失效篩選：${parts.join('；')}`;
}

function pruneDraftSelections({ showHint = true } = {}) {
  const result = pruneResourceFilterSelections(draftFilters, {
    familyOptions: familyOptions.value,
    machineOptions: machineOptions.value,
  });
  if (result.removedCount > 0) {
    runWithDraftPruneSuppressed(() => {
      draftFilters.families = [...result.filters.families];
      draftFilters.machines = [...result.filters.machines];
    });
    if (showHint) {
      autoPruneHint.value = formatPruneHint(result.removed);
    }
  }
  return result;
}

const pruneSignature = computed(() => {
  return JSON.stringify({
    workcenterGroups: draftFilters.workcenterGroups,
    families: draftFilters.families,
    machines: draftFilters.machines,
    isProduction: draftFilters.isProduction,
    isKey: draftFilters.isKey,
    isMonitor: draftFilters.isMonitor,
    familyOptions: familyOptions.value,
    machineOptions: machineOptions.value.map((item) => item.value),
  });
});

watch(pruneSignature, () => {
  if (!draftWatchReady.value || suppressDraftPrune) {
    return;
  }
  pruneDraftSelections({ showHint: true });
});

// ─── Two-phase helpers ──────────────────────────────────────

/**
 * Build a snapshot string of "primary" params (those that require a new Oracle query).
 * Granularity is NOT primary — it can be re-derived from cache.
 */
function buildPrimarySnapshot(filters) {
  const p = buildResourceHistoryQueryParams(filters);
  return JSON.stringify({
    start_date: p.start_date,
    end_date: p.end_date,
    workcenter_groups: p.workcenter_groups || [],
    families: p.families || [],
    resource_ids: p.resource_ids || [],
    is_production: p.is_production || '',
    is_key: p.is_key || '',
    is_monitor: p.is_monitor || '',
  });
}

function applyViewResult(result) {
  const summary = result.summary || {};
  summaryData.value = {
    kpi: mergeComputedKpi(summary.kpi || {}),
    trend: (summary.trend || []).map((item) => mergeComputedKpi(item || {})),
    heatmap: summary.heatmap || [],
    workcenter_comparison: summary.workcenter_comparison || [],
  };

  const detail = result.detail || {};
  detailData.value = Array.isArray(detail.data) ? detail.data : [];
  resetHierarchyState();

  if (detail.truncated) {
    detailWarning.value = `明細資料超過 ${detail.max_records} 筆，僅顯示前 ${detail.max_records} 筆。`;
  } else {
    detailWarning.value = '';
  }
}

async function executePrimaryQuery() {
  const validationError = validateDateRange(committedFilters);
  if (validationError) {
    queryError.value = validationError;
    loading.initial = false;
    return;
  }

  loading.querying = true;
  queryError.value = '';
  detailWarning.value = '';
  exportMessage.value = '';

  try {
    updateUrlState();

    const queryParams = buildResourceHistoryQueryParams(committedFilters);
    const body = {
      start_date: queryParams.start_date,
      end_date: queryParams.end_date,
      granularity: queryParams.granularity,
      workcenter_groups: queryParams.workcenter_groups || [],
      families: queryParams.families || [],
      resource_ids: queryParams.resource_ids || [],
      is_production: !!queryParams.is_production,
      is_key: !!queryParams.is_key,
      is_monitor: !!queryParams.is_monitor,
    };

    const response = await apiPost('/api/resource/history/query', body, {
      timeout: API_TIMEOUT,
      silent: true,
    });

    const payload = unwrapApiResult(response, '查詢失敗');
    queryId.value = payload.data.query_id || '';
    lastPrimarySnapshot.value = buildPrimarySnapshot(committedFilters);
    applyViewResult(payload.data);
  } catch (error) {
    if (error?.name === 'AbortError') {
      queryError.value = '查詢逾時，請縮小日期範圍或資源篩選後重試';
    } else {
      queryError.value = error?.message || '查詢失敗';
    }
    summaryData.value = { kpi: {}, trend: [], heatmap: [], workcenter_comparison: [] };
    detailData.value = [];
    resetHierarchyState();
  } finally {
    loading.querying = false;
    loading.initial = false;
  }
}

async function refreshView() {
  if (!queryId.value) {
    await executePrimaryQuery();
    return;
  }

  loading.querying = true;
  queryError.value = '';

  try {
    updateUrlState();

    const response = await apiGet('/api/resource/history/view', {
      timeout: API_TIMEOUT,
      silent: true,
      params: {
        query_id: queryId.value,
        granularity: committedFilters.granularity || 'day',
      },
    });

    if (response?.success === false && response?.error === 'cache_expired') {
      await executePrimaryQuery();
      return;
    }

    const payload = unwrapApiResult(response, '查詢失敗');
    applyViewResult(payload.data);
  } catch (error) {
    if (error?.message === 'cache_expired' || error?.status === 410) {
      await executePrimaryQuery();
      return;
    }
    queryError.value = error?.message || '查詢失敗';
  } finally {
    loading.querying = false;
  }
}

// ─── Filter actions ─────────────────────────────────────────

async function applyFilters() {
  const validationError = validateDateRange(draftFilters);
  if (validationError) {
    queryError.value = validationError;
    return;
  }
  pruneDraftSelections({ showHint: true });
  assignFilterState(committedFilters, draftFilters);

  const currentPrimary = buildPrimarySnapshot(committedFilters);
  if (queryId.value && currentPrimary === lastPrimarySnapshot.value) {
    await refreshView();
  } else {
    await executePrimaryQuery();
  }
}

async function clearFilters() {
  runWithDraftPruneSuppressed(() => {
    resetToDefaultFilters(draftFilters);
  });
  autoPruneHint.value = '';
  assignFilterState(committedFilters, draftFilters);
  await executePrimaryQuery();
}

function updateFilters(nextFilters) {
  runWithDraftPruneSuppressed(() => {
    assignFilterState(draftFilters, nextFilters);
  });
  pruneDraftSelections({ showHint: true });
}

function handleToggleRow(rowId) {
  hierarchyState[rowId] = !hierarchyState[rowId];
}

function handleToggleAllRows({ expand, rowIds }) {
  (rowIds || []).forEach((rowId) => {
    hierarchyState[rowId] = Boolean(expand);
  });
}

function exportCsv() {
  if (!committedFilters.startDate || !committedFilters.endDate) {
    queryError.value = '請先設定查詢條件';
    return;
  }

  const queryString = buildQueryStringFromFilters(committedFilters);
  const link = document.createElement('a');
  link.href = `/api/resource/history/export?${queryString}`;
  link.download = `resource_history_${committedFilters.startDate}_to_${committedFilters.endDate}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  exportMessage.value = 'CSV 匯出中...';
}

async function initPage() {
  resetToDefaultFilters(committedFilters);
  restoreCommittedFiltersFromUrl();
  runWithDraftPruneSuppressed(() => {
    assignFilterState(draftFilters, committedFilters);
  });

  try {
    await loadOptions();
    pruneDraftSelections({ showHint: true });
    assignFilterState(committedFilters, draftFilters);
  } catch (error) {
    queryError.value = error?.message || '載入篩選選項失敗';
  }

  draftWatchReady.value = true;
  await executePrimaryQuery();
}

onMounted(() => {
  void initPage();
});
</script>

<template>
  <div class="resource-page theme-resource-history">
    <div class="dashboard">
      <header class="header-gradient history-header">
        <h1>設備歷史績效</h1>
      </header>

      <FilterBar
        :filters="draftFilters"
        :options="filterBarOptions"
        :machine-options="machineOptions"
        :loading="loading.options || loading.querying"
        @update-filters="updateFilters"
        @query="applyFilters"
        @clear="clearFilters"
      />

      <p v-if="queryError" class="error-banner query-error">{{ queryError }}</p>
      <p v-if="autoPruneHint" class="filter-indicator">{{ autoPruneHint }}</p>
      <p v-if="detailWarning" class="filter-indicator active">{{ detailWarning }}</p>
      <p v-if="exportMessage" class="filter-indicator active">{{ exportMessage }}</p>

      <KpiCards :kpi="summaryData.kpi" />

      <section class="section-card">
        <div class="section-inner">
          <div class="chart-grid">
            <TrendChart :trend="summaryData.trend || []" />
            <StackedChart :trend="summaryData.trend || []" />
            <ComparisonChart :comparison="summaryData.workcenter_comparison || []" />
            <HeatmapChart :heatmap="summaryData.heatmap || []" />
          </div>
        </div>
      </section>

      <div class="ui-table-wrap" :class="{ 'is-loading': loading.querying }">
        <DetailSection
          :detail-data="detailData"
          :expanded-state="hierarchyState"
          :loading="loading.querying"
          @toggle-row="handleToggleRow"
          @toggle-all="handleToggleAllRows"
          @export-csv="exportCsv"
        />
      </div>
    </div>

    <LoadingOverlay v-if="loading.initial" tier="page" />
  </div>
</template>
