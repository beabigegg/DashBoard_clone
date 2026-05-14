<script setup lang="ts">
import { computed, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api';
import { useSortableTable } from '../../shared-composables/useSortableTable';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import StatusBadge from '../../shared-ui/components/StatusBadge.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import { formatCellValue, formatDateTime, parseDateTime } from '../utils/values';

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
const txnRows = ref<Record<string, unknown>[]>([]);
const loadingTxn = ref(false);
const txnError = ref('');

function buildOrderedColumns(rows: unknown[], preferred: readonly string[]): string[] {
  const keys = new Set(Object.keys((rows?.[0] as Record<string, unknown>) || {}));
  return preferred.filter((column) => keys.has(column));
}

const sortedRows = computed(() => {
  return [...(props.rows || [])].sort((rawA, rawB) => {
    const a = rawA as Record<string, unknown>;
    const b = rawB as Record<string, unknown>;
    const aDate = parseDateTime(a?.CREATEDATE);
    const bDate = parseDateTime(b?.CREATEDATE);
    const aTime = aDate ? aDate.getTime() : 0;
    const bTime = bDate ? bDate.getTime() : 0;
    return bTime - aTime;
  });
});

const sortedRowsTyped = sortedRows as unknown as import('vue').ComputedRef<Record<string, unknown>[]>;
const { sortKey, sortDirection, sortedData: displayRows, toggleSort } = useSortableTable(sortedRowsTyped);

function sortLabel(key: string): string {
  if (sortKey.value !== key) return '⇕';
  return sortDirection.value === 'asc' ? '▲' : '▼';
}

function ariaSortFor(key: string): 'none' | 'ascending' | 'descending' {
  if (sortKey.value !== key) return 'none';
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

const jobColumns = computed(() => {
  return buildOrderedColumns(props.rows, JOB_COLUMN_PRIORITY);
});

const txnColumns = computed(() => {
  return buildOrderedColumns(txnRows.value, TXN_COLUMN_PRIORITY);
});

function rowKey(row: Record<string, unknown>, index: number): string {
  return String(row?.JOBID || `${row?.RESOURCEID || ''}-${index}`);
}

function buildStatusTone(status: unknown): 'success' | 'warning' | 'neutral' | 'danger' | 'info' {
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

function renderJobCellValue(row: Record<string, unknown>, column: string): string {
  if (column === 'CREATEDATE' || column === 'COMPLETEDATE') {
    return formatDateTime(row?.[column]);
  }
  return formatCellValue(row?.[column]);
}

function renderTxnCellValue(row: Record<string, unknown>, column: string): string {
  const normalizedColumn = String(column || '').toUpperCase();
  if (normalizedColumn.includes('DATE') || normalizedColumn.includes('TIME')) {
    return formatDateTime(row?.[column]);
  }
  if (column === 'USER_NAME') {
    return formatCellValue(row?.USER_NAME || row?.EMP_NAME);
  }
  return formatCellValue(row?.[column]);
}

async function loadTxn(jobId: unknown): Promise<void> {
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
    const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
    txnRows.value = Array.isArray(inner?.data) ? inner.data as Record<string, unknown>[] : [];
  } catch (error) {
    txnError.value = (error as Error)?.message || '載入交易歷程失敗';
    txnRows.value = [];
  } finally {
    loadingTxn.value = false;
  }
}
</script>

<template>
  <section class="space-y-3">
    <div>
      <BlockLoadingState v-if="loading" />

      <div v-else-if="displayRows.length === 0" class="placeholder">
        {{ emptyText }}
      </div>

      <div v-else class="query-tool-table-wrap">
        <table class="query-tool-table">
          <thead>
            <tr>
              <th>操作</th>
              <th
                v-for="column in jobColumns"
                :key="column"
                class="sortable-th"
                :aria-sort="ariaSortFor(column)"
                @click="toggleSort(column)"
              >
                {{ column === 'CONTAINERNAMES' ? 'LOT ID' : column }}
                <span class="sort-indicator">{{ sortLabel(column) }}</span>
              </th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="(row, rowIndex) in displayRows" :key="rowKey(row, rowIndex)">
              <td>
                <button
                  type="button"
                  class="ui-btn ui-btn--ghost ui-btn--sm"
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

      <ErrorBanner :message="txnError" />

      <BlockLoadingState v-if="loadingTxn" text="載入交易歷程中..." />

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
              :key="(row?.JOBTXNHISTORYID || `${selectedJobId}-${rowIndex}`) as PropertyKey"
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
