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
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div v-if="loading" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      讀取中...
    </div>

    <div v-else-if="rows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      {{ emptyText }}
    </div>

    <div v-else class="max-h-[420px] overflow-auto rounded-card border border-stroke-soft">
      <table class="min-w-full border-collapse text-xs">
        <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
          <tr>
            <th
              v-for="column in columns"
              :key="column"
              class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold"
            >
              {{ resolveColumnLabel(column) }}
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in rows" :key="row.id || row.JOBID || rowIndex" class="odd:bg-white even:bg-slate-50">
            <td
              v-for="column in columns"
              :key="`${rowIndex}-${column}`"
              class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700"
            >
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
