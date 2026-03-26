<script setup>
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import ExportButton from './ExportButton.vue';
import { formatCellValue } from '../utils/values.js';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  exportDisabled: {
    type: Boolean,
    default: true,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['export']);
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">報廢紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出報廢紀錄"
        @click="emit('export')"
      />
    </div>

    <ErrorBanner :message="error" />

    <DataTable
      :data="rows"
      :loading="loading"
      empty-type="no-data"
    >
      <DataTableColumn column-key="EQUIPMENTNAME" label="EQUIPMENTNAME" :sortable="true" />
      <DataTableColumn column-key="LOSSREASONNAME" label="LOSSREASONNAME" :sortable="true" />
      <DataTableColumn column-key="TOTAL_REJECT_QTY" label="TOTAL_REJECT_QTY" :sortable="true" />
      <DataTableColumn column-key="TOTAL_DEFECT_QTY" label="TOTAL_DEFECT_QTY" :sortable="true" />
      <DataTableColumn column-key="AFFECTED_LOT_COUNT" label="AFFECTED_LOT_COUNT" :sortable="true" />
      <template #cell="{ row, columnKey }">
        {{ formatCellValue(row[columnKey]) }}
      </template>
    </DataTable>
  </div>
</template>
