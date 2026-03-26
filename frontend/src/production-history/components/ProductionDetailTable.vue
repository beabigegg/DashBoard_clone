<script setup>
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

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
  <SectionCard>
    <template #header>
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%;">
        <span class="ui-card-title">明細資料</span>
        <div style="display:flex;align-items:center;gap:12px;">
          <span class="ph-detail-count">
            共 {{ pagination.total_rows.toLocaleString() }} 筆
          </span>
          <a
            v-if="exportUrl"
            :href="exportUrl"
            class="ui-btn ui-btn--ghost"
            download
          >
            匯出 CSV
          </a>
        </div>
      </div>
    </template>

    <DataTable
      :data="rows"
      :loading="loading"
      :pagination="pagination.total_pages > 1 ? { page: pagination.page, totalPages: pagination.total_pages, infoText: `${pagination.page} / ${pagination.total_pages}` } : null"
      @page-change="(p) => emit('page-change', p)"
    >
      <DataTableColumn columnKey="lot_id" label="LotID" />
      <DataTableColumn columnKey="pj_type" label="Type" />
      <DataTableColumn columnKey="bop" label="BOP" />
      <DataTableColumn columnKey="work_order" label="WorkOrder" />
      <DataTableColumn columnKey="wafer_lot" label="WaferLot" />
      <DataTableColumn columnKey="workcenter" label="WorkCenter" />
      <DataTableColumn columnKey="spec" label="Spec" />
      <DataTableColumn columnKey="equipment_name" label="EquipName" />
      <DataTableColumn columnKey="trackin_time" label="TrackIn" />
      <DataTableColumn columnKey="trackout_time" label="TrackOut" />
      <DataTableColumn columnKey="trackin_qty" label="InQTY" align="right" />
      <DataTableColumn columnKey="trackout_qty" label="OutQTY" align="right" />
      <template #cell="{ row, columnKey, value }">
        <template v-if="columnKey === 'trackin_time'">{{ formatTs(value) }}</template>
        <template v-else-if="columnKey === 'trackout_time'">{{ formatTs(value) }}</template>
        <template v-else>{{ value ?? '' }}</template>
      </template>
    </DataTable>
  </SectionCard>
</template>
