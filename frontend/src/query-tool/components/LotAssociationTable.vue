<script setup>
import { computed } from 'vue';

import { useSortableTable } from '../../shared-composables/useSortableTable.js';
import { formatCellValue } from '../utils/values.js';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyText: {
    type: String,
    default: '無資料',
  },
  hiddenColumns: {
    type: Array,
    default: () => [],
  },
  columnLabels: {
    type: Object,
    default: () => ({}),
  },
  columnOrder: {
    type: Array,
    default: () => [],
  },
});

const columns = computed(() => {
  const baseColumns = Object.keys(props.rows[0] || {});
  if (baseColumns.length === 0) {
    return [];
  }

  const hidden = new Set((props.hiddenColumns || []).map((value) => String(value)));
  const visible = baseColumns.filter((column) => !hidden.has(column));

  if (!Array.isArray(props.columnOrder) || props.columnOrder.length === 0) {
    return visible;
  }

  const ordered = [];
  const seen = new Set();
  props.columnOrder.forEach((column) => {
    if (visible.includes(column) && !seen.has(column)) {
      ordered.push(column);
      seen.add(column);
    }
  });
  visible.forEach((column) => {
    if (!seen.has(column)) {
      ordered.push(column);
    }
  });
  return ordered;
});

const rowsRef = computed(() => props.rows);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(rowsRef);

function sortLabel(key) {
  if (sortKey.value !== key) return '⇕';
  return sortDirection.value === 'asc' ? '▲' : '▼';
}

function ariaSortFor(key) {
  if (sortKey.value !== key) return 'none';
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

function resolveColumnLabel(column) {
  return props.columnLabels?.[column] || column;
}
</script>

<template>
  <div>
    <BlockLoadingState v-if="loading" />

    <div v-else-if="rows.length === 0" class="placeholder">
      {{ emptyText }}
    </div>

    <div v-else class="query-tool-table-wrap">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column"
              class="sortable-th"
              :aria-sort="ariaSortFor(column)"
              @click="toggleSort(column)"
            >
              {{ resolveColumnLabel(column) }}
              <span class="sort-indicator">{{ sortLabel(column) }}</span>
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in sortedData" :key="row.id || row.JOBID || rowIndex">
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
