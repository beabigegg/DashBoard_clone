<script setup lang="ts">
/**
 * DetailTable — material-consumption detail spool table
 * Change: material-part-consumption
 *
 * Uses shared-ui DataTable + DataTableColumn.
 * Supports pagination via GET /detail/page.
 * CSV export via POST /export.
 */
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import EmptyState from '../../shared-ui/components/EmptyState.vue';

import type { DetailRow, DetailPagination, QueryParams } from '../composables/useConsumptionQuery';

// --- Props ---
const props = withDefaults(
  defineProps<{
    rows?: DetailRow[];
    pagination?: DetailPagination | null;
    loading?: boolean;
    isAsync?: boolean;
    querySubmitted?: boolean;
    queryParams?: QueryParams | null;
    detailQueryId?: string | null;
  }>(),
  {
    rows: () => [],
    pagination: null,
    loading: false,
    isAsync: false,
    querySubmitted: false,
    queryParams: null,
    detailQueryId: null,
  }
);

const emit = defineEmits<{
  (e: 'submit-detail'): void;
  (e: 'page-change', page: number): void;
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
  { key: 'txn_date', label: '交易日期', sortable: true },
];

function formatTxnDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const s = String(value).trim();

  // Check the raw time component BEFORE any timezone conversion.
  // Oracle DATEs with no real time are stored as midnight (00:00:00) UTC;
  // parsing them via Date() in UTC+8 would show 08:00:00, which is misleading.
  const timeMatch = s.match(/[T ](\d{2}):(\d{2}):(\d{2})/);
  const rawTimeIsZero =
    !timeMatch || (timeMatch[1] === '00' && timeMatch[2] === '00' && timeMatch[3] === '00');

  // Extract date components directly from the raw string (avoids TZ shift on date-only values)
  const dateMatch = s.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!dateMatch) return s;
  const datePart = `${dateMatch[1]}/${dateMatch[2]}/${dateMatch[3]}`;

  if (rawTimeIsZero) return datePart;

  // Has a meaningful time — convert to local timezone via Date()
  const d = new Date(s.replace(' ', 'T'));
  if (isNaN(d.getTime())) return `${datePart} ${timeMatch![1]}:${timeMatch![2]}:${timeMatch![3]}`;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function handlePageChange(page: number) {
  emit('page-change', page);
}

function handleExport() {
  emit('export-csv');
}
</script>

<template>
  <div class="detail-table-wrap" data-testid="detail-table-section">
    <!-- Submit detail button -->
    <div v-if="!querySubmitted && !loading" class="detail-actions">
      <button
        type="button"
        class="ui-btn ui-btn--secondary"
        data-testid="detail-submit-button"
        @click="emit('submit-detail')"
      >
        載入明細資料
      </button>
    </div>

    <!-- Pending/polling state (BLOCKING-4 fix: single loading representation only) -->
    <!-- Option A: descriptive pending text only; no concurrent LoadingOverlay -->
    <div
      v-if="loading && isAsync"
      class="detail-pending-state"
      data-testid="detail-pending-state"
      aria-live="polite"
    >
      <p class="detail-pending-text">非同步查詢中，請稍候...</p>
    </div>

    <!-- Inline loading (section-level, not page-level) -->
    <div v-else-if="loading && !isAsync" class="detail-loading-wrap">
      <BlockLoadingState />
    </div>

    <!-- Results -->
    <template v-else-if="querySubmitted">
      <!-- Toolbar: re-submit + export -->
      <div v-if="rows.length > 0 || detailQueryId" class="detail-toolbar">
        <button
          type="button"
          class="ui-btn ui-btn--secondary"
          data-testid="detail-submit-button"
          @click="emit('submit-detail')"
        >
          重新查詢明細
        </button>
        <button
          v-if="detailQueryId"
          type="button"
          class="ui-btn ui-btn--secondary"
          :disabled="rows.length === 0"
          data-testid="export-csv-button"
          @click="handleExport"
        >
          匯出 CSV
        </button>
      </div>

      <!-- Table -->
      <div class="data-table-container">
        <DataTable
          :data="(rows as Record<string, unknown>[])"
          :loading="loading"
          :pagination="
            pagination && pagination.total_pages > 1
              ? {
                  page: pagination.page,
                  totalPages: pagination.total_pages,
                  infoText: `第 ${pagination.page} / ${pagination.total_pages} 頁，共 ${pagination.total_rows.toLocaleString()} 筆`,
                }
              : null
          "
          @page-change="handlePageChange"
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
            <span v-else>{{ value }}</span>
          </template>
        </DataTable>

        <!-- Empty state -->
        <EmptyState v-if="!loading && rows.length === 0" />
      </div>
    </template>
  </div>
</template>
