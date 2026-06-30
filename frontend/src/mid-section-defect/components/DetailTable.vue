<script setup>
import { computed } from 'vue';

import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

const props = defineProps({
  data: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  pagination: {
    type: Object,
    default: () => ({ page: 1, page_size: 20, total_count: 0, total_pages: 1 }),
  },
  direction: {
    type: String,
    default: 'backward',
  },
  suspectMachines: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['export-csv', 'prev-page', 'next-page']);

const COLUMNS_BACKWARD = [
  { key: 'CONTAINERNAME', label: 'LOT ID', width: '140px' },
  { key: 'PJ_TYPE', label: 'TYPE', width: '80px' },
  { key: 'PRODUCTLINENAME', label: 'PACKAGE', width: '90px' },
  { key: 'WORKFLOW', label: 'WORKFLOW', width: '100px' },
  { key: 'DETECTION_EQUIPMENTNAME', label: '偵測設備', width: '110px' },
  { key: 'INPUT_QTY', label: '投入數', width: '70px', numeric: true },
  { key: 'LOSS_REASON', label: '報廢原因', width: '130px' },
  { key: 'DEFECT_QTY', label: '不良數', width: '70px', numeric: true },
  { key: 'DEFECT_RATE', label: '不良率(%)', width: '90px', numeric: true },
  { key: 'ANCESTOR_COUNT', label: '上游LOT數', width: '80px', numeric: true },
  { key: 'UPSTREAM_MACHINE_COUNT', label: '上游台數', width: '80px', numeric: true },
  { key: 'SUSPECT_HITS', label: '嫌疑命中', width: '200px', custom: true },
];

const COLUMNS_FORWARD = [
  { key: 'CONTAINERNAME', label: 'LOT ID', width: '140px' },
  { key: 'DETECTION_EQUIPMENTNAME', label: '偵測設備', width: '120px' },
  { key: 'DETECTION_LOSS_REASON', label: '前段不良原因', width: '130px' },
  { key: 'TRACKINQTY', label: '偵測投入', width: '80px', numeric: true },
  { key: 'DEFECT_QTY', label: '偵測不良', width: '80px', numeric: true },
  { key: 'DOWNSTREAM_STATIONS_REACHED', label: '下游到達站數', width: '100px', numeric: true },
  { key: 'DOWNSTREAM_TOTAL_REJECT', label: '下游不良總數', width: '100px', numeric: true },
  { key: 'DOWNSTREAM_REJECT_RATE', label: '下游不良率(%)', width: '110px', numeric: true },
  { key: 'WORST_DOWNSTREAM_STATION', label: '最差下游站', width: '120px' },
];

const activeColumns = computed(() => (
  props.direction === 'forward' ? COLUMNS_FORWARD : COLUMNS_BACKWARD
));

const tableInfo = computed(() => {
  const p = props.pagination;
  const total = Number(p.total_count || 0);
  if (total <= 0) return '暫無資料';
  const page = Number(p.page || 1);
  const pageSize = Number(p.page_size || 20);
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `顯示 ${start} - ${end} 筆，共 ${total.toLocaleString()} 筆`;
});

const tablePagination = computed(() => ({
  page: Number(props.pagination.page || 1),
  totalPages: Number(props.pagination.total_pages || 1),
  infoText: tableInfo.value,
}));

function handlePageChange(page) {
  const current = Number(props.pagination.page || 1);
  if (page > current) {
    emit('next-page');
  } else if (page < current) {
    emit('prev-page');
  }
}

function formatCell(value, col) {
  if (value == null || value === '') return '-';
  if (col.key === 'DEFECT_RATE' || col.key === 'DOWNSTREAM_REJECT_RATE') return Number(value).toFixed(2);
  if (col.numeric) return Number(value).toLocaleString();
  return value;
}

function getSuspectHits(row) {
  const upstreamMachines = row.UPSTREAM_MACHINES;
  if (!Array.isArray(upstreamMachines) || upstreamMachines.length === 0) return null;
  const suspects = props.suspectMachines;
  if (!suspects || suspects.length === 0) return null;

  const suspectSet = new Set(suspects);
  const machineNames = upstreamMachines.map((m) => m.machine || m);
  const uniqueNames = [...new Set(machineNames)];
  const hits = uniqueNames.filter((name) => suspectSet.has(name));

  if (hits.length === 0) return null;

  return {
    hitNames: hits,
    hitCount: hits.length,
    totalCount: uniqueNames.length,
    fullMatch: hits.length === uniqueNames.length,
  };
}
</script>

<template>
  <section class="section-card" data-testid="detail-table">
    <div class="section-inner">
      <div class="detail-header">
        <h3 class="section-title">LOT 明細</h3>
        <div class="detail-actions">
          <span class="detail-count">{{ tableInfo }}</span>
          <button type="button" class="ui-btn ui-btn--secondary" :disabled="loading" data-testid="export-btn" @click="$emit('export-csv')">
            匯出 CSV
          </button>
        </div>
      </div>

      <DataTable
        :data="data"
        :loading="loading"
        :pagination="tablePagination"
        @page-change="handlePageChange"
      >
        <DataTableColumn
          v-for="col in activeColumns"
          :key="col.key"
          :column-key="col.key"
          :label="col.label"
          :width="col.width"
          :align="col.numeric ? 'right' : 'left'"
          sortable
        />

        <template #cell="{ row, columnKey, value }">
          <template v-if="columnKey === 'SUSPECT_HITS'">
            <span v-if="getSuspectHits(row)" :class="{ 'hit-full': getSuspectHits(row).fullMatch }" class="suspect-cell">
              {{ getSuspectHits(row).hitNames.join(', ') }}
              <span class="hit-ratio">({{ getSuspectHits(row).hitCount }}/{{ getSuspectHits(row).totalCount }})</span>
            </span>
            <span v-else class="no-hit">-</span>
          </template>
          <template v-else>{{ formatCell(value, activeColumns.find(c => c.key === columnKey) || {}) }}</template>
        </template>
      </DataTable>
    </div>
  </section>
</template>

<style scoped>
.suspect-cell {
  font-size: 12px;
  color: var(--text-primary, theme('colors.token.h374151'));
}
.hit-ratio {
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
  margin-left: theme('spacing.token.p4');
}
.hit-full {
  color: theme('colors.emerald.600');
  font-weight: 600;
}
.no-hit {
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
}
</style>
