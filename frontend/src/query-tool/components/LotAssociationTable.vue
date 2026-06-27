<script setup lang="ts">
import { computed } from 'vue';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next';

import { useSortableTable } from '../../shared-composables/useSortableTable';
import { formatCellValue } from '../utils/values';
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

  const ordered: string[] = [];
  const seen = new Set<string>();
  props.columnOrder.forEach((column) => {
    const col = String(column);
    if (visible.includes(col) && !seen.has(col)) {
      ordered.push(col);
      seen.add(col);
    }
  });
  visible.forEach((column) => {
    if (!seen.has(column)) {
      ordered.push(column);
    }
  });
  return ordered;
});

const rowsRef = computed(() => props.rows as Record<string, unknown>[]);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(rowsRef);

function sortIcon(key: string) {
  if (sortKey.value !== key) return ArrowUpDown;
  return sortDirection.value === 'asc' ? ArrowUp : ArrowDown;
}

function ariaSortFor(key: string): 'none' | 'ascending' | 'descending' {
  if (sortKey.value !== key) return 'none';
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

function resolveColumnLabel(column: string): string {
  return (props.columnLabels as Record<string, string>)?.[column] || column;
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
              <span class="qt-th-inner">
                {{ resolveColumnLabel(column) }}
                <component :is="sortIcon(column)" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === column }" :size="13" />
              </span>
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in sortedData" :key="(row.id || row.JOBID || rowIndex) as PropertyKey">
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
