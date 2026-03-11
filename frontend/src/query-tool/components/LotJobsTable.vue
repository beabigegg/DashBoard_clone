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
  'CONTAINERNAMES',
]);

const TXN_COLUMN_PRIORITY = Object.freeze([
  'TXNDATE',
  'FROMJOBSTATUS',
  'JOBSTATUS',
  'STAGENAME',
  'CAUSECODENAME',
  'REPAIRCODENAME',
  'USER_NAME',
  'COMMENTS',
]);

const selectedJobId = ref('');
const txnRows = ref([]);
const loadingTxn = ref(false);
const txnError = ref('');

function buildOrderedColumns(rows, preferred) {
  const keys = new Set(Object.keys(rows?.[0] || {}));
  return preferred.filter((column) => keys.has(column));
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
      timeout: 360000,
      silent: true,
    });
    const inner = payload?.data || {};
    txnRows.value = Array.isArray(inner?.data) ? inner.data : [];
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
    <div>
      <div v-if="loading" class="placeholder">
        讀取中...
      </div>

      <div v-else-if="sortedRows.length === 0" class="placeholder">
        {{ emptyText }}
      </div>

      <div v-else class="query-tool-table-wrap">
        <table class="query-tool-table">
          <thead>
            <tr>
              <th>操作</th>
              <th v-for="column in jobColumns" :key="column">
                {{ column === 'CONTAINERNAMES' ? 'LOT ID' : column }}
              </th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="(row, rowIndex) in sortedRows" :key="rowKey(row, rowIndex)">
              <td>
                <button
                  type="button"
                  class="btn btn-ghost btn-mini"
                  @click="loadTxn(row?.JOBID)"
                >
                  查看交易歷程
                </button>
              </td>
              <td v-for="column in jobColumns" :key="`${rowKey(row, rowIndex)}-${column}`">
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

    <div v-if="selectedJobId">
      <div class="query-tool-section-header">
        <h4 class="card-title ui-card-title">交易歷程：{{ selectedJobId }}</h4>
        <span class="query-tool-muted">{{ txnRows.length }} 筆</span>
      </div>

      <p v-if="txnError" class="error-banner">
        {{ txnError }}
      </p>

      <div v-if="loadingTxn" class="placeholder">
        載入交易歷程中...
      </div>

      <div v-else-if="txnRows.length === 0" class="placeholder">
        無交易歷程資料
      </div>

      <div v-else class="query-tool-table-wrap">
        <table class="query-tool-table">
          <thead>
            <tr>
              <th v-for="column in txnColumns" :key="column">
                {{ column }}
              </th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="(row, rowIndex) in txnRows"
              :key="row?.JOBTXNHISTORYID || `${selectedJobId}-${rowIndex}`"
            >
              <td v-for="column in txnColumns" :key="`${row?.JOBTXNHISTORYID || rowIndex}-${column}`">
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

<style scoped>
.btn-mini {
  padding: theme('spacing.token.p2') theme('spacing.token.p8');
  font-size: 11px;
}
</style>
