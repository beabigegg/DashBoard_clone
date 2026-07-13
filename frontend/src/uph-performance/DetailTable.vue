<script setup lang="ts">
import { computed } from 'vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';

interface DetailRow {
  lot_id: string;
  equipment_id: string;
  event_time: string;
  uph_value: number | null;
  package: string | null;
  pj_type: string | null;
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
  const m = props.meta ?? { page: 1, per_page: 50, total_count: 0, total_pages: 1 };
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
  return s;
}

function formatUph(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 2 });
}

function onPageChange(page: number): void {
  emit('go-to-page', page);
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">
        UPH 明細
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
        <DataTableColumn column-key="lot_id"       label="LOT ID"      :sortable="false" />
        <DataTableColumn column-key="equipment_id" label="機台 ID"      :sortable="false" />
        <DataTableColumn column-key="event_time"   label="事件時間"     :sortable="false" />
        <DataTableColumn column-key="uph_value"    label="UPH"          :sortable="false" />
        <DataTableColumn column-key="package"      label="Package"      :sortable="false" />
        <DataTableColumn column-key="pj_type"      label="Type"         :sortable="false" />

        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'event_time'">
            <span class="cell-nowrap">{{ formatTs(row.event_time) }}</span>
          </template>
          <template v-else-if="columnKey === 'uph_value'">
            {{ formatUph(row.uph_value as number | null) }}
          </template>
          <template v-else-if="columnKey === 'package'">
            {{ row.package ?? '—' }}
          </template>
          <template v-else-if="columnKey === 'pj_type'">
            {{ row.pj_type ?? '—' }}
          </template>
        </template>
      </DataTable>
    </div>
  </section>
</template>
