<script setup lang="ts">
import { computed } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

interface Pagination {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
}

const props = defineProps<{
  items?: Record<string, unknown>[];
  pagination?: Pagination;
  loading?: boolean;
  paginating?: boolean;
  selectedParetoCount?: number;
  selectedParetoSummary?: string;
}>();

const emit = defineEmits<{
  (e: 'go-to-page', page: number): void;
  (e: 'clear-pareto-selection'): void;
}>();

const tablePagination = computed(() => {
  const p = props.pagination ?? { page: 1, perPage: 20, total: 0, totalPages: 1 };
  return {
    page: p.page,
    totalPages: p.totalPages,
    infoText: `共 ${Number(p.total || 0).toLocaleString('zh-TW')} 筆`,
  };
});

function formatNumber(value: unknown): string {
  return Number(value || 0).toLocaleString('zh-TW');
}

function onPageChange(newPage: number): void {
  emit('go-to-page', newPage);
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">
        明細列表
        <span v-if="(selectedParetoCount ?? 0) > 0" class="detail-reason-badge">
          Pareto 篩選: {{ selectedParetoSummary || `${selectedParetoCount} 項` }}
          <button type="button" class="badge-clear" @click="emit('clear-pareto-selection')">×</button>
        </span>
      </div>
    </div>
    <div class="card-body ui-card-body detail-card-body">
      <DataTable
        :data="items"
        :loading="loading || paginating"
        :pagination="tablePagination"
        @page-change="onPageChange"
      >
        <DataTableColumn column-key="CONTAINERNAME" label="LOT" :sortable="true" />
        <DataTableColumn column-key="WORKCENTERNAME" label="WORKCENTER" :sortable="true" />
        <DataTableColumn column-key="PRODUCTLINENAME" label="Package" :sortable="true" />
        <DataTableColumn column-key="PJ_FUNCTION" label="FUNCTION" :sortable="true" />
        <DataTableColumn column-key="PJ_TYPE" label="TYPE" :sortable="true" />
        <DataTableColumn column-key="PRODUCTNAME" label="PRODUCT" :sortable="true" />
        <DataTableColumn column-key="LOSSREASONNAME" label="原因" :sortable="true" />
        <DataTableColumn column-key="EQUIPMENTNAME" label="EQUIPMENT" :sortable="true" />
        <DataTableColumn column-key="REJECTCOMMENT" label="COMMENT" :sortable="true" />
        <DataTableColumn column-key="REJECT_TOTAL_QTY" label="扣帳報廢量" :sortable="true" align="right" />
        <DataTableColumn column-key="DEFECT_QTY" label="不扣帳報廢量" :sortable="true" align="right" />
        <DataTableColumn column-key="TXN_TIME" label="報廢時間" :sortable="true" />

        <template #cell="{ row, columnKey, value }">
          <template v-if="columnKey === 'CONTAINERNAME'">{{ row.CONTAINERNAME || '' }}</template>
          <template v-else-if="columnKey === 'PJ_FUNCTION'">{{ row.PJ_FUNCTION || '' }}</template>
          <template v-else-if="columnKey === 'PRODUCTNAME'">{{ row.PRODUCTNAME || '' }}</template>
          <template v-else-if="columnKey === 'EQUIPMENTNAME'">{{ row.EQUIPMENTNAME || '' }}</template>
          <template v-else-if="columnKey === 'REJECTCOMMENT'">{{ row.REJECTCOMMENT || '' }}</template>
          <template v-else-if="columnKey === 'REJECT_TOTAL_QTY'">{{ formatNumber(row.REJECT_TOTAL_QTY) }}</template>
          <template v-else-if="columnKey === 'DEFECT_QTY'">{{ formatNumber(row.DEFECT_QTY) }}</template>
          <template v-else-if="columnKey === 'TXN_TIME'">
            <span class="cell-nowrap">{{ row.TXN_TIME || row.TXN_DAY }}</span>
          </template>
          <template v-else>{{ value }}</template>
        </template>

        <template #expand="{ row }">
          <div class="expand-breakdown">
            <span class="expand-breakdown__title">扣帳報廢明細</span>
            <div class="expand-breakdown__grid">
              <div class="expand-breakdown__item">
                <span class="expand-breakdown__label">REJECT</span>
                <span class="expand-breakdown__value">{{ formatNumber(row.REJECT_QTY) }}</span>
              </div>
              <div class="expand-breakdown__item">
                <span class="expand-breakdown__label">STANDBY</span>
                <span class="expand-breakdown__value">{{ formatNumber(row.STANDBY_QTY) }}</span>
              </div>
              <div class="expand-breakdown__item">
                <span class="expand-breakdown__label">QTYTOPROCESS</span>
                <span class="expand-breakdown__value">{{ formatNumber(row.QTYTOPROCESS_QTY) }}</span>
              </div>
              <div class="expand-breakdown__item">
                <span class="expand-breakdown__label">INPROCESS</span>
                <span class="expand-breakdown__value">{{ formatNumber(row.INPROCESS_QTY) }}</span>
              </div>
              <div class="expand-breakdown__item">
                <span class="expand-breakdown__label">PROCESSED</span>
                <span class="expand-breakdown__value">{{ formatNumber(row.PROCESSED_QTY) }}</span>
              </div>
            </div>
          </div>
        </template>
      </DataTable>
    </div>
  </section>
</template>

<style scoped>
/* Flat-table layout: remove card-body padding so DataTable extends flush to card edges */
.detail-card-body {
  padding: 0;
}

.expand-breakdown {
  padding: 4px 0;
}

.expand-breakdown__title {
  font-size: 12px;
  font-weight: 700;
  color: theme('colors.text.subtle');
  margin-bottom: 8px;
  display: block;
}

.expand-breakdown__grid {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.expand-breakdown__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.expand-breakdown__label {
  font-size: 11px;
  color: theme('colors.text.muted');
  font-weight: 600;
}

.expand-breakdown__value {
  font-size: 13px;
  font-weight: 600;
  color: theme('colors.text.primary');
}
</style>
