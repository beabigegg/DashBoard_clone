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
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">維修紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出維修紀錄"
        @click="emit('export')"
      />
    </div>

    <p v-if="error" class="error-banner">
      {{ error }}
    </p>

    <div v-if="loading" class="placeholder">
      載入中...
    </div>

    <div v-else-if="rows.length === 0" class="placeholder">
      無維修紀錄
    </div>

    <div v-else class="query-tool-table-wrap tall">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th>展開</th>
            <th v-for="column in columns" :key="column">
              {{ column }}
            </th>
          </tr>
        </thead>

        <tbody>
          <template v-for="(row, rowIndex) in rows" :key="rowKey(row, rowIndex)">
            <tr class="row-clickable" @click="toggleRow(row, rowIndex)">
              <td class="td-center">{{ isExpanded(row, rowIndex) ? '▾' : '▸' }}</td>
              <td v-for="column in columns" :key="`${rowIndex}-${column}`">
                {{ formatCellValue(row[column]) }}
              </td>
            </tr>

            <tr v-if="isExpanded(row, rowIndex)">
              <td colspan="9" class="td-detail-body">
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
  </div>
</template>

<style scoped>
.row-clickable {
  cursor: pointer;
}
.td-center {
  text-align: center;
}
.td-detail-body {
  padding: theme('spacing.token.p8') theme('spacing.token.p10');
}
</style>
