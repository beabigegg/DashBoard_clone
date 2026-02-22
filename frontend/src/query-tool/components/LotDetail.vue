<script setup>
import { computed } from 'vue';

import ExportButton from './ExportButton.vue';
import LotAssociationTable from './LotAssociationTable.vue';
import LotHistoryTable from './LotHistoryTable.vue';
import LotRejectTable from './LotRejectTable.vue';
import LotTimeline from './LotTimeline.vue';

const props = defineProps({
  selectedContainerId: {
    type: String,
    default: '',
  },
  selectedContainerName: {
    type: String,
    default: '',
  },
  selectedContainerIds: {
    type: Array,
    default: () => [],
  },
  clickedContainerIds: {
    type: Array,
    default: () => [],
  },
  nameMap: {
    type: Object,
    default: () => new Map(),
  },
  activeSubTab: {
    type: String,
    default: 'history',
  },
  loading: {
    type: Object,
    required: true,
  },
  loaded: {
    type: Object,
    required: true,
  },
  exporting: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
  },
  historyRows: {
    type: Array,
    default: () => [],
  },
  associationRows: {
    type: Object,
    required: true,
  },
  workcenterGroups: {
    type: Array,
    default: () => [],
  },
  selectedWorkcenterGroups: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['change-sub-tab', 'update-workcenter-groups', 'export-tab']);

const tabMeta = Object.freeze({
  history: { label: '歷程', emptyText: '無歷程資料' },
  materials: { label: '原物料', emptyText: '無原物料資料' },
  rejects: { label: '報廢', emptyText: '無報廢資料' },
  holds: { label: 'Hold', emptyText: '無 Hold 資料' },
  jobs: { label: 'Job', emptyText: '無 Job 資料' },
});

const subTabs = Object.keys(tabMeta);

const activeRows = computed(() => {
  if (props.activeSubTab === 'history') {
    return props.historyRows;
  }
  return props.associationRows[props.activeSubTab] || [];
});

const activeError = computed(() => {
  return props.errors[props.activeSubTab] || '';
});

const activeLoading = computed(() => {
  return Boolean(props.loading[props.activeSubTab]);
});

const activeLoaded = computed(() => {
  return Boolean(props.loaded[props.activeSubTab]);
});

const activeExporting = computed(() => {
  return Boolean(props.exporting[props.activeSubTab]);
});

const activeEmptyText = computed(() => {
  return tabMeta[props.activeSubTab]?.emptyText || '無資料';
});

const activeColumnLabels = computed(() => {
  if (props.activeSubTab === 'materials') {
    return {
      CONTAINERNAME: 'LOT ID',
    };
  }
  if (props.activeSubTab === 'holds') {
    return {
      CONTAINERNAME: 'LOT ID',
    };
  }
  return {};
});

const activeHiddenColumns = computed(() => {
  if (props.activeSubTab === 'materials') {
    return ['CONTAINERID', 'WORKCENTER_GROUP'];
  }
  if (props.activeSubTab === 'holds') {
    return ['CONTAINERID'];
  }
  return [];
});

const activeColumnOrder = computed(() => {
  if (props.activeSubTab === 'materials') {
    return [
      'CONTAINERNAME',
      'MATERIALPARTNAME',
      'MATERIALLOTNAME',
      'QTYCONSUMED',
      'WORKCENTERNAME',
      'SPECNAME',
      'EQUIPMENTNAME',
      'TXNDATE',
    ];
  }
  if (props.activeSubTab === 'holds') {
    return [
      'CONTAINERNAME',
      'WORKCENTERNAME',
      'HOLDTXNDATE',
      'RELEASETXNDATE',
      'HOLD_STATUS',
      'HOLD_HOURS',
      'HOLDREASONNAME',
      'HOLDCOMMENTS',
      'HOLDEMP',
      'HOLDEMPDEPTNAME',
      'RELEASEEMP',
      'RELEASECOMMENTS',
      'NCRID',
    ];
  }
  return [];
});

const canExport = computed(() => {
  return !activeLoading.value && activeRows.value.length > 0;
});

const detailDisplayNames = computed(() => {
  const clicked = props.clickedContainerIds;
  if (clicked.length === 0) {
    return props.selectedContainerName || props.selectedContainerId;
  }
  return clicked
    .map((cid) => props.nameMap?.get?.(cid) || cid)
    .join('、');
});

const subtreeCount = computed(() => {
  const total = props.selectedContainerIds.length;
  const clicked = props.clickedContainerIds.length || 1;
  return total > clicked ? total - clicked : 0;
});

const detailCountLabel = computed(() => {
  const extra = subtreeCount.value;
  if (extra > 0) {
    return `（含 ${extra} 個子批次）`;
  }
  return '';
});
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3 shadow-soft">
    <div v-if="!selectedContainerId" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-8 text-center text-xs text-slate-500">
      請從上方血緣樹選擇節點後查看明細。
    </div>

    <template v-else>
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-sm font-semibold text-slate-800">LOT 明細{{ detailCountLabel }}</h3>
          <p class="text-xs text-slate-500">{{ detailDisplayNames }}</p>
        </div>

        <ExportButton
          :disabled="!canExport"
          :loading="activeExporting"
          :label="`${tabMeta[activeSubTab]?.label || ''} 匯出 CSV`"
          @click="emit('export-tab', activeSubTab)"
        />
      </div>

      <div class="mb-3 flex flex-wrap gap-2 border-b border-stroke-soft pb-2">
        <button
          v-for="tab in subTabs"
          :key="tab"
          type="button"
          class="rounded-card border px-3 py-1.5 text-xs font-medium transition"
          :class="tab === activeSubTab
            ? 'border-brand-500 bg-brand-50 text-brand-700'
            : 'border-transparent bg-surface-muted/70 text-slate-600 hover:border-stroke-soft hover:text-slate-800'"
          @click="emit('change-sub-tab', tab)"
        >
          {{ tabMeta[tab].label }}
        </button>
      </div>

      <p v-if="activeError" class="mb-2 rounded-card border border-state-danger/40 bg-rose-50 px-3 py-2 text-xs text-state-danger">
        {{ activeError }}
      </p>

      <div v-if="activeSubTab === 'history'" class="space-y-3">
        <LotTimeline
          :history-rows="historyRows"
          :hold-rows="associationRows.holds || []"
          :material-rows="associationRows.materials || []"
        />

        <LotHistoryTable
          :rows="historyRows"
          :loading="loading.history"
          :workcenter-groups="workcenterGroups"
          :selected-workcenter-groups="selectedWorkcenterGroups"
          @update:workcenter-groups="emit('update-workcenter-groups', $event)"
        />
      </div>

      <LotAssociationTable
        v-else-if="activeSubTab !== 'rejects'"
        :rows="activeRows"
        :loading="activeLoading"
        :empty-text="activeLoaded ? activeEmptyText : '尚未查詢此分頁資料'"
        :column-labels="activeColumnLabels"
        :hidden-columns="activeHiddenColumns"
        :column-order="activeColumnOrder"
      />

      <LotRejectTable
        v-else
        :rows="activeRows"
        :loading="activeLoading"
        :empty-text="activeLoaded ? activeEmptyText : '尚未查詢此分頁資料'"
      />
    </template>
  </section>
</template>
