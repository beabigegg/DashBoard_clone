<script setup lang="ts">
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { DetailRow, Pagination } from '../composables/useProductionHistory';

withDefaults(
  defineProps<{
    rows?: DetailRow[];
    pagination?: Pagination;
    loading?: boolean;
    canExport?: boolean;
  }>(),
  {
    rows: () => [],
    pagination: () => ({ page: 1, per_page: 25, total_rows: 0, total_pages: 0 }),
    loading: false,
    canExport: false,
  },
);

const emit = defineEmits<{
  (e: 'page-change', page: number): void;
  (e: 'export-csv'): void;
}>();

function formatTs(value: unknown): string {
  if (!value) return '';
  try {
    const d = new Date(value as string | number | Date);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString('zh-TW', { hour12: false });
  } catch {
    return String(value);
  }
}

/**
 * Returns partial_count from a DataTable slot row (typed as Record<string, unknown>).
 * Guards against missing / non-numeric values so older backends are safe.
 */
function getPartialCount(row: Record<string, unknown>): number {
  const v = row['partial_count'];
  return typeof v === 'number' ? v : 0;
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="section-header">
        <h2 class="section-title">明細資料</h2>
        <div class="detail-toolbar">
          <span class="ph-detail-count">
            共 {{ pagination.total_rows.toLocaleString() }} 筆
          </span>
          <button
            v-if="canExport"
            type="button"
            class="ui-btn ui-btn--secondary"
            :disabled="loading"
            @click="emit('export-csv')"
          >
            匯出 CSV
          </button>
        </div>
      </div>

    <DataTable
      :data="rows"
      :loading="loading"
      :pagination="pagination.total_pages > 1 ? { page: pagination.page, totalPages: pagination.total_pages, infoText: `${pagination.page} / ${pagination.total_pages}` } : null"
      @page-change="(p) => emit('page-change', p)"
    >
      <DataTableColumn columnKey="lot_id" label="LotID" :sortable="true" />
      <DataTableColumn columnKey="pj_type" label="Type" :sortable="true" />
      <DataTableColumn columnKey="package_name" label="Package" :sortable="true" />
      <DataTableColumn columnKey="bop" label="BOP" :sortable="true" />
      <DataTableColumn columnKey="pj_function" label="PJ Function" :sortable="true" />
      <DataTableColumn columnKey="work_order" label="WorkOrder" :sortable="true" />
      <DataTableColumn columnKey="wafer_lot" label="WaferLot" :sortable="true" />
      <DataTableColumn columnKey="workcenter" label="WorkCenter" :sortable="true" />
      <DataTableColumn columnKey="spec" label="Spec" :sortable="true" />
      <DataTableColumn columnKey="equipment_name" label="EquipName" :sortable="true" />
      <DataTableColumn columnKey="trackin_time" label="TrackIn" :sortable="true" />
      <DataTableColumn columnKey="trackout_time" label="TrackOut" :sortable="true" />
      <DataTableColumn columnKey="trackin_qty" label="InQTY" align="right" :sortable="true" />
      <DataTableColumn columnKey="trackout_qty" label="OutQTY" align="right" :sortable="true" />
      <template #cell="{ row, columnKey, value }">
        <template v-if="columnKey === 'trackin_time'">{{ formatTs(value) }}</template>
        <template v-else-if="columnKey === 'trackout_time'">{{ formatTs(value) }}</template>
        <template v-else-if="columnKey === 'lot_id'">
          {{ value ?? '' }}<span
            v-if="getPartialCount(row) > 1"
            class="ml-1 inline-block text-xs bg-gray-100 text-gray-600 rounded px-1"
            :aria-label="`此列合併了 ${getPartialCount(row)} 筆 partial trackout`"
          >×{{ getPartialCount(row) }} 合併</span>
        </template>
        <template v-else>{{ value ?? '' }}</template>
      </template>
    </DataTable>
    </div>
  </section>
</template>
