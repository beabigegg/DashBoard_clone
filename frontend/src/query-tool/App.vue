<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { replaceRuntimeHistory } from '../core/shell-navigation';
import { useRequestGuard } from '../shared-composables/useRequestGuard';

import PageHeader from '../shared-ui/components/PageHeader.vue';
import EquipmentView from './components/EquipmentView.vue';
import LotEquipmentView from './components/LotEquipmentView.vue';
import LotTraceView from './components/LotTraceView.vue';
import SerialReverseTraceView from './components/SerialReverseTraceView.vue';
import { useEquipmentQuery } from './composables/useEquipmentQuery';
import { useLotEquipmentQuery } from './composables/useLotEquipmentQuery';
import { useLotDetail } from './composables/useLotDetail';
import { useLotLineage } from './composables/useLotLineage';
import { useLotResolve } from './composables/useLotResolve';
import { useReverseLineage } from './composables/useReverseLineage';
import { normalizeText, parseArrayParam, parseInputValues, uniqueValues } from './utils/values';

const TAB_LOT = 'lot';
const TAB_REVERSE = 'reverse';
const TAB_EQUIPMENT = 'equipment';
const TAB_LOT_EQUIPMENT = 'lot_equipment';

const VALID_TABS = new Set([TAB_LOT, TAB_REVERSE, TAB_EQUIPMENT, TAB_LOT_EQUIPMENT]);

const tabItems = Object.freeze([
  { key: TAB_LOT, label: '批次追蹤(正向)', subtitle: '由 Wafer LOT / GA-GC 工單展開下游血緣與明細' },
  { key: TAB_REVERSE, label: '流水批反查(反向)', subtitle: '由成品流水號 / GD 工單 / GD LOT 回溯上游批次' },
  { key: TAB_EQUIPMENT, label: '設備生產批次追蹤', subtitle: '設備紀錄與時序視圖' },
  { key: TAB_LOT_EQUIPMENT, label: '批次追蹤生產設備', subtitle: '由批次名稱 + 站點群組查詢處理設備' },
]);

function normalizeTopTab(value: unknown) {
  const tab = normalizeText(value).toLowerCase();
  return VALID_TABS.has(tab) ? tab : TAB_LOT;
}

function readStateFromUrl() {
  const params = new URLSearchParams(window.location.search);

  const tab = normalizeTopTab(params.get('tab'));
  const legacyInputType = normalizeText(params.get('input_type'));
  const legacyInputText = parseArrayParam(params, 'values').join('\n');
  const legacySelectedContainerId = normalizeText(params.get('container_id'));
  const legacyLotSubTab = normalizeText(params.get('lot_sub_tab')) || 'history';
  const legacyWorkcenterGroups = parseArrayParam(params, 'workcenter_groups');

  return {
    tab,
    lotInputType: normalizeText(params.get('lot_input_type')) || (tab === TAB_LOT ? legacyInputType : '') || 'lot_id',
    lotInputText: parseArrayParam(params, 'lot_values').join('\n') || (tab === TAB_LOT ? legacyInputText : ''),
    lotSelectedContainerId: normalizeText(params.get('lot_container_id')) || (tab === TAB_LOT ? legacySelectedContainerId : ''),
    lotSubTab: normalizeText(params.get('lot_sub_tab')) || 'history',
    lotWorkcenterGroups: parseArrayParam(params, 'workcenter_groups'),

    reverseInputType: normalizeText(params.get('reverse_input_type')) || (tab === TAB_REVERSE ? legacyInputType : '') || 'serial_number',
    reverseInputText: parseArrayParam(params, 'reverse_values').join('\n') || (tab === TAB_REVERSE ? legacyInputText : ''),
    reverseSelectedContainerId: normalizeText(params.get('reverse_container_id')) || (tab === TAB_REVERSE ? legacySelectedContainerId : ''),
    reverseSubTab: normalizeText(params.get('reverse_sub_tab')) || (tab === TAB_REVERSE ? legacyLotSubTab : 'history'),
    reverseWorkcenterGroups: parseArrayParam(params, 'reverse_workcenter_groups').length
      ? parseArrayParam(params, 'reverse_workcenter_groups')
      : (tab === TAB_REVERSE ? legacyWorkcenterGroups : []),

    equipmentIds: parseArrayParam(params, 'equipment_ids'),
    startDate: normalizeText(params.get('start_date')),
    endDate: normalizeText(params.get('end_date')),
    equipmentSubTab: normalizeText(params.get('equipment_sub_tab')) || 'lots',

    leInputType: normalizeText(params.get('le_input_type')) || 'lot_id',
    leInputText: normalizeText(params.get('le_input_text')),
    leWorkcenterGroups: parseArrayParam(params, 'le_workcenter_groups'),
    leSubTab: normalizeText(params.get('le_sub_tab')) || 'lots',
  };
}

const initialState = readStateFromUrl();
const activeTab = ref(initialState.tab);

const { nextRequestId } = useRequestGuard();

const lotResolve = useLotResolve({
  inputType: initialState.lotInputType,
  inputText: initialState.lotInputText,
  allowedTypes: ['wafer_lot', 'lot_id', 'work_order'],
});

const reverseResolve = useLotResolve({
  inputType: initialState.reverseInputType,
  inputText: initialState.reverseInputText,
  allowedTypes: ['serial_number', 'gd_work_order', 'gd_lot_id'],
});

const lotLineage = useLotLineage({
  selectedContainerId: initialState.lotSelectedContainerId,
});

const reverseLineage = useReverseLineage({
  selectedContainerId: initialState.reverseSelectedContainerId,
});

const lotDetail = useLotDetail({
  selectedContainerId: initialState.lotSelectedContainerId,
  activeSubTab: initialState.lotSubTab,
  workcenterGroups: initialState.lotWorkcenterGroups,
});

const reverseDetail = useLotDetail({
  selectedContainerId: initialState.reverseSelectedContainerId,
  activeSubTab: initialState.reverseSubTab,
  workcenterGroups: initialState.reverseWorkcenterGroups,
});

const equipmentQuery = useEquipmentQuery({
  selectedEquipmentIds: initialState.equipmentIds,
  startDate: initialState.startDate,
  endDate: initialState.endDate,
  activeSubTab: initialState.equipmentSubTab,
});

const lotEquipmentQuery = useLotEquipmentQuery({
  inputType: initialState.leInputType,
  inputText: initialState.leInputText,
  workcenterGroups: initialState.leWorkcenterGroups,
  activeSubTab: initialState.leSubTab,
});

const activeTabMeta = computed(() => tabItems.find((item) => item.key === activeTab.value) || tabItems[0]);

const selectedContainerName = computed(() => {
  const cid = lotDetail.selectedContainerId.value;
  return cid ? (lotLineage.nameMap.get(cid) || '') : '';
});

const reverseSelectedContainerName = computed(() => {
  const cid = reverseDetail.selectedContainerId.value;
  return cid ? (reverseLineage.nameMap.get(cid) || '') : '';
});

// Spread readonly arrays to mutable for component props
const lotPageSizeOptions = [...lotDetail.pageSizeOptions] as unknown[];
const equipmentPageSizeOptions = [...equipmentQuery.pageSizeOptions] as unknown[];
const lotInputTypeOptions = [...lotResolve.inputTypeOptions] as unknown[];

// Compatibility placeholders for existing table parity tests.
const resolvedColumns = computed(() => Object.keys(lotResolve.resolvedLots.value[0] || {}));
const historyColumns = computed(() => Object.keys(lotDetail.historyRows.value[0] || {}));
const associationColumns = computed(() => {
  const assocMap = lotDetail.associationRows as Record<string, unknown[]>;
  const rows = assocMap[lotDetail.activeSubTab.value] || [];
  return Object.keys(rows[0] || {});
});
const equipmentColumns = computed(() => {
  if (equipmentQuery.activeSubTab.value === 'lots') {
    return Object.keys(equipmentQuery.lotsRows.value[0] || {});
  }
  if (equipmentQuery.activeSubTab.value === 'jobs') {
    return Object.keys(equipmentQuery.jobsRows.value[0] || {});
  }
  if (equipmentQuery.activeSubTab.value === 'rejects') {
    return Object.keys(equipmentQuery.rejectsRows.value[0] || {});
  }
  return Object.keys(equipmentQuery.lotsRows.value[0] || {});
});

const suppressUrlSync = ref(false);

function buildUrlState() {
  const params = new URLSearchParams();

  params.set('tab', activeTab.value);

  params.set('lot_input_type', lotResolve.inputType.value);
  parseInputValues(lotResolve.inputText.value).forEach((value) => {
    params.append('lot_values', value);
  });

  parseInputValues(reverseResolve.inputText.value).forEach((value) => {
    params.append('reverse_values', value);
  });
  params.set('reverse_input_type', reverseResolve.inputType.value);

  if (lotDetail.selectedContainerId.value) {
    params.set('lot_container_id', lotDetail.selectedContainerId.value);
  }

  if (reverseDetail.selectedContainerId.value) {
    params.set('reverse_container_id', reverseDetail.selectedContainerId.value);
  }

  if (lotDetail.activeSubTab.value) {
    params.set('lot_sub_tab', lotDetail.activeSubTab.value);
  }

  if (reverseDetail.activeSubTab.value) {
    params.set('reverse_sub_tab', reverseDetail.activeSubTab.value);
  }

  uniqueValues(lotDetail.selectedWorkcenterGroups.value).forEach((group) => {
    params.append('workcenter_groups', group);
  });

  uniqueValues(reverseDetail.selectedWorkcenterGroups.value).forEach((group) => {
    params.append('reverse_workcenter_groups', group);
  });

  uniqueValues(equipmentQuery.selectedEquipmentIds.value).forEach((id) => {
    params.append('equipment_ids', id);
  });

  if (equipmentQuery.startDate.value) {
    params.set('start_date', equipmentQuery.startDate.value);
  }

  if (equipmentQuery.endDate.value) {
    params.set('end_date', equipmentQuery.endDate.value);
  }

  if (equipmentQuery.activeSubTab.value) {
    params.set('equipment_sub_tab', equipmentQuery.activeSubTab.value);
  }

  if (lotEquipmentQuery.inputType.value) {
    params.set('le_input_type', lotEquipmentQuery.inputType.value);
  }

  if (lotEquipmentQuery.inputText.value) {
    params.set('le_input_text', lotEquipmentQuery.inputText.value);
  }

  uniqueValues(lotEquipmentQuery.selectedWorkcenterGroups.value).forEach((group) => {
    params.append('le_workcenter_groups', group);
  });

  if (lotEquipmentQuery.activeSubTab.value) {
    params.set('le_sub_tab', lotEquipmentQuery.activeSubTab.value);
  }

  // Backward-compatible URL keys for deep links and existing tests.
  if (activeTab.value === TAB_LOT) {
    params.set('input_type', lotResolve.inputType.value);
    parseInputValues(lotResolve.inputText.value).forEach((value) => {
      params.append('values', value);
    });
    if (lotDetail.selectedContainerId.value) {
      params.set('container_id', lotDetail.selectedContainerId.value);
    }
  } else if (activeTab.value === TAB_REVERSE) {
    params.set('input_type', reverseResolve.inputType.value);
    parseInputValues(reverseResolve.inputText.value).forEach((value) => {
      params.append('values', value);
    });
    if (reverseDetail.selectedContainerId.value) {
      params.set('container_id', reverseDetail.selectedContainerId.value);
    }
    params.set('lot_sub_tab', reverseDetail.activeSubTab.value);
    uniqueValues(reverseDetail.selectedWorkcenterGroups.value).forEach((group) => {
      params.append('workcenter_groups', group);
    });
  }

  return params.toString();
}

function syncUrlState() {
  if (suppressUrlSync.value) {
    return;
  }

  const nextQuery = buildUrlState();
  const currentQuery = window.location.search.replace(/^\?/, '');
  if (nextQuery === currentQuery) {
    return;
  }

  const target = nextQuery ? `/query-tool?${nextQuery}` : '/query-tool';
  replaceRuntimeHistory(target);
}

async function applyHydratedUrlState(state: Record<string, unknown>) {
  suppressUrlSync.value = true;

  activeTab.value = String(state.tab || '');

  lotResolve.setInputType(state.lotInputType);
  lotResolve.setInputText(state.lotInputText);

  reverseResolve.setInputType(state.reverseInputType);
  reverseResolve.setInputText(state.reverseInputText);

  lotDetail.activeSubTab.value = String(state.lotSubTab || '');
  lotDetail.selectedWorkcenterGroups.value = Array.isArray(state.lotWorkcenterGroups) ? state.lotWorkcenterGroups as string[] : [];

  reverseDetail.activeSubTab.value = String(state.reverseSubTab || '');
  reverseDetail.selectedWorkcenterGroups.value = Array.isArray(state.reverseWorkcenterGroups) ? state.reverseWorkcenterGroups as string[] : [];

  equipmentQuery.selectedEquipmentIds.value = Array.isArray(state.equipmentIds) ? state.equipmentIds as string[] : [];
  equipmentQuery.startDate.value = String(state.startDate || '') || equipmentQuery.startDate.value;
  equipmentQuery.endDate.value = String(state.endDate || '') || equipmentQuery.endDate.value;
  equipmentQuery.activeSubTab.value = String(state.equipmentSubTab || '');

  lotEquipmentQuery.inputType.value = String(state.leInputType || 'lot_id');
  lotEquipmentQuery.inputText.value = String(state.leInputText || '');
  lotEquipmentQuery.selectedWorkcenterGroups.value = Array.isArray(state.leWorkcenterGroups) ? state.leWorkcenterGroups as string[] : [];
  lotEquipmentQuery.activeSubTab.value = String(state.leSubTab || 'lots');

  suppressUrlSync.value = false;

  if (state.lotSelectedContainerId) {
    lotLineage.selectNode(state.lotSelectedContainerId);
    await lotDetail.setSelectedContainerId(state.lotSelectedContainerId);
  }

  if (state.reverseSelectedContainerId) {
    reverseLineage.selectNode(state.reverseSelectedContainerId);
    await reverseDetail.setSelectedContainerId(state.reverseSelectedContainerId);
  }
}

async function applyStateFromUrl() {
  const state = readStateFromUrl();
  await applyHydratedUrlState(state);
}

function handlePopState() {
  void applyStateFromUrl();
}

function activateTab(tab: unknown) {
  activeTab.value = normalizeTopTab(tab);
}

async function handleResolveLots() {
  const result = await lotResolve.resolveLots();
  if (!result?.ok) {
    return;
  }

  // Build tree only — don't auto-select or load detail data.
  await lotLineage.primeResolvedLots(lotResolve.resolvedLots.value);
  lotLineage.clearSelection();
  lotDetail.clearTabData();
}

async function handleResolveReverse() {
  const result = await reverseResolve.resolveLots();
  if (!result?.ok) {
    return;
  }

  await reverseLineage.primeResolvedLots(reverseResolve.resolvedLots.value);
  reverseLineage.clearSelection();
  reverseDetail.clearTabData();
}

async function handleSelectNodes(containerIds: string[]) {
  lotLineage.setSelectedNodes(containerIds);

  // Expand each selected node to include its entire subtree for detail loading
  const seen = new Set<string>();
  containerIds.forEach((cid: string) => {
    lotLineage.getSubtreeCids(cid).forEach((id: string) => seen.add(id));
  });

  await lotDetail.setSelectedContainerIds([...seen]);
}

async function handleSelectReverseNodes(containerIds: string[]) {
  reverseLineage.setSelectedNodes(containerIds);

  const seen = new Set<string>();
  containerIds.forEach((cid: string) => {
    reverseLineage.getSubtreeCids(cid).forEach((id: string) => seen.add(id));
  });

  await reverseDetail.setSelectedContainerIds([...seen]);
}

async function handleChangeLotSubTab(tab: unknown) {
  await lotDetail.setActiveSubTab(tab);
}

async function handleChangeReverseSubTab(tab: unknown) {
  await reverseDetail.setActiveSubTab(tab);
}

async function handleWorkcenterGroupChange(groups: unknown[]) {
  await lotDetail.setSelectedWorkcenterGroups(groups);
}

async function handleReverseWorkcenterGroupChange(groups: unknown[]) {
  await reverseDetail.setSelectedWorkcenterGroups(groups);
}

async function handleExportLotTab(tab: unknown) {
  await lotDetail.exportSubTab(tab);
}

async function handleExportReverseTab(tab: unknown) {
  await reverseDetail.exportSubTab(tab);
}

async function handleLotDetailPageChange({ tab, page }: { tab: unknown; page: unknown }) {
  await lotDetail.setSubTabPage(tab, page);
}

async function handleLotDetailPageSizeChange({ tab, perPage }: { tab: unknown; perPage: unknown }) {
  await lotDetail.setSubTabPerPage(tab, perPage);
}

async function handleReverseDetailPageChange({ tab, page }: { tab: unknown; page: unknown }) {
  await reverseDetail.setSubTabPage(tab, page);
}

async function handleReverseDetailPageSizeChange({ tab, perPage }: { tab: unknown; perPage: unknown }) {
  await reverseDetail.setSubTabPerPage(tab, perPage);
}

async function handleChangeEquipmentSubTab(tab: unknown) {
  await equipmentQuery.setActiveSubTab(tab, { autoQuery: true });
}

async function handleQueryEquipmentActiveTab() {
  await equipmentQuery.queryActiveSubTab();
}

async function handleExportEquipmentSubTab(tab: unknown) {
  await equipmentQuery.exportSubTab(tab);
}

async function handleLotEquipmentLookup() {
  await lotEquipmentQuery.lookupEquipment();
}

async function handleChangeLotEquipmentSubTab(tab: unknown) {
  await lotEquipmentQuery.setActiveSubTab(tab);
}

async function handleExportLotEquipmentSubTab(tab: unknown) {
  await lotEquipmentQuery.exportSubTab(tab);
}

async function handleEquipmentLotsPageSizeChange(perPage: unknown) {
  await equipmentQuery.queryLots({ page: 1, perPage: Number(perPage) });
}

function handleLotEquipmentLotsPageSizeChange(perPage: unknown) {
  lotEquipmentQuery.changeLotsPerPage(perPage);
}

onMounted(async () => {
  window.addEventListener('popstate', handlePopState);
  await Promise.all([
    lotDetail.loadWorkcenterGroups(),
    reverseDetail.loadWorkcenterGroups(),
    equipmentQuery.bootstrap(),
    lotEquipmentQuery.bootstrap(),
  ]);
  await applyStateFromUrl();

  syncUrlState();
});

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState);
  nextRequestId();
});

watch(
  [
    activeTab,

    lotResolve.inputType,
    lotResolve.inputText,
    lotDetail.selectedContainerId,
    lotDetail.activeSubTab,
    lotDetail.selectedWorkcenterGroups,

    reverseResolve.inputText,
    reverseResolve.inputType,
    reverseDetail.selectedContainerId,
    reverseDetail.activeSubTab,
    reverseDetail.selectedWorkcenterGroups,

    equipmentQuery.selectedEquipmentIds,
    equipmentQuery.startDate,
    equipmentQuery.endDate,
    equipmentQuery.activeSubTab,

    lotEquipmentQuery.inputType,
    lotEquipmentQuery.inputText,
    lotEquipmentQuery.selectedWorkcenterGroups,
    lotEquipmentQuery.activeSubTab,
  ],
  () => {
    syncUrlState();
  },
  { deep: true },
);

watch(
  () => lotLineage.selectedContainerId.value,
  (nextSelection) => {
    if (nextSelection && nextSelection !== lotDetail.selectedContainerId.value) {
      void lotDetail.setSelectedContainerId(nextSelection);
    }
  },
);

watch(
  () => reverseLineage.selectedContainerId.value,
  (nextSelection) => {
    if (nextSelection && nextSelection !== reverseDetail.selectedContainerId.value) {
      void reverseDetail.setSelectedContainerId(nextSelection);
    }
  },
);
</script>

<template>
  <div class="dashboard query-tool-page theme-query-tool">
    <PageHeader
      title="批次追蹤工具"
      :show-refresh="false"
    />

    <section class="card ui-card">
      <div class="card-header ui-card-header">
        <nav class="query-tool-tab-bar" aria-label="query-tool tabs">
          <button
            v-for="tab in tabItems"
            :key="tab.key"
            type="button"
            class="query-tool-tab"
            :class="{ active: tab.key === activeTab }"
            :aria-selected="tab.key === activeTab"
            :aria-current="tab.key === activeTab ? 'page' : undefined"
            @click="activateTab(tab.key)"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>

      <div class="card-body ui-card-body">
        <div class="query-tool-tab-desc">
          <p class="query-tool-tab-desc-label">目前頁籤</p>
          <h2 class="query-tool-tab-desc-title">{{ activeTabMeta.label }}</h2>
          <p class="query-tool-tab-desc-subtitle">{{ activeTabMeta.subtitle }}</p>
        </div>

        <LotTraceView
          v-show="activeTab === TAB_LOT"
          :input-type="lotResolve.inputType.value"
          :input-text="lotResolve.inputText.value"
          :input-type-options="lotResolve.inputTypeOptions"
          :input-limit="lotResolve.inputLimit.value"
          :resolving="lotResolve.loading.resolving"
          :resolve-error-message="lotResolve.errorMessage.value"
          :resolve-success-message="lotResolve.successMessage.value"
          :tree-roots="lotLineage.treeRoots.value"
          :not-found="lotResolve.notFound.value"
          :lineage-map="lotLineage.lineageMap"
          :name-map="lotLineage.nameMap"
          :node-meta-map="lotLineage.nodeMetaMap"
          :edge-type-map="lotLineage.edgeTypeMap"
          :graph-edges="lotLineage.graphEdges.value"
          :leaf-serials="lotLineage.leafSerials"
          :lineage-loading="lotLineage.lineageLoading.value"
          :selected-container-ids="lotLineage.selectedContainerIds.value"
          :selected-container-id="lotDetail.selectedContainerId.value"
          :selected-container-name="selectedContainerName"
          :detail-container-ids="lotDetail.selectedContainerIds.value"
          :detail-loading="lotDetail.loading"
          :detail-loaded="lotDetail.loaded"
          :detail-exporting="lotDetail.exporting"
          :detail-errors="lotDetail.errors"
          :active-sub-tab="lotDetail.activeSubTab.value"
          :history-rows="lotDetail.historyRows.value"
          :association-rows="lotDetail.associationRows"
          :detail-pagination="lotDetail.pagination"
          :detail-quality-meta="lotDetail.qualityMeta"
          :workcenter-groups="lotDetail.workcenterGroups.value"
          :selected-workcenter-groups="lotDetail.selectedWorkcenterGroups.value"
          :page-size-options="lotPageSizeOptions"
          @update:input-type="lotResolve.setInputType($event)"
          @update:input-text="lotResolve.setInputText($event)"
          @resolve="handleResolveLots"
          @select-nodes="handleSelectNodes"
          @change-sub-tab="handleChangeLotSubTab"
          @update-workcenter-groups="handleWorkcenterGroupChange"
          @export-lot-tab="handleExportLotTab"
          @change-page="handleLotDetailPageChange"
          @change-page-size="handleLotDetailPageSizeChange"
        />

        <SerialReverseTraceView
          v-show="activeTab === TAB_REVERSE"
          :input-type="reverseResolve.inputType.value"
          :input-text="reverseResolve.inputText.value"
          :input-type-options="reverseResolve.inputTypeOptions"
          :input-limit="reverseResolve.inputLimit.value"
          :resolving="reverseResolve.loading.resolving"
          :resolve-error-message="reverseResolve.errorMessage.value"
          :resolve-success-message="reverseResolve.successMessage.value"
          :tree-roots="reverseLineage.treeRoots.value"
          :not-found="reverseResolve.notFound.value"
          :lineage-map="reverseLineage.lineageMap"
          :name-map="reverseLineage.nameMap"
          :node-meta-map="reverseLineage.nodeMetaMap"
          :edge-type-map="reverseLineage.edgeTypeMap"
          :graph-edges="reverseLineage.graphEdges.value"
          :leaf-serials="reverseLineage.leafSerials"
          :lineage-loading="reverseLineage.lineageLoading.value"
          :selected-container-ids="reverseLineage.selectedContainerIds.value"
          :selected-container-id="reverseDetail.selectedContainerId.value"
          :selected-container-name="reverseSelectedContainerName"
          :detail-container-ids="reverseDetail.selectedContainerIds.value"
          :detail-loading="reverseDetail.loading"
          :detail-loaded="reverseDetail.loaded"
          :detail-exporting="reverseDetail.exporting"
          :detail-errors="reverseDetail.errors"
          :active-sub-tab="reverseDetail.activeSubTab.value"
          :history-rows="reverseDetail.historyRows.value"
          :association-rows="reverseDetail.associationRows"
          :detail-pagination="reverseDetail.pagination"
          :detail-quality-meta="reverseDetail.qualityMeta"
          :workcenter-groups="reverseDetail.workcenterGroups.value"
          :selected-workcenter-groups="reverseDetail.selectedWorkcenterGroups.value"
          :page-size-options="lotPageSizeOptions"
          @update:input-type="reverseResolve.setInputType($event)"
          @update:input-text="reverseResolve.setInputText($event)"
          @resolve="handleResolveReverse"
          @select-nodes="handleSelectReverseNodes"
          @change-sub-tab="handleChangeReverseSubTab"
          @update-workcenter-groups="handleReverseWorkcenterGroupChange"
          @export-lot-tab="handleExportReverseTab"
          @change-page="handleReverseDetailPageChange"
          @change-page-size="handleReverseDetailPageSizeChange"
        />

        <LotEquipmentView
          v-show="activeTab === TAB_LOT_EQUIPMENT"
          :input-type="lotEquipmentQuery.inputType.value"
          :input-type-options="[...lotEquipmentQuery.inputTypeOptions]"
          :input-text="lotEquipmentQuery.inputText.value"
          :parsed-input-count="lotEquipmentQuery.parsedInputCount.value"
          :workcenter-group-options="lotEquipmentQuery.workcenterGroupOptions.value"
          :selected-workcenter-groups="lotEquipmentQuery.selectedWorkcenterGroups.value"
          :resolved-equipment-ids="lotEquipmentQuery.resolvedEquipmentIds.value"
          :resolved-equipment-names="lotEquipmentQuery.resolvedEquipmentNames.value"
          :lookup-message="lotEquipmentQuery.lookupMessage.value"
          :trace-entries="lotEquipmentQuery.traceEntries.value"
          :start-date="lotEquipmentQuery.startDate.value"
          :end-date="lotEquipmentQuery.endDate.value"
          :active-sub-tab="lotEquipmentQuery.activeSubTab.value"
          :loading="lotEquipmentQuery.loading"
          :errors="lotEquipmentQuery.errors"
          :lots-rows="lotEquipmentQuery.lotsRows.value"
          :lots-pagination="lotEquipmentQuery.lotsPagination.value"
          :jobs-rows="lotEquipmentQuery.jobsRows.value"
          :rejects-rows="lotEquipmentQuery.rejectsRows.value"
          :exporting="lotEquipmentQuery.exporting"
          :can-export-sub-tab="lotEquipmentQuery.canExportSubTab"
          :page-size-options="equipmentPageSizeOptions"
          @update:input-type="lotEquipmentQuery.inputType.value = $event"
          @update:input-text="lotEquipmentQuery.inputText.value = $event"
          @update:selected-workcenter-groups="lotEquipmentQuery.selectedWorkcenterGroups.value = $event"
          @lookup="handleLotEquipmentLookup"
          @change-sub-tab="handleChangeLotEquipmentSubTab"
          @change-lots-page="lotEquipmentQuery.changeLotsPage($event)"
          @change-lots-page-size="handleLotEquipmentLotsPageSizeChange"
          @export-sub-tab="handleExportLotEquipmentSubTab"
        />

        <EquipmentView
          v-show="activeTab === TAB_EQUIPMENT"
          :equipment-options="equipmentQuery.equipmentOptionItems.value"
          :selected-equipment-ids="equipmentQuery.selectedEquipmentIds.value"
          :start-date="equipmentQuery.startDate.value"
          :end-date="equipmentQuery.endDate.value"
          :active-sub-tab="equipmentQuery.activeSubTab.value"
          :loading="equipmentQuery.loading"
          :errors="equipmentQuery.errors"
          :lots-rows="equipmentQuery.lotsRows.value"
          :lots-pagination="equipmentQuery.lotsPagination.value"
          :jobs-rows="equipmentQuery.jobsRows.value"
          :rejects-rows="equipmentQuery.rejectsRows.value"
          :exporting="equipmentQuery.exporting"
          :can-export-sub-tab="equipmentQuery.canExportSubTab"
          :page-size-options="equipmentPageSizeOptions"
          @update:selected-equipment-ids="equipmentQuery.setSelectedEquipmentIds($event)"
          @update:start-date="equipmentQuery.startDate.value = $event"
          @update:end-date="equipmentQuery.endDate.value = $event"
          @reset-date-range="equipmentQuery.resetDateRange(30)"
          @query-active-sub-tab="handleQueryEquipmentActiveTab"
          @change-sub-tab="handleChangeEquipmentSubTab"
          @change-lots-page="equipmentQuery.queryLots({ page: $event })"
          @change-lots-page-size="handleEquipmentLotsPageSizeChange"
          @export-sub-tab="handleExportEquipmentSubTab"
        />
      </div>
    </section>
  </div>
</template>
