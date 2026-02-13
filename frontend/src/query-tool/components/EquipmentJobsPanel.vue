<script setup>
import { ref } from 'vue';

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

const expandedIds = ref(new Set());

function rowKey(row, index) {
  return String(row?.JOBID || row?.id || index);
}

function toggleRow(row, index) {
  const key = rowKey(row, index);
  const next = new Set(expandedIds.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  expandedIds.value = next;
}

function isExpanded(row, index) {
  return expandedIds.value.has(rowKey(row, index));
}

const columns = Object.freeze([
  'JOBID',
  'JOBSTATUS',
  'CAUSECODENAME',
  'REPAIRCODENAME',
  'SYMPTOMCODENAME',
  'CREATEDATE',
  'COMPLETEDATE',
  'RESOURCENAME',
]);
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div class="mb-2 flex items-center justify-between gap-2">
      <h4 class="text-sm font-semibold text-slate-800">維修紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出維修紀錄"
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
      無維修紀錄
    </div>

    <div v-else class="max-h-[460px] overflow-auto rounded-card border border-stroke-soft">
      <table class="min-w-full border-collapse text-xs">
        <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
          <tr>
            <th class="border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">展開</th>
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
          <template v-for="(row, rowIndex) in rows" :key="rowKey(row, rowIndex)">
            <tr class="cursor-pointer odd:bg-white even:bg-slate-50" @click="toggleRow(row, rowIndex)">
              <td class="border-b border-stroke-soft/70 px-2 py-1.5 text-center text-slate-500">{{ isExpanded(row, rowIndex) ? '▾' : '▸' }}</td>
              <td
                v-for="column in columns"
                :key="`${rowIndex}-${column}`"
                class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700"
              >
                {{ formatCellValue(row[column]) }}
              </td>
            </tr>

            <tr v-if="isExpanded(row, rowIndex)" class="bg-slate-50/60">
              <td class="border-b border-stroke-soft/70 px-2 py-2" colspan="9">
                <div class="grid gap-2 text-[11px] text-slate-600 md:grid-cols-2">
                  <p><span class="font-semibold text-slate-700">RESOURCEID:</span> {{ formatCellValue(row.RESOURCEID) }}</p>
                  <p><span class="font-semibold text-slate-700">JOBMODELNAME:</span> {{ formatCellValue(row.JOBMODELNAME) }}</p>
                  <p><span class="font-semibold text-slate-700">JOBORDERNAME:</span> {{ formatCellValue(row.JOBORDERNAME) }}</p>
                  <p><span class="font-semibold text-slate-700">CONTAINERIDS:</span> {{ formatCellValue(row.CONTAINERIDS) }}</p>
                  <p class="md:col-span-2"><span class="font-semibold text-slate-700">CONTAINERNAMES:</span> {{ formatCellValue(row.CONTAINERNAMES) }}</p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>
