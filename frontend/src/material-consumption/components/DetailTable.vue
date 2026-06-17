<script setup lang="ts">
/**
 * DetailTable — material-consumption detail spool table
 * Change: material-part-consumption
 *
 * Uses shared-ui DataTable with serverSort=true (global, DuckDB-backed sort).
 * Supports pagination via GET /detail/page.
 * CSV export via POST /export.
 */
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

import type { DetailRow, DetailPagination } from '../composables/useConsumptionQuery';

// --- Props ---
const props = withDefaults(
  defineProps<{
    rows?: DetailRow[];
    pagination?: DetailPagination | null;
    loading?: boolean;
    isAsync?: boolean;
    detailQueryId?: string | null;
    activeSortKey?: string;
    activeSortDir?: string;
  }>(),
  {
    rows: () => [],
    pagination: null,
    loading: false,
    isAsync: false,
    detailQueryId: null,
    activeSortKey: '',
    activeSortDir: 'asc',
  }
);

const emit = defineEmits<{
  (e: 'page-change', page: number): void;
  (e: 'sort', payload: { key: string; direction: string }): void;
  (e: 'export-csv'): void;
}>();

// --- Constants: table columns ---
const TABLE_COLUMNS: { key: string; label: string; sortable: boolean }[] = [
  { key: 'material_part', label: '料號', sortable: true },
  { key: 'containername', label: 'LOT ID', sortable: true },
  { key: 'pj_workorder', label: '工單', sortable: true },
  { key: 'workcentername', label: '站點', sortable: true },
  { key: 'materiallotname', label: '物料批號', sortable: true },
  { key: 'qty_required', label: '應扣量', sortable: true },
  { key: 'qty_consumed', label: '實扣量', sortable: true },
  { key: 'pj_type', label: 'TYPE', sortable: true },
  { key: 'productlinename', label: 'Package', sortable: true },
  { key: 'txn_date', label: '交易日期', sortable: true },
];

function formatTxnDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const s = String(value).trim();

  // Backend normalises Oracle DATEs to YYYY-MM-DD before JSON serialisation.
  // Check the raw time component BEFORE any timezone conversion.
  const timeMatch = s.match(/[T ](\d{2}):(\d{2}):(\d{2})/);
  const rawTimeIsZero =
    !timeMatch || (timeMatch[1] === '00' && timeMatch[2] === '00' && timeMatch[3] === '00');

  const dateMatch = s.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!dateMatch) return s;
  const datePart = `${dateMatch[1]}/${dateMatch[2]}/${dateMatch[3]}`;

  if (rawTimeIsZero) return datePart;

  const d = new Date(s.replace(' ', 'T'));
  if (isNaN(d.getTime())) return `${datePart} ${timeMatch![1]}:${timeMatch![2]}:${timeMatch![3]}`;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
</script>

<template>
  <div class="detail-table-wrap" data-testid="detail-table-section">
    <!-- Pending/polling state -->
    <div
      v-if="loading && isAsync"
      class="detail-pending-state"
      data-testid="detail-pending-state"
      aria-live="polite"
    >
      <p class="detail-pending-text">非同步查詢中，請稍候...</p>
    </div>

    <!-- Inline loading (section-level) -->
    <div v-else-if="loading && !isAsync" class="detail-loading-wrap">
      <BlockLoadingState />
    </div>

    <!-- Results / empty -->
    <template v-else>
      <!-- Toolbar: CSV export -->
      <div v-if="detailQueryId" class="detail-toolbar">
        <button
          type="button"
          class="ui-btn ui-btn--secondary"
          :disabled="rows.length === 0"
          data-testid="export-csv-button"
          @click="emit('export-csv')"
        >
          匯出 CSV
        </button>
      </div>

      <!-- Table (serverSort=true — sorting is handled by DuckDB ORDER BY) -->
      <div class="data-table-container">
        <DataTable
          :data="(rows as Record<string, unknown>[])"
          :loading="false"
          :server-sort="true"
          :controlled-sort-key="activeSortKey"
          :controlled-sort-dir="activeSortDir"
          :pagination="
            pagination && pagination.total_pages > 1
              ? {
                  page: pagination.page,
                  totalPages: pagination.total_pages,
                  infoText: `第 ${pagination.page} / ${pagination.total_pages} 頁，共 ${pagination.total_rows.toLocaleString()} 筆`,
                }
              : null
          "
          @page-change="(page) => emit('page-change', page)"
          @sort="(payload) => emit('sort', payload)"
        >
          <DataTableColumn
            v-for="col in TABLE_COLUMNS"
            :key="col.key"
            :column-key="col.key"
            :label="col.label"
            :sortable="col.sortable"
          />
          <template #cell="{ columnKey, value }">
            <span v-if="columnKey === 'txn_date'">{{ formatTxnDate(value) }}</span>
            <span v-else>{{ value ?? '-' }}</span>
          </template>
        </DataTable>
      </div>
    </template>
  </div>
</template>
