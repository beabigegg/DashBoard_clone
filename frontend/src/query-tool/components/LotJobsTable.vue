<script setup>
import { computed, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api.js';
import StatusBadge from '../../shared-ui/components/StatusBadge.vue';
import { formatCellValue, formatDateTime, parseDateTime } from '../utils/values.js';

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
    default: '無維修資料',
  },
});

ensureMesApiAvailable();

const JOB_COLUMN_PRIORITY = Object.freeze([
  'JOBID',
  'RESOURCEID',
  'RESOURCENAME',
  'JOBSTATUS',
  'JOBMODELNAME',
  'JOBORDERNAME',
  'CREATEDATE',
  'COMPLETEDATE',
  'CANCELDATE',
  'FIRSTCLOCKONDATE',
  'LASTCLOCKOFFDATE',
  'CAUSECODENAME',
  'REPAIRCODENAME',
  'SYMPTOMCODENAME',
  'PJ_CAUSECODE2NAME',
  'PJ_REPAIRCODE2NAME',
  'PJ_SYMPTOMCODE2NAME',
  'CREATE_EMPNAME',
  'COMPLETE_EMPNAME',
  'CONTAINERIDS',
  'CONTAINERNAMES',
]);

const TXN_COLUMN_PRIORITY = Object.freeze([
  'JOBTXNHISTORYID',
  'JOBID',
  'TXNDATE',
  'FROMJOBSTATUS',
  'JOBSTATUS',
  'STAGENAME',
  'TOSTAGENAME',
  'CAUSECODENAME',
  'REPAIRCODENAME',
  'SYMPTOMCODENAME',
  'USER_EMPNO',
  'USER_NAME',
  'EMP_EMPNO',
  'EMP_NAME',
  'COMMENTS',
  'CDONAME',
  'JOBMODELNAME',
  'JOBORDERNAME',
]);

const selectedJobId = ref('');
const txnRows = ref([]);
const loadingTxn = ref(false);
const txnError = ref('');

function buildOrderedColumns(rows, preferred) {
  const keys = Object.keys(rows?.[0] || {});
  if (keys.length === 0) {
    return [...preferred];
  }

  const keySet = new Set(keys);
  const ordered = preferred.filter((column) => keySet.has(column));
  const orderedSet = new Set(ordered);
  keys.forEach((column) => {
    if (!orderedSet.has(column)) {
      ordered.push(column);
    }
  });
  return ordered;
}

const sortedRows = computed(() => {
  return [...(props.rows || [])].sort((a, b) => {
    const aDate = parseDateTime(a?.CREATEDATE);
    const bDate = parseDateTime(b?.CREATEDATE);
    const aTime = aDate ? aDate.getTime() : 0;
    const bTime = bDate ? bDate.getTime() : 0;
    return bTime - aTime;
  });
});

const jobColumns = computed(() => {
  return buildOrderedColumns(props.rows, JOB_COLUMN_PRIORITY);
});

const txnColumns = computed(() => {
  return buildOrderedColumns(txnRows.value, TXN_COLUMN_PRIORITY);
});

function rowKey(row, index) {
  return String(row?.JOBID || `${row?.RESOURCEID || ''}-${index}`);
}

function buildStatusTone(status) {
  const text = String(status || '').trim().toLowerCase();
  if (!text) {
    return 'neutral';
  }
  if (['complete', 'completed', 'done', 'closed', 'finish'].some((keyword) => text.includes(keyword))) {
    return 'success';
  }
  if (['open', 'pending', 'queue', 'wait', 'hold', 'in progress'].some((keyword) => text.includes(keyword))) {
    return 'warning';
  }
  if (['cancel', 'abort', 'fail', 'error'].some((keyword) => text.includes(keyword))) {
    return 'danger';
  }
  return 'neutral';
}

function renderJobCellValue(row, column) {
  if (column === 'CREATEDATE' || column === 'COMPLETEDATE') {
    return formatDateTime(row?.[column]);
  }
  return formatCellValue(row?.[column]);
}

function renderTxnCellValue(row, column) {
  const normalizedColumn = String(column || '').toUpperCase();
  if (normalizedColumn.includes('DATE') || normalizedColumn.includes('TIME')) {
    return formatDateTime(row?.[column]);
  }
  if (column === 'USER_NAME') {
    return formatCellValue(row?.USER_NAME || row?.EMP_NAME);
  }
  return formatCellValue(row?.[column]);
}

async function loadTxn(jobId) {
  const id = String(jobId || '').trim();
  if (!id) {
    return;
  }

  selectedJobId.value = id;
  loadingTxn.value = true;
  txnError.value = '';
  txnRows.value = [];

  try {
    const payload = await apiGet(`/api/job-query/txn/${encodeURIComponent(id)}`, {
      timeout: 60000,
      silent: true,
    });
    txnRows.value = Array.isArray(payload?.data) ? payload.data : [];
  } catch (error) {
    txnError.value = error?.message || '載入交易歷程失敗';
    txnRows.value = [];
  } finally {
    loadingTxn.value = false;
  }
}
</script>

<template>
  <section class="space-y-3">
    <div class="rounded-card border border-stroke-soft bg-white p-3">
      <div v-if="loading" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
        讀取中...
      </div>

      <div v-else-if="sortedRows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
        {{ emptyText }}
      </div>

      <div v-else class="max-h-[420px] overflow-auto rounded-card border border-stroke-soft">
        <table class="min-w-full border-collapse text-xs">
          <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
            <tr>
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">操作</th>
              <th
                v-for="column in jobColumns"
                :key="column"
                class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold"
              >
                {{ column }}
              </th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="(row, rowIndex) in sortedRows" :key="rowKey(row, rowIndex)" class="odd:bg-white even:bg-slate-50">
              <td class="border-b border-stroke-soft/70 px-2 py-1.5">
                <button
                  type="button"
                  class="rounded-card border border-stroke-soft bg-white px-2 py-1 text-[11px] font-medium text-slate-600 transition hover:bg-surface-muted/70 hover:text-slate-800"
                  @click="loadTxn(row?.JOBID)"
                >
                  查看交易歷程
                </button>
              </td>
              <td
                v-for="column in jobColumns"
                :key="`${rowKey(row, rowIndex)}-${column}`"
                class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700"
              >
                <StatusBadge
                  v-if="column === 'JOBSTATUS'"
                  :tone="buildStatusTone(row?.[column])"
                  :text="formatCellValue(row?.[column])"
                />
                <span v-else>{{ renderJobCellValue(row, column) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="selectedJobId" class="rounded-card border border-stroke-soft bg-white p-3">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 class="text-sm font-semibold text-slate-800">交易歷程：{{ selectedJobId }}</h4>
        <span class="text-xs text-slate-500">{{ txnRows.length }} 筆</span>
      </div>

      <p v-if="txnError" class="mb-2 rounded-card border border-state-danger/40 bg-rose-50 px-3 py-2 text-xs text-state-danger">
        {{ txnError }}
      </p>

      <div v-if="loadingTxn" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
        載入交易歷程中...
      </div>

      <div v-else-if="txnRows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
        無交易歷程資料
      </div>

      <div v-else class="max-h-[420px] overflow-auto rounded-card border border-stroke-soft">
        <table class="min-w-full border-collapse text-xs">
          <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
            <tr>
              <th
                v-for="column in txnColumns"
                :key="column"
                class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold"
              >
                {{ column }}
              </th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="(row, rowIndex) in txnRows"
              :key="row?.JOBTXNHISTORYID || `${selectedJobId}-${rowIndex}`"
              class="odd:bg-white even:bg-slate-50"
            >
              <td
                v-for="column in txnColumns"
                :key="`${row?.JOBTXNHISTORYID || rowIndex}-${column}`"
                class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700"
              >
                <StatusBadge
                  v-if="column === 'JOBSTATUS' || column === 'FROMJOBSTATUS'"
                  :tone="buildStatusTone(row?.[column])"
                  :text="formatCellValue(row?.[column])"
                />
                <span v-else>{{ renderTxnCellValue(row, column) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
