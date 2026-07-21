<script setup lang="ts">
/**
 * ResultsTable — equipment-lookup query results
 *
 * Uses shared-ui DataTable with serverSort=true (server-side sort_by/sort_dir
 * round-trip). Supports pagination via GET /list?page=N. CSV export re-fetches
 * the full filtered set (page_size=10000) and builds/downloads the CSV
 * client-side — there is deliberately no dedicated backend export endpoint.
 */
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

import type { EquipmentRow, EquipmentPagination } from '../composables/useEquipmentLookup';

// --- Props ---
const props = withDefaults(
  defineProps<{
    rows?: EquipmentRow[];
    pagination?: EquipmentPagination | null;
    loading?: boolean;
    isExporting?: boolean;
    activeSortKey?: string;
    activeSortDir?: string;
  }>(),
  {
    rows: () => [],
    pagination: null,
    loading: false,
    isExporting: false,
    activeSortKey: '',
    activeSortDir: 'asc',
  }
);

const emit = defineEmits<{
  (e: 'sort', payload: { key: string; direction: string }): void;
  (e: 'page-change', page: number): void;
  (e: 'export-csv'): void;
}>();

// --- Constants: table columns (order per interaction spec) ---
const TABLE_COLUMNS: { key: string; label: string; sortable: boolean }[] = [
  { key: 'RESOURCENAME', label: '編號', sortable: true },
  { key: 'LOCATIONNAME', label: '機台位置', sortable: true },
  { key: 'RESOURCEFAMILYNAME', label: '機型', sortable: true },
  { key: 'VENDORNAME', label: '供應商', sortable: false },
  { key: 'VENDORMODEL', label: '廠商型號', sortable: false },
  { key: 'WORKCENTERNAME', label: '工站', sortable: false },
];
</script>

<template>
  <div class="results-table-wrap" data-testid="results-table-section">
    <!-- Inline loading (section-level) -->
    <div v-if="loading" class="results-loading-wrap">
      <BlockLoadingState />
    </div>

    <!-- Results -->
    <template v-else>
      <!-- Toolbar: result count + CSV export -->
      <div class="results-toolbar">
        <span class="results-count" data-testid="results-count">
          共 {{ (pagination?.total ?? 0).toLocaleString() }} 筆
        </span>
        <button
          type="button"
          class="ui-btn ui-btn--secondary export-csv-btn"
          :disabled="isExporting || rows.length === 0"
          data-testid="export-csv-button"
          @click="emit('export-csv')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {{ isExporting ? '匯出中...' : '匯出 CSV' }}
        </button>
      </div>

      <!-- Table (serverSort=true — sort_by/sort_dir round-trips to the API) -->
      <div class="data-table-container">
        <DataTable
          :data="(rows as Record<string, unknown>[])"
          :loading="false"
          :server-sort="true"
          :controlled-sort-key="activeSortKey"
          :controlled-sort-dir="activeSortDir"
          empty-type="filter-empty"
          :pagination="
            pagination && pagination.total_pages > 1
              ? {
                  page: pagination.page,
                  totalPages: pagination.total_pages,
                  infoText: `第 ${pagination.page} / ${pagination.total_pages} 頁，共 ${pagination.total.toLocaleString()} 筆`,
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
          <template #cell="{ value }">
            <span>{{ value ?? '-' }}</span>
          </template>
        </DataTable>
      </div>
    </template>
  </div>
</template>
