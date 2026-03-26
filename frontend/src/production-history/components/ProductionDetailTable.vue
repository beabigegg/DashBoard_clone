<script setup>
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

const props = defineProps({
  rows: { type: Array, default: () => [] },
  pagination: {
    type: Object,
    default: () => ({ page: 1, per_page: 25, total_rows: 0, total_pages: 0 }),
  },
  loading: { type: Boolean, default: false },
  exportUrl: { type: String, default: null },
});

const emit = defineEmits(['page-change']);

function formatTs(value) {
  if (!value) return '';
  try {
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return d.toLocaleString('zh-TW', { hour12: false });
  } catch {
    return String(value);
  }
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
          <a
            v-if="exportUrl"
            :href="exportUrl"
            class="ui-btn ui-btn--sm"
            download
          >
            匯出 CSV
          </a>
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
        <template v-else>{{ value ?? '' }}</template>
      </template>
    </DataTable>
    </div>
  </section>
</template>
