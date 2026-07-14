<script setup lang="ts">
import { computed } from 'vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';

interface DetailRow {
  alarm_id: string | null;
  eqp_id: string | null;
  eqp_type: string | null;
  lot_id: string | null;
  pj_type: string | null;
  product_line: string | null;
  pj_bop: string | null;
  alarm_text: string | null;
  alarm_category_code: number | null;
  alarm_start: string | null;
  alarm_end: string | null;
  duration_seconds: number | null;
  detail_params: Record<string, unknown> | null;
  // v4 spool: raw EVENT_TYPE ('EQP_SECS_ALARM' | 'EQP_SECS_EVENT');
  // null when the row comes from a pre-v4 spool
  alarm_source: string | null;
}

interface DetailMeta {
  page: number;
  per_page: number;
  total_count: number;
  total_pages: number;
}

const props = defineProps<{
  rows?: DetailRow[];
  meta?: DetailMeta;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'go-to-page', page: number): void;
}>();

const tablePagination = computed(() => {
  const m = props.meta ?? { page: 1, per_page: 20, total_count: 0, total_pages: 1 };
  return {
    page: m.page,
    totalPages: m.total_pages,
    infoText: `共 ${Number(m.total_count || 0).toLocaleString('zh-TW')} 筆`,
  };
});

function formatTs(value: unknown): string {
  if (!value) return '';
  const s = String(value);
  const match = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/);
  if (match) return `${match[1]} ${match[2]}`;
  const dateOnly = s.match(/^(\d{4}-\d{2}-\d{2})$/);
  if (dateOnly) return dateOnly[1];
  return s;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
}

function formatDetailParams(params: Record<string, unknown> | null): string {
  if (!params) return '';
  try {
    return JSON.stringify(params, null, 2);
  } catch {
    return String(params);
  }
}

function onPageChange(page: number): void {
  emit('go-to-page', page);
}

const hasExpandable = computed(() =>
  Array.isArray(props.rows) && props.rows.some((r) => r.detail_params != null)
);
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">
        ALARM 明細
        <span v-if="meta && meta.total_count > 0" class="detail-count-badge">
          {{ meta.total_count.toLocaleString('zh-TW') }} 筆
        </span>
      </div>
    </div>
    <div class="card-body ui-card-body detail-card-body">
      <DataTable
        :data="rows"
        :loading="loading"
        :pagination="tablePagination"
        @page-change="onPageChange"
      >
        <DataTableColumn column-key="eqp_id"          label="機台 ID"      :sortable="false" />
        <DataTableColumn column-key="eqp_type"        label="機台類型"     :sortable="false" />
        <DataTableColumn column-key="alarm_id"        label="ALARM ID"     :sortable="false" />
        <DataTableColumn column-key="alarm_text"      label="ALARM 訊息"   :sortable="false" />
        <DataTableColumn column-key="alarm_source"    label="通報來源"     :sortable="false" />
        <DataTableColumn column-key="alarm_start"     label="發生時間"     :sortable="false" />
        <DataTableColumn column-key="alarm_end"       label="解除時間"     :sortable="false" />
        <DataTableColumn column-key="duration_seconds"label="排除時間"     :sortable="false" />
        <DataTableColumn column-key="lot_id"          label="LOT ID"       :sortable="false" />
        <DataTableColumn column-key="pj_type"         label="Type"         :sortable="false" />
        <DataTableColumn column-key="product_line"    label="Package"      :sortable="false" />
        <DataTableColumn column-key="pj_bop"          label="BOP"          :sortable="false" />

        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'alarm_start'">
            <span class="cell-nowrap">{{ formatTs(row.alarm_start) }}</span>
          </template>
          <template v-else-if="columnKey === 'alarm_end'">
            <span class="cell-nowrap">{{ row.alarm_end ? formatTs(row.alarm_end) : '尚未解除' }}</span>
          </template>
          <template v-else-if="columnKey === 'duration_seconds'">
            <span :class="row.alarm_end ? '' : 'cell-unresolved'">
              {{ formatDuration(row.duration_seconds) }}
            </span>
          </template>
          <template v-else-if="columnKey === 'lot_id'">
            {{ row.lot_id ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'pj_type'">
            {{ row.pj_type ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'product_line'">
            {{ row.product_line ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'pj_bop'">
            {{ row.pj_bop ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'alarm_text'">
            <span class="alarm-text-cell" :title="String(row.alarm_text ?? '')">
              {{ row.alarm_text ?? '—' }}
            </span>
          </template>
          <template v-else-if="columnKey === 'alarm_source'">
            <span class="cell-nowrap">{{ row.alarm_source ?? '—' }}</span>
          </template>
        </template>

        <template v-if="hasExpandable" #expand="{ row }">
          <div v-if="row.detail_params" class="detail-params-expand">
            <pre class="detail-params-pre">{{ formatDetailParams((row.detail_params as Record<string, unknown> | null)) }}</pre>
          </div>
          <div v-else class="detail-params-none">無額外參數</div>
        </template>
      </DataTable>
    </div>
  </section>
</template>
