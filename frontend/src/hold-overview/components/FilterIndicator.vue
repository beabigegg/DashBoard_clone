<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps({
  matrixFilter: {
    type: Object,
    default: null,
  },
  treemapFilter: {
    type: Object,
    default: null,
  },
  showClearAll: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(['clear-matrix', 'clear-treemap', 'clear-all']);

const matrixLabel = computed(() => {
  const filter = props.matrixFilter;
  if (!filter) {
    return '';
  }
  const parts = [];
  if (filter.workcenter) {
    parts.push(`Workcenter=${filter.workcenter}`);
  }
  if (filter.package) {
    parts.push(`Package=${filter.package}`);
  }
  return parts.join(', ');
});

const treemapLabel = computed(() => {
  const filter = props.treemapFilter;
  if (!filter) {
    return '';
  }
  const parts = [];
  if (filter.workcenter) {
    parts.push(`Workcenter=${filter.workcenter}`);
  }
  if (filter.reason) {
    parts.push(`Reason=${filter.reason}`);
  }
  return parts.join(', ');
});

const hasMatrixFilter = computed(() => Boolean(matrixLabel.value));
const hasTreemapFilter = computed(() => Boolean(treemapLabel.value));
const hasAnyFilter = computed(() => hasMatrixFilter.value || hasTreemapFilter.value);
</script>

<template>
  <section v-if="hasAnyFilter" class="cascade-filter-indicator">
    <div v-if="hasMatrixFilter" class="filter-chip matrix">
      <span>Matrix 篩選：{{ matrixLabel }}（柏拉圖 + Lot 清單已連動）</span>
      <button type="button" class="chip-clear" @click="emit('clear-matrix')">×</button>
    </div>

    <div v-if="hasTreemapFilter" class="filter-chip treemap">
      <span>TreeMap 篩選：{{ treemapLabel }}</span>
      <button type="button" class="chip-clear" @click="emit('clear-treemap')">×</button>
    </div>

    <button
      v-if="showClearAll"
      type="button"
      class="ui-btn ui-btn--ghost clear-all-btn"
      @click="emit('clear-all')"
    >
      清除所有篩選
    </button>
  </section>
</template>
