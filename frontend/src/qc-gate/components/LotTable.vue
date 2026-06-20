<script setup lang="ts">
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { LotItem } from '../composables/useQcGateData';

interface ActiveFilter {
  station: string;
  bucket: string;
}

interface Props {
  lots?: LotItem[];
  activeFilter?: ActiveFilter | null;
}

const props = withDefaults(defineProps<Props>(), {
  lots: () => [],
  activeFilter: null,
});

const emit = defineEmits<{
  (e: 'clear-filter'): void;
}>();

const BUCKET_LABELS: Record<string, string> = {
  lt_6h: '<6hr',
  '6h_12h': '6-12hr',
  '12h_24h': '12-24hr',
  gt_24h: '>24hr',
};

function formatValue(value: unknown, fallback = '-'): string {
  if (value == null || value === '') {
    return fallback;
  }
  return String(value);
}

function formatQty(value: unknown): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '-';
  }
  return parsed.toLocaleString('zh-TW');
}

function formatWait(value: unknown): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '-';
  }
  return parsed.toFixed(1);
}

function formatTime(value: unknown): string {
  if (!value) {
    return '-';
  }
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function bucketLabel(value: unknown): string {
  return BUCKET_LABELS[String(value ?? '')] || String(value ?? '') || '-';
}

function bucketClass(value: unknown): string {
  return `bucket-pill bucket-${String(value || '').replace(/[^a-z0-9]+/gi, '-')}`;
}
</script>

<template>
  <div class="lot-table-wrap">
    <div v-if="activeFilter" class="filter-chip" data-testid="clear-filter-chip" @click="emit('clear-filter')">
      已套用圖表篩選，點擊清除
    </div>

    <DataTable
      :data="lots"
      :loading="false"
      empty-type="no-data"
    >
      <DataTableColumn columnKey="lot_id" label="LOT ID" :sortable="true" />
      <DataTableColumn columnKey="package" label="Package" :sortable="true" />
      <DataTableColumn columnKey="product" label="Product" :sortable="true" />
      <DataTableColumn columnKey="qty" label="QTY" :sortable="true" align="right" />
      <DataTableColumn columnKey="step" label="站點" :sortable="true" />
      <DataTableColumn columnKey="workorder" label="Workorder" :sortable="true" />
      <DataTableColumn columnKey="move_in_time" label="Move In" :sortable="true" />
      <DataTableColumn columnKey="wait_hours" label="Wait (hr)" :sortable="true" align="right" />
      <DataTableColumn columnKey="bucket" label="區間" :sortable="true" />
      <DataTableColumn columnKey="status" label="狀態" :sortable="true" />

      <template #cell="{ row, columnKey }">
        <template v-if="columnKey === 'lot_id'">{{ formatValue(row.lot_id) }}</template>
        <template v-else-if="columnKey === 'package'">{{ formatValue(row.package) }}</template>
        <template v-else-if="columnKey === 'product'">{{ formatValue(row.product) }}</template>
        <template v-else-if="columnKey === 'qty'">{{ formatQty(row.qty) }}</template>
        <template v-else-if="columnKey === 'step'">{{ formatValue(row.step) }}</template>
        <template v-else-if="columnKey === 'workorder'">{{ formatValue(row.workorder) }}</template>
        <template v-else-if="columnKey === 'move_in_time'">{{ formatTime(row.move_in_time) }}</template>
        <template v-else-if="columnKey === 'wait_hours'">{{ formatWait(row.wait_hours) }}</template>
        <template v-else-if="columnKey === 'bucket'">
          <span :class="bucketClass(row.bucket)">{{ bucketLabel(row.bucket) }}</span>
        </template>
        <template v-else-if="columnKey === 'status'">{{ formatValue(row.status) }}</template>
      </template>
    </DataTable>
  </div>
</template>
