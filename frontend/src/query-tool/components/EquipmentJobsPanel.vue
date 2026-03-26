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
      <h4 class="card-title ui-card-title">維修紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出維修紀錄"
        @click="emit('export')"
      />
    </div>

    <ErrorBanner :message="error" />

    <DataTable
      :data="rows"
      :loading="loading"
      empty-type="no-data"
    >
      <DataTableColumn column-key="JOBID" label="JOBID" :sortable="true" />
      <DataTableColumn column-key="JOBSTATUS" label="JOBSTATUS" :sortable="true" />
      <DataTableColumn column-key="CAUSECODENAME" label="CAUSECODENAME" :sortable="true" />
      <DataTableColumn column-key="REPAIRCODENAME" label="REPAIRCODENAME" :sortable="true" />
      <DataTableColumn column-key="SYMPTOMCODENAME" label="SYMPTOMCODENAME" :sortable="true" />
      <DataTableColumn column-key="CREATEDATE" label="CREATEDATE" :sortable="true" />
      <DataTableColumn column-key="COMPLETEDATE" label="COMPLETEDATE" :sortable="true" />
      <DataTableColumn column-key="RESOURCENAME" label="RESOURCENAME" :sortable="true" />

      <template #cell="{ row, columnKey }">
        {{ formatCellValue(row[columnKey]) }}
      </template>

      <template #expand="{ row }">
        <div class="grid gap-2 text-[11px] text-slate-600 md:grid-cols-2">
          <p><span class="font-semibold text-slate-700">RESOURCEID:</span> {{ formatCellValue(row.RESOURCEID) }}</p>
          <p><span class="font-semibold text-slate-700">JOBMODELNAME:</span> {{ formatCellValue(row.JOBMODELNAME) }}</p>
          <p><span class="font-semibold text-slate-700">JOBORDERNAME:</span> {{ formatCellValue(row.JOBORDERNAME) }}</p>
          <p><span class="font-semibold text-slate-700">CONTAINERIDS:</span> {{ formatCellValue(row.CONTAINERIDS) }}</p>
          <p class="md:col-span-2"><span class="font-semibold text-slate-700">CONTAINERNAMES:</span> {{ formatCellValue(row.CONTAINERNAMES) }}</p>
        </div>
      </template>
    </DataTable>
  </div>
</template>
