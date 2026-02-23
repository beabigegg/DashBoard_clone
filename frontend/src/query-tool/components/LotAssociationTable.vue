<script setup>
import { computed } from 'vue';

import { formatCellValue } from '../utils/values.js';

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

function resolveColumnLabel(column) {
  return props.columnLabels?.[column] || column;
}
</script>

<template>
  <div>
    <div v-if="loading" class="placeholder">
      讀取中...
    </div>

    <div v-else-if="rows.length === 0" class="placeholder">
      {{ emptyText }}
    </div>

    <div v-else class="query-tool-table-wrap">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">
              {{ resolveColumnLabel(column) }}
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in rows" :key="row.id || row.JOBID || rowIndex">
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
