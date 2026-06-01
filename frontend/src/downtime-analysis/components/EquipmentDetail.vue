<script setup lang="ts">
import { computed, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { EquipmentDetailRow, Pagination } from '../types';

const props = defineProps<{
  rows: EquipmentDetailRow[];
  pagination: Pagination;
  exporting?: boolean;
}>();

const emit = defineEmits<{
  (e: 'page-change', page: number): void;
  (e: 'export'): void;
}>();

const tableData = computed(() =>
  props.rows.map((r) => ({
    resource_name: r.resource_name ?? r.resource_id,
    workcenter: r.workcenter ?? '—',
    family: r.family ?? '—',
    udt_hours: r.udt_hours,
    sdt_hours: r.sdt_hours,
    egt_hours: r.egt_hours,
    total_hours: r.total_hours,
    event_count: r.event_count,
    top_reason: r.top_reason ?? '—',
  }))
);

const paginationShape = computed(() => ({
  page: props.pagination.page,
  totalPages: props.pagination.total_pages,
  infoText: `共 ${props.pagination.total_rows} 筆`,
}));

function formatHours(val: unknown): string {
  return typeof val === 'number' ? val.toFixed(2) : String(val ?? '');
}

// Toolbar ref for focus management
const exportBtnRef = ref<HTMLButtonElement | null>(null);
</script>

<template>
  <div class="equipment-detail-section">
    <div class="detail-toolbar">
      <h3 class="section-title">設備停機明細</h3>
      <button
        ref="exportBtnRef"
        type="button"
        class="ui-btn ui-btn--secondary"
        :class="{ 'is-loading': exporting }"
        :disabled="rows.length === 0 || exporting"
        @click="emit('export')"
      >
        {{ exporting ? '匯出中...' : '↓ 匯出 CSV' }}
      </button>
    </div>

    <DataTable
      :data="tableData"
      :pagination="rows.length > 0 ? paginationShape : null"
      @page-change="(p) => emit('page-change', p)"
    >
      <DataTableColumn column-key="resource_name" label="設備名稱" :sortable="true" />
      <DataTableColumn column-key="workcenter" label="工作站" :sortable="true" />
      <DataTableColumn column-key="family" label="機種" :sortable="true" />
      <DataTableColumn column-key="udt_hours" label="UDT (h)" :sortable="true" align="right" />
      <DataTableColumn column-key="sdt_hours" label="SDT (h)" :sortable="true" align="right" />
      <DataTableColumn column-key="egt_hours" label="EGT (h)" :sortable="true" align="right" />
      <DataTableColumn column-key="total_hours" label="總計 (h)" :sortable="true" align="right" />
      <DataTableColumn column-key="event_count" label="事件數" :sortable="true" align="right" />
      <DataTableColumn column-key="top_reason" label="主要原因" :sortable="true" />

      <template #cell="{ columnKey, value }">
        <span v-if="['udt_hours','sdt_hours','egt_hours','total_hours'].includes(columnKey)">
          {{ formatHours(value) }}
        </span>
        <span v-else>{{ value }}</span>
      </template>
    </DataTable>
  </div>
</template>
