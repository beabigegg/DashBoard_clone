<script setup lang="ts">
import QueryBar from './QueryBar.vue';
import LineageTreeChart from './LineageTreeChart.vue';
import LotDetail from './LotDetail.vue';

const props = defineProps({
  inputType: {
    type: String,
    default: 'lot_id',
  },
  inputText: {
    type: String,
    default: '',
  },
  inputTypeOptions: {
    type: Array,
    default: () => [],
  },
  inputLimit: {
    type: Number,
    default: 50,
  },
  resolving: {
    type: Boolean,
    default: false,
  },
  resolveErrorMessage: {
    type: String,
    default: '',
  },
  resolveSuccessMessage: {
    type: String,
    default: '',
  },
  treeRoots: {
    type: Array,
    default: () => [],
  },
  notFound: {
    type: Array,
    default: () => [],
  },
  lineageMap: {
    type: Object,
    required: true,
  },
  nameMap: {
    type: Object,
    default: () => new Map(),
  },
  nodeMetaMap: {
    type: Object,
    default: () => new Map(),
  },
  edgeTypeMap: {
    type: Object,
    default: () => new Map(),
  },
  graphEdges: {
    type: Array,
    default: () => [],
  },
  leafSerials: {
    type: Object,
    default: () => new Map(),
  },
  lineageLoading: {
    type: Boolean,
    default: false,
  },
  selectedContainerIds: {
    type: Array,
    default: () => [],
  },
  selectedContainerId: {
    type: String,
    default: '',
  },
  selectedContainerName: {
    type: String,
    default: '',
  },
  detailContainerIds: {
    type: Array,
    default: () => [],
  },
  detailLoading: {
    type: Object,
    required: true,
  },
  detailLoaded: {
    type: Object,
    required: true,
  },
  detailExporting: {
    type: Object,
    required: true,
  },
  detailErrors: {
    type: Object,
    required: true,
  },
  activeSubTab: {
    type: String,
    default: 'history',
  },
  historyRows: {
    type: Array,
    default: () => [],
  },
  associationRows: {
    type: Object,
    required: true,
  },
  detailPagination: {
    type: Object,
    required: true,
  },
  detailQualityMeta: {
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
  pageSizeOptions: {
    type: Array,
    default: () => [25, 50, 100, 200],
  },
});

const emit = defineEmits([
  'update:inputType',
  'update:inputText',
  'resolve',
  'select-nodes',
  'change-sub-tab',
  'update-workcenter-groups',
  'export-lot-tab',
  'change-page',
  'change-page-size',
]);
</script>

<template>
  <div class="space-y-3">
    <QueryBar
      :input-type="inputType"
      :input-text="inputText"
      :input-type-options="inputTypeOptions"
      :input-limit="inputLimit"
      :resolving="resolving"
      :error-message="resolveErrorMessage"
      @update:input-type="emit('update:inputType', $event)"
      @update:input-text="emit('update:inputText', $event)"
      @resolve="emit('resolve')"
    />

    <p v-if="resolveSuccessMessage" class="query-tool-success">
      {{ resolveSuccessMessage }}
    </p>

    <LineageTreeChart
      :tree-roots="treeRoots"
      :not-found="notFound"
      :lineage-map="lineageMap"
      :name-map="nameMap"
      :node-meta-map="nodeMetaMap"
      :edge-type-map="edgeTypeMap"
      :graph-edges="graphEdges"
      :leaf-serials="leafSerials"
      :selected-container-ids="selectedContainerIds"
      :loading="lineageLoading"
      @select-nodes="emit('select-nodes', $event)"
    />

    <LotDetail
      :selected-container-id="selectedContainerId"
      :selected-container-name="selectedContainerName"
      :selected-container-ids="detailContainerIds"
      :clicked-container-ids="selectedContainerIds"
      :name-map="nameMap"
      :active-sub-tab="activeSubTab"
      :loading="detailLoading"
      :loaded="detailLoaded"
      :exporting="detailExporting"
      :errors="detailErrors"
      :history-rows="historyRows"
      :association-rows="associationRows"
      :pagination="detailPagination"
      :quality-meta="detailQualityMeta"
      :workcenter-groups="workcenterGroups"
      :selected-workcenter-groups="selectedWorkcenterGroups"
      :page-size-options="pageSizeOptions"
      @change-sub-tab="emit('change-sub-tab', $event)"
      @update-workcenter-groups="emit('update-workcenter-groups', $event)"
      @export-tab="emit('export-lot-tab', $event)"
      @change-page="emit('change-page', $event)"
      @change-page-size="emit('change-page-size', $event)"
    />
  </div>
</template>
