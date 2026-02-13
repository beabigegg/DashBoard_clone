<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { replaceRuntimeHistory } from '../core/shell-navigation.js';

import EquipmentView from './components/EquipmentView.vue';
import LotTraceView from './components/LotTraceView.vue';
import { useEquipmentQuery } from './composables/useEquipmentQuery.js';
import { useLotDetail } from './composables/useLotDetail.js';
import { useLotLineage } from './composables/useLotLineage.js';
import { useLotResolve } from './composables/useLotResolve.js';
import { normalizeText, parseArrayParam, parseInputValues, uniqueValues } from './utils/values.js';

const TAB_LOT = 'lot';
const TAB_EQUIPMENT = 'equipment';

const VALID_TABS = new Set([TAB_LOT, TAB_EQUIPMENT]);

const tabItems = Object.freeze([
  { key: TAB_LOT, label: 'LOT 追蹤', subtitle: '血緣樹與批次詳情' },
  { key: TAB_EQUIPMENT, label: '設備查詢', subtitle: '設備紀錄與時序視圖' },
]);

function normalizeTopTab(value) {
  const tab = normalizeText(value).toLowerCase();
  return VALID_TABS.has(tab) ? tab : TAB_LOT;
}

function readStateFromUrl() {
  const params = new URLSearchParams(window.location.search);

  return {
    tab: normalizeTopTab(params.get('tab')),
    inputType: normalizeText(params.get('input_type')) || 'lot_id',
    inputText: parseArrayParam(params, 'values').join('\n'),
    selectedContainerId: normalizeText(params.get('container_id')),
    lotSubTab: normalizeText(params.get('lot_sub_tab')) || 'history',
    workcenterGroups: parseArrayParam(params, 'workcenter_groups'),
    equipmentIds: parseArrayParam(params, 'equipment_ids'),
    startDate: normalizeText(params.get('start_date')),
    endDate: normalizeText(params.get('end_date')),
    equipmentSubTab: normalizeText(params.get('equipment_sub_tab')) || 'lots',
  };
}

const initialState = readStateFromUrl();
const activeTab = ref(initialState.tab);

const lotResolve = useLotResolve({
  inputType: initialState.inputType,
  inputText: initialState.inputText,
});

const lotLineage = useLotLineage({
  selectedContainerId: initialState.selectedContainerId,
});

const lotDetail = useLotDetail({
  selectedContainerId: initialState.selectedContainerId,
  activeSubTab: initialState.lotSubTab,
  workcenterGroups: initialState.workcenterGroups,
});

const equipmentQuery = useEquipmentQuery({
  selectedEquipmentIds: initialState.equipmentIds,
  startDate: initialState.startDate,
  endDate: initialState.endDate,
  activeSubTab: initialState.equipmentSubTab,
});

const activeTabMeta = computed(() => tabItems.find((item) => item.key === activeTab.value) || tabItems[0]);

const selectedContainerName = computed(() => {
  const cid = lotDetail.selectedContainerId.value;
  return cid ? (lotLineage.nameMap.get(cid) || '') : '';
});

// Compatibility placeholders for existing table parity tests.
const resolvedColumns = computed(() => Object.keys(lotResolve.resolvedLots.value[0] || {}));
const historyColumns = computed(() => Object.keys(lotDetail.historyRows.value[0] || {}));
const associationColumns = computed(() => {
  const rows = lotDetail.associationRows[lotDetail.activeSubTab.value] || [];
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
  return Object.keys(equipmentQuery.statusRows.value[0] || {});
});

const suppressUrlSync = ref(false);

function buildUrlState() {
  const params = new URLSearchParams();

  params.set('tab', activeTab.value);
  params.set('input_type', lotResolve.inputType.value);

  parseInputValues(lotResolve.inputText.value).forEach((value) => {
    params.append('values', value);
  });

  if (lotDetail.selectedContainerId.value) {
    params.set('container_id', lotDetail.selectedContainerId.value);
  }

  if (lotDetail.activeSubTab.value) {
    params.set('lot_sub_tab', lotDetail.activeSubTab.value);
  }

  uniqueValues(lotDetail.selectedWorkcenterGroups.value).forEach((group) => {
    params.append('workcenter_groups', group);
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

  replaceRuntimeHistory(nextQuery ? `/query-tool?${nextQuery}` : '/query-tool');
}

async function applyStateFromUrl() {
  const state = readStateFromUrl();

  suppressUrlSync.value = true;

  activeTab.value = state.tab;

  lotResolve.setInputType(state.inputType);
  lotResolve.setInputText(state.inputText);

  lotDetail.activeSubTab.value = state.lotSubTab;
  lotDetail.selectedWorkcenterGroups.value = state.workcenterGroups;

  equipmentQuery.selectedEquipmentIds.value = state.equipmentIds;
  equipmentQuery.startDate.value = state.startDate || equipmentQuery.startDate.value;
  equipmentQuery.endDate.value = state.endDate || equipmentQuery.endDate.value;
  equipmentQuery.activeSubTab.value = state.equipmentSubTab;

  suppressUrlSync.value = false;

  if (state.selectedContainerId) {
    lotLineage.selectNode(state.selectedContainerId);
    await lotDetail.setSelectedContainerId(state.selectedContainerId);
  }
}

function handlePopState() {
  void applyStateFromUrl();
}

function activateTab(tab) {
  activeTab.value = normalizeTopTab(tab);
}

async function handleResolveLots() {
  const result = await lotResolve.resolveLots();
  if (!result?.ok) {
    return;
  }

  await lotLineage.primeResolvedLots(lotResolve.resolvedLots.value);

  const rootIds = lotLineage.rootContainerIds.value;
  if (rootIds.length === 0) {
    await lotDetail.setSelectedContainerId('');
    lotLineage.clearSelection();
    return;
  }

  const preferredSelection = lotDetail.selectedContainerId.value && rootIds.includes(lotDetail.selectedContainerId.value)
    ? lotDetail.selectedContainerId.value
    : rootIds[0];

  lotLineage.selectNode(preferredSelection);
  await lotDetail.setSelectedContainerId(preferredSelection);
}

async function handleSelectNodes(containerIds) {
  lotLineage.setSelectedNodes(containerIds);

  // Expand each selected node to include its entire subtree for detail loading
  const seen = new Set();
  containerIds.forEach((cid) => {
    lotLineage.getSubtreeCids(cid).forEach((id) => seen.add(id));
  });

  await lotDetail.setSelectedContainerIds([...seen]);
}

async function handleChangeLotSubTab(tab) {
  await lotDetail.setActiveSubTab(tab);
}

async function handleWorkcenterGroupChange(groups) {
  await lotDetail.setSelectedWorkcenterGroups(groups);
}

async function handleExportLotTab(tab) {
  await lotDetail.exportSubTab(tab);
}

async function handleChangeEquipmentSubTab(tab) {
  await equipmentQuery.setActiveSubTab(tab, { autoQuery: true });
}

async function handleQueryEquipmentActiveTab() {
  await equipmentQuery.queryActiveSubTab();
}

async function handleExportEquipmentSubTab(tab) {
  await equipmentQuery.exportSubTab(tab);
}

onMounted(async () => {
  window.addEventListener('popstate', handlePopState);
  await Promise.all([
    lotDetail.loadWorkcenterGroups(),
    equipmentQuery.bootstrap(),
  ]);

  if (initialState.selectedContainerId) {
    lotLineage.selectNode(initialState.selectedContainerId);
    await lotDetail.setSelectedContainerId(initialState.selectedContainerId);
  }

  syncUrlState();
});

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState);
});

watch(
  [
    activeTab,
    lotResolve.inputType,
    lotResolve.inputText,
    lotDetail.selectedContainerId,
    lotDetail.activeSubTab,
    lotDetail.selectedWorkcenterGroups,
    equipmentQuery.selectedEquipmentIds,
    equipmentQuery.startDate,
    equipmentQuery.endDate,
    equipmentQuery.activeSubTab,
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
</script>

<template>
  <div class="u-content-shell space-y-3 p-3 lg:p-5">
    <header class="rounded-shell bg-gradient-to-r from-brand-500 to-accent-500 px-5 py-4 text-white shadow-shell">
      <h1 class="text-xl font-semibold tracking-wide">批次追蹤工具</h1>
      <p class="mt-1 text-xs text-indigo-100">LOT 追蹤與設備查詢整合入口</p>
    </header>

    <section class="rounded-shell border border-stroke-panel bg-surface-card shadow-panel">
      <div class="border-b border-stroke-soft px-3 pt-3 lg:px-5">
        <nav class="flex flex-wrap gap-2" aria-label="query-tool tabs">
          <button
            v-for="tab in tabItems"
            :key="tab.key"
            type="button"
            class="rounded-card border px-4 py-2 text-sm font-medium transition"
            :class="tab.key === activeTab
              ? 'border-brand-500 bg-brand-50 text-brand-700 shadow-soft'
              : 'border-transparent bg-surface-muted text-slate-600 hover:border-stroke-soft hover:text-slate-800'"
            :aria-selected="tab.key === activeTab"
            :aria-current="tab.key === activeTab ? 'page' : undefined"
            @click="activateTab(tab.key)"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>

      <div class="space-y-3 px-3 py-4 lg:px-5">
        <div class="rounded-card border border-stroke-soft bg-surface-muted/60 px-4 py-3">
          <p class="text-xs font-medium tracking-wide text-slate-500">目前頁籤</p>
          <h2 class="mt-1 text-base font-semibold text-slate-800">{{ activeTabMeta.label }}</h2>
          <p class="mt-1 text-sm text-slate-600">{{ activeTabMeta.subtitle }}</p>
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
          :workcenter-groups="lotDetail.workcenterGroups.value"
          :selected-workcenter-groups="lotDetail.selectedWorkcenterGroups.value"
          @update:input-type="lotResolve.setInputType($event)"
          @update:input-text="lotResolve.setInputText($event)"
          @resolve="handleResolveLots"
          @select-nodes="handleSelectNodes"
          @change-sub-tab="handleChangeLotSubTab"
          @update-workcenter-groups="handleWorkcenterGroupChange"
          @export-lot-tab="handleExportLotTab"
        />

        <EquipmentView
          v-show="activeTab === TAB_EQUIPMENT"
          :equipment-options="equipmentQuery.equipmentOptionItems.value"
          :equipment-raw-options="equipmentQuery.equipmentOptions.value"
          :selected-equipment-ids="equipmentQuery.selectedEquipmentIds.value"
          :start-date="equipmentQuery.startDate.value"
          :end-date="equipmentQuery.endDate.value"
          :active-sub-tab="equipmentQuery.activeSubTab.value"
          :loading="equipmentQuery.loading"
          :errors="equipmentQuery.errors"
          :lots-rows="equipmentQuery.lotsRows.value"
          :jobs-rows="equipmentQuery.jobsRows.value"
          :rejects-rows="equipmentQuery.rejectsRows.value"
          :status-rows="equipmentQuery.statusRows.value"
          :exporting="equipmentQuery.exporting"
          :can-export-sub-tab="equipmentQuery.canExportSubTab"
          @update:selected-equipment-ids="equipmentQuery.setSelectedEquipmentIds($event)"
          @update:start-date="equipmentQuery.startDate.value = $event"
          @update:end-date="equipmentQuery.endDate.value = $event"
          @reset-date-range="equipmentQuery.resetDateRange(30)"
          @query-active-sub-tab="handleQueryEquipmentActiveTab"
          @change-sub-tab="handleChangeEquipmentSubTab"
          @export-sub-tab="handleExportEquipmentSubTab"
        />
      </div>
    </section>
  </div>
</template>
