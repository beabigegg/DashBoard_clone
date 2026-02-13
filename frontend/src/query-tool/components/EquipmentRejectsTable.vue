<script setup>
import ExportButton from './ExportButton.vue';
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
  error: {
    type: String,
    default: '',
  },
  exportDisabled: {
    type: Boolean,
    default: true,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['export']);

const columns = Object.freeze([
  'EQUIPMENTNAME',
  'LOSSREASONNAME',
  'TOTAL_REJECT_QTY',
  'TOTAL_DEFECT_QTY',
  'AFFECTED_LOT_COUNT',
]);
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div class="mb-2 flex items-center justify-between gap-2">
      <h4 class="text-sm font-semibold text-slate-800">報廢紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出報廢紀錄"
        @click="emit('export')"
      />
    </div>

    <p v-if="error" class="mb-2 rounded-card border border-state-danger/40 bg-rose-50 px-3 py-2 text-xs text-state-danger">
      {{ error }}
    </p>

    <div v-if="loading" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      載入中...
    </div>

    <div v-else-if="rows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      無報廢紀錄
    </div>

    <div v-else class="max-h-[460px] overflow-auto rounded-card border border-stroke-soft">
      <table class="min-w-full border-collapse text-xs">
        <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
          <tr>
            <th
              v-for="column in columns"
              :key="column"
              class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold"
            >
              {{ column }}
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in rows" :key="rowIndex" class="odd:bg-white even:bg-slate-50">
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
