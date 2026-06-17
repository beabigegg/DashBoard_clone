<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';

import QueryBar from './QueryBar.vue';
import LineageTreeChart from './LineageTreeChart.vue';
import LotDetail from './LotDetail.vue';
import { normalizeText } from '../utils/values';

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

const showTreeModal = ref(false);
const openTreeBtn = ref<HTMLButtonElement | null>(null);
const nodeSearchQuery = ref('');

const allSelectableNodes = computed<Array<{ cid: string; name: string }>>(() => {
  const result: Array<{ cid: string; name: string }> = [];
  const lm = props.lineageMap as Map<string, { children?: string[] }>;
  if (!lm || typeof lm.forEach !== 'function') return result;
  lm.forEach((_entry, cid) => {
    const id = normalizeText(cid);
    if (!id) return;
    const name = normalizeText((props.nameMap as Map<string, string>)?.get?.(id) || id);
    result.push({ cid: id, name });
  });
  result.sort((a, b) => a.name.localeCompare(b.name, 'zh-Hant'));
  return result;
});

const filteredNodes = computed(() => {
  const q = normalizeText(nodeSearchQuery.value).toLowerCase();
  if (!q) return allSelectableNodes.value;
  return allSelectableNodes.value.filter(
    (n) => n.name.toLowerCase().includes(q) || n.cid.toLowerCase().includes(q),
  );
});

const selectedSet = computed(() => new Set((props.selectedContainerIds as string[]).map(normalizeText).filter(Boolean)));

function toggleNode(cid: string) {
  const current = new Set(selectedSet.value);
  if (current.has(cid)) {
    current.delete(cid);
  } else {
    current.add(cid);
  }
  emit('select-nodes', [...current]);
}

function removeNode(cid: string) {
  const current = new Set(selectedSet.value);
  current.delete(normalizeText(cid));
  emit('select-nodes', [...current]);
}

function clearAllNodes() {
  emit('select-nodes', []);
}

function selectAllFiltered() {
  const current = new Set(selectedSet.value);
  filteredNodes.value.forEach((n) => current.add(n.cid));
  emit('select-nodes', [...current]);
}

function deselectAllFiltered() {
  const toRemove = new Set(filteredNodes.value.map((n) => n.cid));
  const current = [...selectedSet.value].filter((cid) => !toRemove.has(cid));
  emit('select-nodes', current);
}

const allFilteredSelected = computed(() =>
  filteredNodes.value.length > 0 && filteredNodes.value.every((n) => selectedSet.value.has(n.cid)),
);

async function openModal() {
  showTreeModal.value = true;
  await nextTick();
}

async function closeModal() {
  showTreeModal.value = false;
  await nextTick();
  openTreeBtn.value?.focus();
}

function handleModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    void closeModal();
  }
}
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

    <!-- Lineage summary bar -->
    <div v-if="treeRoots.length > 0 || lineageLoading" class="lineage-summary-bar">
      <div class="lineage-summary-info">
        <span v-if="lineageLoading" class="lineage-summary-text">正在解析血緣資料…</span>
        <span v-else class="lineage-summary-text">
          已解析 <strong>{{ treeRoots.length }}</strong> 個根批次，共 <strong>{{ allSelectableNodes.length }}</strong> 個節點
        </span>
      </div>
      <button
        ref="openTreeBtn"
        type="button"
        class="ui-btn ui-btn--primary ui-btn--sm"
        :disabled="lineageLoading || treeRoots.length === 0"
        aria-haspopup="dialog"
        @click="openModal"
      >
        查看血緣樹
      </button>
    </div>

    <!-- Node filter -->
    <div v-if="allSelectableNodes.length > 0" class="lineage-node-filter">
      <div class="lineage-node-filter-header">
        <span class="lineage-node-filter-title">節點篩選明細</span>
        <span class="lineage-node-filter-hint">勾選節點後，下方明細僅顯示所選批次</span>
        <div class="lineage-node-filter-actions">
          <button
            v-if="filteredNodes.length > 0"
            type="button"
            class="ui-btn ui-btn--ghost ui-btn--sm"
            @click="allFilteredSelected ? deselectAllFiltered() : selectAllFiltered()"
          >
            {{ allFilteredSelected ? '取消全選' : '全選' }}
          </button>
          <button
            v-if="selectedContainerIds.length > 0"
            type="button"
            class="ui-btn ui-btn--ghost ui-btn--sm lineage-clear-btn"
            @click="clearAllNodes"
          >
            清除全部
          </button>
        </div>
      </div>

      <!-- Selected chips -->
      <div v-if="selectedContainerIds.length > 0" class="lineage-node-chips">
        <span
          v-for="cid in (selectedContainerIds as string[]).slice(0, 12)"
          :key="cid"
          class="lineage-node-chip"
        >
          {{ (nameMap as Map<string, string>)?.get?.(cid) || cid }}
          <button
            type="button"
            class="lineage-chip-remove"
            :title="`取消篩選 ${cid}`"
            :aria-label="`取消篩選 ${cid}`"
            @click="removeNode(cid)"
          >×</button>
        </span>
        <span v-if="selectedContainerIds.length > 12" class="lineage-node-chip-more">
          +{{ selectedContainerIds.length - 12 }} 更多
        </span>
      </div>

      <!-- Search input -->
      <input
        v-model="nodeSearchQuery"
        type="search"
        class="lineage-node-search"
        placeholder="搜尋節點名稱或 CID…"
        aria-label="搜尋節點"
      />

      <!-- Checkbox list -->
      <div class="lineage-node-list" role="listbox" aria-multiselectable="true" aria-label="節點清單">
        <label
          v-for="node in filteredNodes"
          :key="node.cid"
          class="lineage-node-item"
          :class="{ selected: selectedSet.has(node.cid) }"
        >
          <input
            type="checkbox"
            class="lineage-node-checkbox"
            :checked="selectedSet.has(node.cid)"
            :value="node.cid"
            @change="toggleNode(node.cid)"
          />
          <span class="lineage-node-name">{{ node.name }}</span>
          <span v-if="node.name !== node.cid" class="lineage-node-cid">{{ node.cid }}</span>
        </label>
        <div v-if="filteredNodes.length === 0" class="lineage-node-empty">
          無符合條件的節點
        </div>
      </div>
    </div>

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

    <!-- Lineage tree modal -->
    <Teleport to="body">
      <div class="theme-query-tool">
      <div
        v-if="showTreeModal"
        class="lineage-modal-backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="批次血緣樹"
        @keydown="handleModalKeydown"
        @click.self="closeModal"
      >
        <div class="lineage-modal-container">
          <div class="lineage-modal-header">
            <h2 class="lineage-modal-title">批次血緣樹</h2>
            <button
              type="button"
              class="lineage-modal-close"
              aria-label="關閉血緣樹視窗"
              title="關閉（Esc）"
              @click="closeModal"
            >✕</button>
          </div>
          <div class="lineage-modal-body">
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
          </div>
        </div>
      </div>
      </div>
    </Teleport>
  </div>
</template>
