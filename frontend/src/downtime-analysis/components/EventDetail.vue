<script setup lang="ts">
import { computed, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { EventDetailRow, Pagination } from '../types';
import { formatDowntimeDate } from '../formatDowntimeDate';

const props = defineProps<{
  rows: EventDetailRow[];
  pagination: Pagination;
  exporting?: boolean;
}>();

const emit = defineEmits<{
  (e: 'page-change', page: number): void;
  (e: 'export'): void;
}>();

function jobField(row: EventDetailRow, key: keyof NonNullable<EventDetailRow['job']>): string {
  if (row.job === null) return '—';
  const value = row.job[key];
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return value.toFixed(1);
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
}

function matchSourceLabel(src: string): string {
  switch (src) {
    case 'jobid': return 'JOBID';
    case 'overlap': return '時間重疊';
    case 'none': return '未匹配';
    default: return src;
  }
}

const tableData = computed(() =>
  props.rows.map((r) => ({
    resource_name: r.resource_name ?? r.resource_id,
    status: r.status,
    reason: r.reason ?? '—',
    category: r.category,
    start_ts: formatDowntimeDate(r.start_ts),
    end_ts: formatDowntimeDate(r.end_ts),
    hours: r.hours,
    match_source: matchSourceLabel(r.match_source),
    job_order_name: jobField(r, 'job_order_name'),
    job_model: jobField(r, 'job_model'),
    symptom: jobField(r, 'symptom'),
    cause: jobField(r, 'cause'),
    repair: jobField(r, 'repair'),
    wait_min: jobField(r, 'wait_min'),
    repair_min: jobField(r, 'repair_min'),
    handler: jobField(r, 'handler'),
    // Keep match_source raw for badge class
    _match_source_raw: r.match_source,
    _match_ambiguous: r.job?.match_ambiguous ?? false,
  }))
);

const paginationShape = computed(() => ({
  page: props.pagination.page,
  totalPages: props.pagination.total_pages,
  infoText: `共 ${props.pagination.total_rows} 筆`,
}));

const exportBtnRef = ref<HTMLButtonElement | null>(null);
</script>

<template>
  <div class="event-detail-section">
    <div class="detail-toolbar">
      <h3 class="section-title">停機事件明細</h3>
      <button
        ref="exportBtnRef"
        type="button"
        class="export-csv-btn"
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
      <DataTableColumn column-key="status" label="狀態" :sortable="true" />
      <DataTableColumn column-key="reason" label="原因" :sortable="true" />
      <DataTableColumn column-key="category" label="類別" :sortable="true" />
      <DataTableColumn column-key="start_ts" label="開始時間" :sortable="true" />
      <DataTableColumn column-key="end_ts" label="結束時間" :sortable="true" />
      <DataTableColumn column-key="hours" label="時數 (h)" :sortable="true" align="right" />
      <DataTableColumn column-key="match_source" label="橋接來源" :sortable="true" />
      <DataTableColumn column-key="job_order_name" label="工單名稱" :sortable="true" />
      <DataTableColumn column-key="job_model" label="機型" :sortable="true" />
      <DataTableColumn column-key="symptom" label="症狀" :sortable="true" />
      <DataTableColumn column-key="cause" label="原因碼" :sortable="true" />
      <DataTableColumn column-key="repair" label="修復" :sortable="true" />
      <DataTableColumn column-key="wait_min" label="待料 (min)" :sortable="true" align="right" />
      <DataTableColumn column-key="repair_min" label="維修 (min)" :sortable="true" align="right" />
      <DataTableColumn column-key="handler" label="負責人" :sortable="true" />

      <template #cell="{ columnKey, row, value }">
        <template v-if="columnKey === 'status'">
          <span class="status-badge" :class="`status-${String(value).toLowerCase()}`">
            {{ value }}
          </span>
        </template>
        <template v-else-if="columnKey === 'match_source'">
          <span
            class="match-badge"
            :class="{
              'badge-success': row._match_source_raw === 'jobid',
              'badge-warning': row._match_source_raw === 'overlap',
              'badge-muted': row._match_source_raw === 'none',
            }"
          >
            {{ value }}
            <span
              v-if="row._match_source_raw !== 'none' && row._match_ambiguous"
              class="ambiguous-indicator"
              title="候補重疊率 ≥80%，匹配結果可能存疑"
              aria-label="匹配存疑"
            >⚠</span>
          </span>
        </template>
        <template v-else-if="columnKey === 'hours'">
          {{ typeof value === 'number' ? value.toFixed(2) : value }}
        </template>
        <template v-else>
          {{ value }}
        </template>
      </template>
    </DataTable>
  </div>
</template>
