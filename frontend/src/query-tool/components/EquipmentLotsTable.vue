<script setup lang="ts">
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import ExportButton from './ExportButton.vue';
import { formatCellValue } from '../utils/values';

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

const COLUMN_DEFS = Object.freeze([
  { key: 'CONTAINERNAME', label: 'LOT ID' },
  { key: 'WAFER_LOT_ID', label: 'WAFER LOT' },
  { key: 'PJ_TYPE', label: 'TYPE' },
  { key: 'PJ_BOP', label: 'BOP' },
  { key: 'SPECNAME', label: 'SPECNAME' },
  { key: 'PJ_WORKORDER', label: 'WORKORDER' },
  { key: 'TRACKINTIMESTAMP', label: 'TRACKINTIMESTAMP' },
  { key: 'TRACKOUTTIMESTAMP', label: 'TRACKOUTTIMESTAMP' },
  { key: 'TRACKINQTY', label: 'TRACKINQTY' },
  { key: 'TRACKOUTQTY', label: 'TRACKOUTQTY' },
  { key: 'EQUIPMENTNAME', label: 'EQUIPMENTNAME' },
  { key: 'WORKCENTERNAME', label: 'WORKCENTERNAME' },
]);
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">生產紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出生產紀錄"
        @click="emit('export')"
      />
    </div>

    <ErrorBanner :message="error" />

    <DataTable
      :data="rows as Record<string, unknown>[]"
      :loading="loading"
      empty-type="no-data"
    >
      <DataTableColumn
        v-for="col in COLUMN_DEFS"
        :key="col.key"
        :column-key="col.key"
        :label="col.label"
        :sortable="true"
      />
      <template #cell="{ row, columnKey }">
        {{ formatCellValue(row[columnKey]) }}
      </template>
    </DataTable>
  </div>
</template>
