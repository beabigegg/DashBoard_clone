<script setup>
import { computed, ref } from 'vue';

import Pagination from '../../shared-ui/components/PaginationControl.vue';

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
    default: () => ({ page: 1, page_size: 200, total_count: 0, total_pages: 1 }),
  },
  direction: {
    type: String,
    default: 'backward',
  },
});

const emit = defineEmits(['export-csv', 'prev-page', 'next-page']);

const sortField = ref('DEFECT_RATE');
const sortAsc = ref(false);

const COLUMNS_BACKWARD = [
  { key: 'CONTAINERNAME', label: 'LOT ID', width: '140px' },
  { key: 'PJ_TYPE', label: 'TYPE', width: '80px' },
  { key: 'PRODUCTLINENAME', label: 'PACKAGE', width: '90px' },
  { key: 'WORKFLOW', label: 'WORKFLOW', width: '100px' },
  { key: 'DETECTION_EQUIPMENTNAME', label: '偵測設備', width: '110px' },
  { key: 'INPUT_QTY', label: '投入數', width: '70px', numeric: true },
  { key: 'LOSS_REASON', label: '不良原因', width: '130px' },
  { key: 'DEFECT_QTY', label: '不良數', width: '70px', numeric: true },
  { key: 'DEFECT_RATE', label: '不良率(%)', width: '90px', numeric: true },
  { key: 'ANCESTOR_COUNT', label: '上游LOT數', width: '80px', numeric: true },
  { key: 'UPSTREAM_MACHINES', label: '上游機台', width: '200px' },
];

const COLUMNS_FORWARD = [
  { key: 'CONTAINERNAME', label: 'LOT ID', width: '140px' },
  { key: 'DETECTION_EQUIPMENTNAME', label: '偵測設備', width: '120px' },
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

const sortedData = computed(() => {
  if (!props.data || !props.data.length) return [];
  const field = sortField.value;
  const asc = sortAsc.value;
  return [...props.data].sort((a, b) => {
    const va = a[field] ?? '';
    const vb = b[field] ?? '';
    if (typeof va === 'number' && typeof vb === 'number') {
      return asc ? va - vb : vb - va;
    }
    const sa = String(va);
    const sb = String(vb);
    return asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
  });
});

const tableInfo = computed(() => {
  const p = props.pagination;
  const total = Number(p.total_count || 0);
  if (total <= 0) return '暫無資料';
  const page = Number(p.page || 1);
  const pageSize = Number(p.page_size || 200);
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `顯示 ${start} - ${end} 筆，共 ${total.toLocaleString()} 筆`;
});

function toggleSort(field) {
  if (sortField.value === field) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortField.value = field;
    sortAsc.value = false;
  }
}

function sortIcon(field) {
  if (sortField.value !== field) return '';
  return sortAsc.value ? ' ▲' : ' ▼';
}

function formatCell(value, col) {
  if (value == null || value === '') return '-';
  if (col.key === 'DEFECT_RATE' || col.key === 'DOWNSTREAM_REJECT_RATE') return Number(value).toFixed(2);
  if (col.numeric) return Number(value).toLocaleString();
  return value;
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="detail-header">
        <h3 class="section-title">LOT 明細</h3>
        <div class="detail-actions">
          <span class="detail-count">{{ tableInfo }}</span>
          <button type="button" class="btn-sm" :disabled="loading" @click="$emit('export-csv')">
            匯出 CSV
          </button>
        </div>
      </div>

      <div class="table-wrapper">
        <table class="detail-table">
          <thead>
            <tr>
              <th
                v-for="col in activeColumns"
                :key="col.key"
                :style="{ width: col.width }"
                class="sortable"
                @click="toggleSort(col.key)"
              >
                {{ col.label }}{{ sortIcon(col.key) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in sortedData" :key="idx">
              <td v-for="col in activeColumns" :key="col.key" :class="{ numeric: col.numeric }">
                {{ formatCell(row[col.key], col) }}
              </td>
            </tr>
            <tr v-if="!sortedData.length">
              <td :colspan="activeColumns.length" class="empty-row">暫無資料</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Pagination
        :visible="Number(pagination.total_pages || 1) > 1"
        :page="Number(pagination.page || 1)"
        :total-pages="Number(pagination.total_pages || 1)"
        @prev="emit('prev-page')"
        @next="emit('next-page')"
      />
    </div>
  </section>
</template>
