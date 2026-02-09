<script setup>
import { computed, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api.js';
import { useAutoRefresh } from '../wip-shared/composables/useAutoRefresh.js';
import { MATRIX_STATUS_COLUMNS, STATUS_DISPLAY_MAP, normalizeStatus } from '../resource-shared/constants.js';

import EquipmentGrid from './components/EquipmentGrid.vue';
import FilterBar from './components/FilterBar.vue';
import FloatingTooltip from './components/FloatingTooltip.vue';
import MatrixSection from './components/MatrixSection.vue';
import StatusHeader from './components/StatusHeader.vue';
import SummaryCards from './components/SummaryCards.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 60000;

const allEquipment = ref([]);
const workcenterGroups = ref([]);
const summary = ref({
  totalCount: 0,
  byStatus: {
    PRD: 0,
    SBY: 0,
    UDT: 0,
    SDT: 0,
    EGT: 0,
    NST: 0,
    OTHER: 0,
  },
  ouPct: 0,
  availabilityPct: 0,
});

const filterState = reactive({
  group: '',
  isProduction: false,
  isKey: false,
  isMonitor: false,
});

const matrixFilter = ref(null);
const summaryStatusFilter = ref(null);
const hierarchyState = reactive({});

const loading = reactive({
  initial: true,
  refreshing: false,
  options: false,
});

const cacheLevel = ref('loading');
const cacheText = ref('檢查中...');
const lastUpdate = ref('--');

const summaryError = ref('');
const equipmentError = ref('');

const tooltipState = reactive({
  visible: false,
  type: 'lot',
  payload: null,
  position: { x: 0, y: 0 },
});

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success === true) {
    return result.data;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  return result;
}

function buildFilterParams() {
  const params = {};

  if (filterState.group) {
    params.workcenter_groups = filterState.group;
  }
  if (filterState.isProduction) {
    params.is_production = 1;
  }
  if (filterState.isKey) {
    params.is_key = 1;
  }
  if (filterState.isMonitor) {
    params.is_monitor = 1;
  }

  return params;
}

function resetHierarchyState() {
  Object.keys(hierarchyState).forEach((key) => {
    delete hierarchyState[key];
  });
}

async function loadOptions() {
  loading.options = true;

  try {
    const result = await apiGet('/api/resource/status/options', {
      timeout: API_TIMEOUT,
      silent: true,
    });
    const data = unwrapApiResult(result, '載入篩選選項失敗');
    workcenterGroups.value = Array.isArray(data?.workcenter_groups) ? data.workcenter_groups : [];
  } finally {
    loading.options = false;
  }
}

async function loadSummary() {
  const result = await apiGet('/api/resource/status/summary', {
    params: buildFilterParams(),
    timeout: API_TIMEOUT,
    silent: true,
  });

  const data = unwrapApiResult(result, '載入摘要失敗');
  const byStatus = data?.by_status || {};

  const normalizedStatus = Object.fromEntries(
    MATRIX_STATUS_COLUMNS.map((status) => [status, Number(byStatus[status] || 0)])
  );

  summary.value = {
    totalCount: Number(data?.total_count || 0),
    byStatus: normalizedStatus,
    ouPct: Number(data?.ou_pct || 0),
    availabilityPct: Number(data?.availability_pct || 0),
  };
}

async function loadEquipment() {
  const result = await apiGet('/api/resource/status', {
    params: buildFilterParams(),
    timeout: API_TIMEOUT,
    silent: true,
  });

  const data = unwrapApiResult(result, '載入設備資料失敗');

  allEquipment.value = Array.isArray(data) ? data : [];
  matrixFilter.value = null;
  summaryStatusFilter.value = null;
  resetHierarchyState();
}

async function checkCacheStatus() {
  try {
    const health = await apiGet('/health', {
      timeout: 15000,
      retries: 0,
      silent: true,
    });

    const resourceCache = health?.resource_cache || {};
    const equipmentCache = health?.equipment_status_cache || {};

    if (resourceCache.enabled && resourceCache.loaded) {
      cacheLevel.value = 'ok';
      cacheText.value = `快取正常 (${Number(resourceCache.count || 0)} 筆)`;
    } else if (resourceCache.enabled) {
      cacheLevel.value = 'loading';
      cacheText.value = '快取載入中...';
    } else {
      cacheLevel.value = 'error';
      cacheText.value = '快取未啟用';
    }

    if (equipmentCache.updated_at) {
      lastUpdate.value = new Date(equipmentCache.updated_at).toLocaleString('zh-TW');
    } else {
      lastUpdate.value = '--';
    }
  } catch {
    cacheLevel.value = 'error';
    cacheText.value = '無法連線';
    lastUpdate.value = '--';
  }
}

function buildMatrixFilterLabel(filter) {
  if (!filter) {
    return '';
  }

  const parts = [filter.workcenter_group];
  if (filter.family) {
    parts.push(filter.family);
  }
  if (filter.resource) {
    const resource = allEquipment.value.find((item) => item.RESOURCEID === filter.resource);
    parts.push(resource?.RESOURCENAME || filter.resource);
  }

  parts.push(STATUS_DISPLAY_MAP[filter.status] || filter.status);
  return `矩陣篩選: ${parts.join(' / ')}`;
}

function isSameMatrixFilter(left, right) {
  if (!left || !right) {
    return false;
  }
  return (
    (left.workcenter_group || null) === (right.workcenter_group || null) &&
    (left.status || null) === (right.status || null) &&
    (left.family || null) === (right.family || null) &&
    (left.resource || null) === (right.resource || null)
  );
}

function matchMatrixFilter(eq, filter) {
  if (!filter) {
    return true;
  }

  if ((eq.WORKCENTER_GROUP || 'UNKNOWN') !== filter.workcenter_group) {
    return false;
  }
  if (filter.family && (eq.RESOURCEFAMILYNAME || 'UNKNOWN') !== filter.family) {
    return false;
  }
  if (filter.resource && (eq.RESOURCEID || null) !== filter.resource) {
    return false;
  }

  return normalizeStatus(eq.EQUIPMENTASSETSSTATUS) === filter.status;
}

const displayedEquipment = computed(() => {
  return allEquipment.value.filter((eq) => {
    if (matrixFilter.value && !matchMatrixFilter(eq, matrixFilter.value)) {
      return false;
    }
    if (summaryStatusFilter.value && normalizeStatus(eq.EQUIPMENTASSETSSTATUS) !== summaryStatusFilter.value) {
      return false;
    }
    return true;
  });
});

const activeFilterText = computed(() => {
  const labels = [];

  const matrixLabel = buildMatrixFilterLabel(matrixFilter.value);
  if (matrixLabel) {
    labels.push(matrixLabel);
  }

  if (summaryStatusFilter.value) {
    labels.push(`卡片篩選: ${STATUS_DISPLAY_MAP[summaryStatusFilter.value] || summaryStatusFilter.value}`);
  }

  return labels.join(' | ');
});

function applyMatrixFilter(nextFilter) {
  if (isSameMatrixFilter(matrixFilter.value, nextFilter)) {
    matrixFilter.value = null;
    return;
  }
  matrixFilter.value = {
    workcenter_group: nextFilter.workcenter_group,
    status: nextFilter.status,
    family: nextFilter.family || null,
    resource: nextFilter.resource || null,
  };
}

function clearAllEquipmentFilters() {
  matrixFilter.value = null;
  summaryStatusFilter.value = null;
}

function toggleSummaryStatus(status) {
  summaryStatusFilter.value = summaryStatusFilter.value === status ? null : status;
}

function handleToggleRow(rowId) {
  hierarchyState[rowId] = !hierarchyState[rowId];
}

function handleToggleAllRows({ expand, rowIds }) {
  (rowIds || []).forEach((rowId) => {
    hierarchyState[rowId] = Boolean(expand);
  });
}

function closeTooltip() {
  tooltipState.visible = false;
  tooltipState.payload = null;
}

function openLotTooltip({ x, y, equipment }) {
  const lotDetails = equipment?.LOT_DETAILS;
  if (!Array.isArray(lotDetails) || lotDetails.length === 0) {
    return;
  }

  tooltipState.type = 'lot';
  tooltipState.payload = lotDetails;
  tooltipState.position = { x, y };
  tooltipState.visible = true;
}

function openJobTooltip({ x, y, equipment }) {
  if (!equipment?.JOBORDER) {
    return;
  }

  tooltipState.type = 'job';
  tooltipState.payload = equipment;
  tooltipState.position = { x, y };
  tooltipState.visible = true;
}

async function loadData(showOverlay = false) {
  if (showOverlay) {
    loading.initial = true;
  }

  loading.refreshing = true;
  summaryError.value = '';
  equipmentError.value = '';

  const [summaryResult, equipmentResult] = await Promise.allSettled([loadSummary(), loadEquipment()]);
  await checkCacheStatus();

  if (summaryResult.status === 'rejected') {
    summaryError.value = summaryResult.reason?.message || '摘要資料載入失敗';
  }

  if (equipmentResult.status === 'rejected') {
    equipmentError.value = equipmentResult.reason?.message || '設備資料載入失敗';
    allEquipment.value = [];
  }

  loading.refreshing = false;
  loading.initial = false;
}

async function applyFiltersAndReload() {
  closeTooltip();
  await loadData(false);
  resetAutoRefresh();
}

function updateGroup(group) {
  filterState.group = group || '';
  void applyFiltersAndReload();
}

function updateFlags(nextFlags) {
  filterState.isProduction = Boolean(nextFlags?.isProduction);
  filterState.isKey = Boolean(nextFlags?.isKey);
  filterState.isMonitor = Boolean(nextFlags?.isMonitor);
  void applyFiltersAndReload();
}

const { resetAutoRefresh, triggerRefresh } = useAutoRefresh({
  onRefresh: () => loadData(false),
  intervalMs: 5 * 60 * 1000,
  autoStart: true,
  refreshOnVisible: true,
});

async function handleManualRefresh() {
  closeTooltip();
  await triggerRefresh({ force: true, resetTimer: true });
}

async function initPage() {
  try {
    await loadOptions();
  } catch (error) {
    equipmentError.value = error?.message || '載入篩選選項失敗';
  }
  await loadData(true);
}

void initPage();
</script>

<template>
  <div class="resource-page">
    <div class="dashboard">
      <StatusHeader
        :cache-level="cacheLevel"
        :cache-text="cacheText"
        :last-update="lastUpdate"
        :refreshing="loading.refreshing"
        @refresh="handleManualRefresh"
      />

      <FilterBar
        :workcenter-groups="workcenterGroups"
        :selected-group="filterState.group"
        :flags="filterState"
        :loading="loading.options || loading.refreshing"
        @change-group="updateGroup"
        @change-flags="updateFlags"
      />

      <p v-if="summaryError" class="error-banner">{{ summaryError }}</p>
      <SummaryCards :summary="summary" :active-status="summaryStatusFilter" @toggle-status="toggleSummaryStatus" />

      <p v-if="equipmentError" class="error-banner">{{ equipmentError }}</p>
      <MatrixSection
        :equipment="allEquipment"
        :expanded-state="hierarchyState"
        :matrix-filter="matrixFilter"
        @toggle-row="handleToggleRow"
        @toggle-all="handleToggleAllRows"
        @cell-filter="applyMatrixFilter"
      />

      <EquipmentGrid
        :equipment="displayedEquipment"
        :active-filter-text="activeFilterText"
        @clear-filter="clearAllEquipmentFilters"
        @show-lot="openLotTooltip"
        @show-job="openJobTooltip"
      />
    </div>

    <div class="loading-overlay" :class="{ hidden: !loading.initial }">
      <div class="loading-spinner"></div>
    </div>

    <FloatingTooltip
      :visible="tooltipState.visible"
      :type="tooltipState.type"
      :payload="tooltipState.payload"
      :position="tooltipState.position"
      @close="closeTooltip"
    />
  </div>
</template>
