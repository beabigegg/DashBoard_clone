<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api';
import { unwrapApiData as unwrapApiResult } from '../core/unwrap-api-result';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh';
import { bindUpdateBadge } from '../shared-composables/usePageUpdateBadge';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { MATRIX_STATUS_COLUMNS, OU_BADGE_THRESHOLDS, STATUS_DISPLAY_MAP, normalizeStatus } from '../resource-shared/constants';
import { useCrossFilter } from './composables/useCrossFilter';
import type { CrossFilterSource } from './composables/useCrossFilter';

// --- Domain Interfaces ---

interface EquipmentItem {
  RESOURCEID: string;
  RESOURCENAME: string;
  EQUIPMENTASSETSSTATUS: string;
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  RESOURCEFAMILYNAME: string;
  WORKCENTERNAME: string;
  LOCATIONNAME: string;
  LOT_COUNT: number | string;
  LOT_DETAILS: LotItem[];
  JOBORDER: string;
  JOBSTATUS: string;
  JOBMODEL: string;
  JOBSTAGE: string;
  JOBID: string;
  CREATEDATE: string;
  CREATEUSERNAME: string;
  CREATEUSER: string;
  TECHNICIANUSERNAME: string;
  TECHNICIANUSER: string;
  SYMPTOMCODE: string;
  CAUSECODE: string;
  REPAIRCODE: string;
  STATUS_CATEGORY: string;
  PACKAGEGROUPNAME: string | null;
}

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
}

interface ResourceOption {
  id: string;
  name: string;
  family: string;
  workcenterGroup: string;
  isProduction: boolean;
  isKey: boolean;
  isMonitor: boolean;
}

interface SummaryData {
  totalCount: number;
  byStatus: Record<string, number>;
  ouPct: number;
  availabilityPct: number;
}

interface MatrixFilter {
  workcenter_group: string;
  status: string;
  family: string | null;
  resource: string | null;
}

interface TooltipState {
  visible: boolean;
  type: 'lot' | 'job';
  payload: LotItem[] | EquipmentItem | null;
  position: { x: number; y: number };
}

interface LoadingState {
  initial: boolean;
  refreshing: boolean;
  options: boolean;
}

interface MachineOption {
  label: string;
  value: string;
}

import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';

import EquipmentGrid from './components/EquipmentGrid.vue';
import FilterBar from './components/FilterBar.vue';
import FloatingTooltip from './components/FloatingTooltip.vue';
import MaintenanceAlerts from './components/MaintenanceAlerts.vue';
import MatrixSection from './components/MatrixSection.vue';
import OuHeatmap from './components/OuHeatmap.vue';
import WorkcenterOuRings from './components/WorkcenterOuRings.vue';
ensureMesApiAvailable();

const API_TIMEOUT = 60000;

const allEquipment = ref<EquipmentItem[]>([]);
const workcenterGroups = ref<string[]>([]);
const packageGroups = ref<string[]>([]);
const allResources = ref<ResourceOption[]>([]);
const summary = ref<SummaryData>({
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

// --- Filter orchestration with cascading: group/flags -> families -> machines ---

interface FilterState {
  groups: string[];
  isProduction: boolean;
  isKey: boolean;
  isMonitor: boolean;
  families: string[];
  machines: string[];
  packageGroups: string[];
}

const {
  committed: _filterStateRaw,
  updateField,
} = useFilterOrchestrator({
  fields: {
    groups:        { trigger: 'immediate', initial: [] },
    isProduction:  { trigger: 'immediate', initial: false },
    isKey:         { trigger: 'immediate', initial: false },
    isMonitor:     { trigger: 'immediate', initial: false },
    families:      { trigger: 'immediate', initial: [] },
    machines:      { trigger: 'immediate', initial: [] },
    packageGroups: { trigger: 'immediate', initial: [] },
  },
  dependencies: [
    { when: 'groups',       then: ['families', 'machines'], action: 'clear' },
    { when: 'isProduction', then: ['families', 'machines'], action: 'clear' },
    { when: 'isKey',        then: ['families', 'machines'], action: 'clear' },
    { when: 'isMonitor',    then: ['families', 'machines'], action: 'clear' },
    { when: 'families',     then: ['machines'],             action: 'clear' },
  ],
  onFetch: () => void applyFiltersAndReload(),
});

// Cast committed to typed FilterState for property access throughout the component
const filterState = _filterStateRaw as unknown as FilterState;

const hierarchyState = reactive<Record<string, boolean>>({});

const {
  activeSelections,
  filteredEquipment,
  hasActiveSelections,
  addSelection,
  removeSelection,
  clearAll: clearAllCrossFilter,
  getInputForChart,
} = useCrossFilter(allEquipment);

// Focus-return: track the last element that triggered a cross-filter selection
// so ESC and the clear-all button can return focus to a meaningful element.
const lastClickedTrigger = ref<HTMLElement | null>(null);

function captureLastTrigger(): void {
  const active = document.activeElement;
  if (active && active !== document.body) {
    lastClickedTrigger.value = active as HTMLElement;
  }
}

// Derive ring selection for highlight (first ring-source selection)
const ringSelection = computed(() => {
  const sel = activeSelections.value.find((s) => s.source === 'ring');
  if (!sel) return null;
  // Extract group+status from label — stored as { group, status } in meta
  return (sel as { source: string; label: string; _meta?: { group: string; status: string } })._meta ?? null;
});

// Heatmap selected cell
const heatmapSelectedCell = computed(() => {
  const sel = activeSelections.value.find((s) => s.source === 'heatmap');
  return (sel as { source: string; label: string; _meta?: { group: string; packageGroupName: string } } | undefined)?._meta ?? null;
});

// Alerts selected id
const alertsSelectedId = computed(() => {
  const sel = activeSelections.value.find((s) => s.source === 'alerts');
  return (sel as { source: string; label: string; _meta?: { resourceId: string } } | undefined)?._meta?.resourceId ?? null;
});

// matrix active selection (for MatrixSection activeSelection prop)
const matrixActiveSelection = computed<MatrixFilter | null>(() => {
  const sel = activeSelections.value.find((s) => s.source === 'matrix');
  return (sel as { source: string; label: string; _meta?: MatrixFilter } | undefined)?._meta ?? null;
});

const loading = reactive<LoadingState>({
  initial: true,
  refreshing: false,
  options: false,
});

const lastUpdate = ref('--');

bindUpdateBadge({ updateTime: lastUpdate, refreshing: () => loading.refreshing });

const summaryError = ref('');
const equipmentError = ref('');

const STATUS_ACCENT_MAP: Record<string, string> = {
  PRD: 'prd',
  SBY: 'sby',
  UDT: 'udt',
  SDT: 'sdt',
  EGT: 'egt',
  NST: 'nst',
  OTHER: 'neutral',
};

function resolveOuAccent(value: number): string {
  const pct = Number(value || 0);
  if (pct >= OU_BADGE_THRESHOLDS.high) return 'success';
  if (pct >= OU_BADGE_THRESHOLDS.medium) return 'warning';
  return 'danger';
}

const statusTotalForPct = computed(() => {
  return MATRIX_STATUS_COLUMNS.reduce((total, status) => total + Number(summary.value.byStatus?.[status] || 0), 0);
});

function statusPctSub(status: string): string {
  const count = Number(summary.value.byStatus?.[status] || 0);
  const total = statusTotalForPct.value;
  const pctStr = total > 0 ? `${((count / total) * 100).toFixed(1)}%` : '--';
  return `${STATUS_DISPLAY_MAP[status] || status} (${pctStr})`;
}

const tooltipState = reactive<TooltipState>({
  visible: false,
  type: 'lot',
  payload: null,
  position: { x: 0, y: 0 },
});

// unwrapApiResult imported from ../core/unwrap-api-result.js (as unwrapApiData)

function buildFilterParams(): Record<string, string | number> {
  const params: Record<string, string | number> = {};

  if (filterState.groups.length > 0) {
    params.workcenter_groups = filterState.groups.join(',');
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
  if (filterState.families.length) {
    params.families = filterState.families.join(',');
  }
  if (filterState.machines.length) {
    params.resource_ids = filterState.machines.join(',');
  }
  if (filterState.packageGroups.length) {
    params.package_groups = filterState.packageGroups.join(',');
  }

  return params;
}

// --- Cascade: derive available family/machine options from upstream filters ---
const filteredByUpstream = computed(() => {
  const groupSet = filterState.groups.length > 0 ? new Set(filterState.groups) : null;
  return allResources.value.filter((r) => {
    if (groupSet && !groupSet.has(r.workcenterGroup)) return false;
    if (filterState.isProduction && !r.isProduction) return false;
    if (filterState.isKey && !r.isKey) return false;
    if (filterState.isMonitor && !r.isMonitor) return false;
    return true;
  });
});

const familyOptions = computed<string[]>(() => {
  const set = new Set<string>();
  filteredByUpstream.value.forEach((r) => {
    if (r.family) set.add(r.family);
  });
  return [...set].sort();
});

const machineOptions = computed<(string | number | Record<string, unknown>)[]>(() => {
  let list = filteredByUpstream.value;
  if (filterState.families.length > 0) {
    const fset = new Set<string>(filterState.families);
    list = list.filter((r) => fset.has(r.family));
  }
  return list
    .map((r): Record<string, unknown> => ({ label: r.name, value: r.id }))
    .sort((a, b) => String(a['label']).localeCompare(String(b['label'])));
});

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
    const data = unwrapApiResult(result, '載入篩選選項失敗') as { workcenter_groups?: unknown; resources?: unknown; package_groups?: unknown } | null | undefined;
    workcenterGroups.value = Array.isArray(data?.workcenter_groups) ? (data.workcenter_groups as string[]) : [];
    allResources.value = Array.isArray(data?.resources) ? (data.resources as ResourceOption[]) : [];
    packageGroups.value = Array.isArray(data?.package_groups) ? (data.package_groups as string[]) : [];
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

  const data = unwrapApiResult(result, '載入摘要失敗') as {
    by_status?: Record<string, unknown>;
    total_count?: unknown;
    ou_pct?: unknown;
    availability_pct?: unknown;
  } | null | undefined;
  const byStatus: Record<string, unknown> = data?.by_status || {};

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
  clearAllCrossFilter();
  resetHierarchyState();
}

async function checkCacheStatus(): Promise<void> {
  try {
    const healthRaw = await apiGet('/health', { timeout: 15000, retries: 0, silent: true });
    const health = healthRaw as { equipment_status_cache?: { updated_at?: string } } | null | undefined;
    const updated = health?.equipment_status_cache?.updated_at;
    if (updated) {
      const d = new Date(updated);
      const pad = (n: number): string => String(n).padStart(2, '0');
      lastUpdate.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } else {
      lastUpdate.value = '--';
    }
  } catch {
    lastUpdate.value = '--';
  }
}

function buildSingleFilterLabel(filter: MatrixFilter): string {
  const parts = [filter.workcenter_group];
  if (filter.family) {
    parts.push(filter.family);
  }
  if (filter.resource) {
    const resource = allEquipment.value.find((item) => item.RESOURCEID === filter.resource);
    parts.push(resource?.RESOURCENAME || filter.resource);
  }
  parts.push(STATUS_DISPLAY_MAP[filter.status] || filter.status);
  return parts.join(' / ');
}

function filterKey(f: MatrixFilter): string {
  return `${f.workcenter_group}|${f.status}|${f.family || ''}|${f.resource || ''}`;
}

function matchSingleFilter(eq: EquipmentItem, filter: MatrixFilter): boolean {
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

// displayedEquipment replaced by useCrossFilter.filteredEquipment

const activeFilterText = computed(() => {
  return activeSelections.value.map((s) => s.label).join(' | ');
});

function applyMatrixFilter(nextFilter: MatrixFilter): void {
  captureLastTrigger();
  const entry: MatrixFilter = {
    workcenter_group: nextFilter.workcenter_group,
    status: nextFilter.status,
    family: nextFilter.family || null,
    resource: nextFilter.resource || null,
  };
  const label = buildSingleFilterLabel(entry);
  const existing = activeSelections.value.find((s) => s.source === 'matrix');
  if (existing) {
    const existingMeta = (existing as { source: string; label: string; _meta?: MatrixFilter })._meta;
    if (
      existingMeta &&
      filterKey(existingMeta) === filterKey(entry)
    ) {
      removeSelection('matrix');
      return;
    }
  }
  const sel = Object.assign(
    {
      source: 'matrix' as CrossFilterSource,
      label: `矩陣篩選: ${label}`,
      predicate: (row: { WORKCENTER_GROUP: string; RESOURCEFAMILYNAME?: string; RESOURCEID?: string; EQUIPMENTASSETSSTATUS: string }) =>
        matchSingleFilter(row as Parameters<typeof matchSingleFilter>[0], entry),
    },
    { _meta: entry }
  );
  addSelection(sel);
}

function clearAllEquipmentFilters() {
  const trigger = lastClickedTrigger.value;
  clearAllCrossFilter();
  nextTick(() => {
    trigger?.focus();
  });
}

function toggleSummaryStatus(status: string): void {
  captureLastTrigger();
  const existing = activeSelections.value.find((s) => s.source === 'summary');
  const existingMeta = (existing as { source: string; label: string; _meta?: { status: string } } | undefined)?._meta;
  if (existingMeta?.status === status) {
    removeSelection('summary');
  } else {
    const sel = Object.assign(
      {
        source: 'summary' as CrossFilterSource,
        label: `卡片篩選: ${STATUS_DISPLAY_MAP[status] || status}`,
        predicate: (row: { EQUIPMENTASSETSSTATUS: string }) =>
          normalizeStatus(row.EQUIPMENTASSETSSTATUS) === status,
      },
      { _meta: { status } }
    );
    addSelection(sel);
  }
}


function handleRingSelect(payload: { source: 'ring'; group: string; status: string } | null): void {
  captureLastTrigger();
  if (!payload) {
    removeSelection('ring');
    return;
  }
  const { group, status } = payload;
  const existing = activeSelections.value.find((s) => s.source === 'ring');
  const existingMeta = (existing as { _meta?: { group: string; status: string } } | undefined)?._meta;
  if (existingMeta?.group === group && existingMeta?.status === status) {
    removeSelection('ring');
    return;
  }
  const label = `Ring: ${group} / ${status}`;
  const sel = Object.assign(
    {
      source: 'ring' as CrossFilterSource,
      label,
      predicate: (row: { WORKCENTER_GROUP: string; EQUIPMENTASSETSSTATUS: string }) =>
        (row.WORKCENTER_GROUP || 'UNKNOWN') === group && normalizeStatus(row.EQUIPMENTASSETSSTATUS) === status,
    },
    { _meta: { group, status } }
  );
  addSelection(sel);
}

function handleHeatmapSelect(payload: { source: 'heatmap'; group: string; packageGroupName: string } | null): void {
  captureLastTrigger();
  if (!payload) {
    removeSelection('heatmap');
    return;
  }
  const { group, packageGroupName } = payload;
  const normPkg = packageGroupName?.trim() || '—';
  const existing = activeSelections.value.find((s) => s.source === 'heatmap');
  const existingMeta = (existing as { _meta?: { group: string; packageGroupName: string } } | undefined)?._meta;
  if (existingMeta?.group === group && existingMeta?.packageGroupName === normPkg) {
    removeSelection('heatmap');
    return;
  }
  const label = `Heatmap: ${group} / ${normPkg}`;
  const sel = Object.assign(
    {
      source: 'heatmap' as CrossFilterSource,
      label,
      predicate: (row: { WORKCENTER_GROUP: string; PACKAGEGROUPNAME?: string | null }) =>
        (row.WORKCENTER_GROUP || 'UNKNOWN') === group && (row.PACKAGEGROUPNAME?.trim() || '—') === normPkg,
    },
    { _meta: { group, packageGroupName: normPkg } }
  );
  addSelection(sel);
}

function handleAlertSelect(payload: { source: 'alerts'; resourceId: string } | null): void {
  captureLastTrigger();
  if (!payload) {
    removeSelection('alerts');
    return;
  }
  const { resourceId } = payload;
  const existing = activeSelections.value.find((s) => s.source === 'alerts');
  const existingMeta = (existing as { _meta?: { resourceId: string } } | undefined)?._meta;
  if (existingMeta?.resourceId === resourceId) {
    removeSelection('alerts');
    return;
  }
  const label = `告警: ${resourceId}`;
  const sel = Object.assign(
    {
      source: 'alerts' as CrossFilterSource,
      label,
      predicate: (row: { RESOURCEID: string }) => row.RESOURCEID === resourceId,
    },
    { _meta: { resourceId } }
  );
  addSelection(sel);
}

function handleEscClear(event: KeyboardEvent): void {
  // Capture trigger before clearing (button is v-if'd and will be removed from DOM)
  const trigger = lastClickedTrigger.value;
  clearAllCrossFilter();
  nextTick(() => {
    // Return focus to the last chart element that was clicked; fall back to
    // the button itself if no prior chart interaction has occurred.
    (trigger ?? (event.target as HTMLElement))?.focus();
  });
}

function handleGlobalEsc(): void {
  if (hasActiveSelections.value) {
    const trigger = lastClickedTrigger.value;
    clearAllCrossFilter();
    nextTick(() => {
      trigger?.focus();
    });
  }
}

function handleToggleRow(rowId: string): void {
  hierarchyState[rowId] = !hierarchyState[rowId];
}

function handleToggleAllRows({ expand, rowIds }: { expand: boolean; rowIds: string[] }): void {
  (rowIds || []).forEach((rowId) => {
    hierarchyState[rowId] = Boolean(expand);
  });
}

function closeTooltip() {
  tooltipState.visible = false;
  tooltipState.payload = null;
}

function openLotTooltip({ x, y, equipment }: { x: number; y: number; equipment: EquipmentItem }): void {
  const lotDetails = equipment?.LOT_DETAILS;
  if (!Array.isArray(lotDetails) || lotDetails.length === 0) {
    return;
  }

  tooltipState.type = 'lot';
  tooltipState.payload = lotDetails;
  tooltipState.position = { x, y };
  tooltipState.visible = true;
}

function openJobTooltip({ x, y, equipment }: { x: number; y: number; equipment: EquipmentItem }): void {
  if (!equipment?.JOBORDER) {
    return;
  }

  tooltipState.type = 'job';
  tooltipState.payload = equipment;
  tooltipState.position = { x, y };
  tooltipState.visible = true;
}

async function loadData(showOverlay = false): Promise<void> {
  if (showOverlay) {
    loading.initial = true;
  }

  loading.refreshing = true;
  summaryError.value = '';
  equipmentError.value = '';

  const [summaryResult, equipmentResult] = await Promise.allSettled([loadSummary(), loadEquipment()]);
  void checkCacheStatus();

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

function updateGroups(groups: string[]): void {
  updateField('groups', groups || []);
}

function updateFlags(nextFlags: { isProduction?: boolean; isKey?: boolean; isMonitor?: boolean }): void {
  const keys = ['isProduction', 'isKey', 'isMonitor'] as const;
  for (const key of keys) {
    const next = Boolean(nextFlags?.[key]);
    if (next !== filterState[key]) {
      updateField(key, next);
    }
  }
}

function updateFamilies(families: string[]): void {
  updateField('families', families || []);
}

function updateMachines(machines: string[]): void {
  updateField('machines', machines || []);
}

function updatePackageGroups(groups: string[]): void {
  updateField('packageGroups', groups || []);
}

const { resetAutoRefresh } = useAutoRefresh({
  onRefresh: () => loadData(false),
  intervalMs: 5 * 60 * 1000,
  autoStart: true,
  refreshOnVisible: true,
});

async function initPage(): Promise<void> {
  try {
    await loadOptions();
  } catch (error) {
    equipmentError.value = (error as Error)?.message || '載入篩選選項失敗';
  }
  await loadData(true);
}

onMounted(() => {
  void initPage();
});
</script>

<template>
  <div class="resource-page theme-resource" @keydown.esc="handleGlobalEsc">
    <div class="dashboard">

      <FilterBar
        :workcenter-groups="workcenterGroups"
        :selected-groups="filterState.groups"
        :flags="filterState"
        :family-options="familyOptions"
        :machine-options="machineOptions"
        :selected-families="filterState.families"
        :selected-machines="filterState.machines"
        :package-groups="packageGroups"
        :selected-package-groups="filterState.packageGroups"
        :loading="loading.options || loading.refreshing"
        @change-groups="updateGroups"
        @change-flags="updateFlags"
        @change-families="updateFamilies"
        @change-machines="updateMachines"
        @change-package-groups="updatePackageGroups"
      />

      <ErrorBanner :message="summaryError" @dismiss="summaryError = ''" />

      <SummaryCardGroup columns="auto">
        <SummaryCard
          label="OU%"
          :value="summary.ouPct"
          format="percent"
          :accent="resolveOuAccent(summary.ouPct)"
        >
          <template #sub>稼動率</template>
        </SummaryCard>
        <SummaryCard
          label="AVAIL%"
          :value="summary.availabilityPct"
          format="percent"
          :accent="resolveOuAccent(summary.availabilityPct)"
        >
          <template #sub>可用率</template>
        </SummaryCard>
        <SummaryCard
          v-for="status in MATRIX_STATUS_COLUMNS"
          :key="status"
          :label="status"
          :value="Number(summary.byStatus?.[status] || 0)"
          format="number"
          :accent="STATUS_ACCENT_MAP[status] || 'neutral'"
          clickable
          :active="activeSelections.some((s) => s.source === 'summary' && (s as any)._meta?.status === status)"
          @click="toggleSummaryStatus(status)"
        >
          <template #sub>{{ statusPctSub(status) }}</template>
        </SummaryCard>
        <SummaryCard
          label="Total"
          :value="summary.totalCount"
          format="number"
          accent="brand"
        >
          <template #sub>設備總數</template>
        </SummaryCard>
      </SummaryCardGroup>

      <ErrorBanner :message="equipmentError" @dismiss="equipmentError = ''" />

      <WorkcenterOuRings
        :equipment="getInputForChart('ring').value"
        :selection="ringSelection"
        @chart-select="handleRingSelect"
      />

      <OuHeatmap
        :equipment="getInputForChart('heatmap').value"
        :selected-cell="heatmapSelectedCell"
        @cell-select="handleHeatmapSelect"
      />

      <MaintenanceAlerts
        :equipment="getInputForChart('alerts').value"
        :last-update="lastUpdate"
        :selected-id="alertsSelectedId"
        @show-job="(p: { x: number; y: number; equipment: unknown }) => openJobTooltip(p as { x: number; y: number; equipment: EquipmentItem })"
        @alert-select="handleAlertSelect"
      />

      <MatrixSection
        :equipment="getInputForChart('matrix').value"
        :expanded-state="hierarchyState"
        :matrix-filter="[]"
        :active-selection="matrixActiveSelection"
        @toggle-row="handleToggleRow"
        @toggle-all="handleToggleAllRows"
        @cell-filter="applyMatrixFilter"
      />

      <div v-if="hasActiveSelections" class="cross-filter-clear-btn-wrap">
        <button type="button" class="cross-filter-clear-btn" @click="clearAllEquipmentFilters" @keydown.esc.stop="handleEscClear($event)">清除全部篩選</button>
      </div>
      <EquipmentGrid
        v-if="hasActiveSelections"
        :equipment="filteredEquipment"
        :active-filter-text="activeFilterText"
        @clear-filter="clearAllEquipmentFilters"
        @show-lot="openLotTooltip"
        @show-job="openJobTooltip"
      />
    </div>

    <LoadingOverlay v-if="loading.initial || loading.refreshing" tier="page" />

    <FloatingTooltip
      :visible="tooltipState.visible"
      :type="tooltipState.type"
      :payload="tooltipState.payload"
      :position="tooltipState.position"
      @close="closeTooltip"
    />
  </div>
</template>
