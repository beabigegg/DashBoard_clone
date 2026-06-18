<script setup lang="ts">
import { computed } from 'vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';

interface DetailRow {
  event_id: string;
  eqp_id: string;
  eqp_type: string;
  lot_id: string | null;
  alarm_text: string | null;
  alarm_category: string;
  alarm_time: string;
  detail_params: Record<string, unknown> | null;
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

/**
 * Format alarm_time safely: inspect H/M/S via regex before new Date()
 * to avoid ±8h TZ shift on Oracle DATE midnight UTC columns
 * (frontend-patterns.md).
 */
function formatAlarmTime(value: unknown): string {
  if (!value) return '';
  const s = String(value);
  // ISO-like: YYYY-MM-DD HH:MM:SS or YYYY-MM-DDTHH:MM:SS
  const match = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/);
  if (match) {
    return `${match[1]} ${match[2]}`;
  }
  // Date only (Oracle DATE midnight UTC): return as-is to avoid TZ shift
  const dateOnly = s.match(/^(\d{4}-\d{2}-\d{2})$/);
  if (dateOnly) {
    return dateOnly[1];
  }
  return s;
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

// Whether any row has detail_params (controls expand slot registration)
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
        <DataTableColumn column-key="eqp_id" label="機台 ID" :sortable="false" />
        <DataTableColumn column-key="eqp_type" label="機台類型" :sortable="false" />
        <DataTableColumn column-key="lot_id" label="LOT ID" :sortable="false" />
        <DataTableColumn column-key="alarm_text" label="ALARM 訊息" :sortable="false" />
        <DataTableColumn column-key="alarm_category" label="ALARM 類別" :sortable="false" />
        <DataTableColumn column-key="alarm_time" label="ALARM 時間" :sortable="false" />

        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'alarm_time'">
            <span class="cell-nowrap">{{ formatAlarmTime(row.alarm_time) }}</span>
          </template>
          <template v-else-if="columnKey === 'lot_id'">
            {{ row.lot_id ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'alarm_text'">
            <span class="alarm-text-cell" :title="String(row.alarm_text ?? '')">
              {{ row.alarm_text ?? '—' }}
            </span>
          </template>
        </template>

        <!-- Built-in DataTable #expand slot: renders detail_params JSON in expanded row -->
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
