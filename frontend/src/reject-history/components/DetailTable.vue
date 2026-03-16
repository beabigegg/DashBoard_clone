<script setup>
import { computed, ref } from 'vue';
import { useSortableTable } from '../../shared-composables/useSortableTable.js';

const props = defineProps({
  items: { type: Array, default: () => [] },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 20, total: 0, totalPages: 1 }),
  },
  loading: { type: Boolean, default: false },
  paginating: { type: Boolean, default: false },
  selectedParetoCount: { type: Number, default: 0 },
  selectedParetoSummary: { type: String, default: '' },
});

defineEmits(['go-to-page', 'clear-pareto-selection']);

const itemsRef = computed(() => props.items);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(itemsRef);

const showRejectBreakdown = ref(false);

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">
        明細列表
        <span v-if="selectedParetoCount > 0" class="detail-reason-badge">
          Pareto 篩選: {{ selectedParetoSummary || `${selectedParetoCount} 項` }}
          <button type="button" class="badge-clear" @click="$emit('clear-pareto-selection')">×</button>
        </span>
      </div>
    </div>
    <div class="card-body ui-card-body detail-table-wrap" :class="{ 'is-loading': loading, 'is-paginating': paginating }">
      <div v-if="loading" class="table-loading-overlay"><span class="table-spinner"></span></div>
      <table class="detail-table">
        <thead>
          <tr>
            <th @click="toggleSort('CONTAINERNAME')" style="cursor:pointer" :aria-sort="sortKey === 'CONTAINERNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">LOT <span>{{ sortKey === 'CONTAINERNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('WORKCENTERNAME')" style="cursor:pointer" :aria-sort="sortKey === 'WORKCENTERNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">WORKCENTER <span>{{ sortKey === 'WORKCENTERNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('PRODUCTLINENAME')" style="cursor:pointer" :aria-sort="sortKey === 'PRODUCTLINENAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Package <span>{{ sortKey === 'PRODUCTLINENAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('PJ_FUNCTION')" style="cursor:pointer" :aria-sort="sortKey === 'PJ_FUNCTION' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">FUNCTION <span>{{ sortKey === 'PJ_FUNCTION' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="col-left" @click="toggleSort('PJ_TYPE')" style="cursor:pointer" :aria-sort="sortKey === 'PJ_TYPE' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">TYPE <span>{{ sortKey === 'PJ_TYPE' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('WORKFLOWNAME')" style="cursor:pointer" :aria-sort="sortKey === 'WORKFLOWNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">WORKFLOW <span>{{ sortKey === 'WORKFLOWNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('PRODUCTNAME')" style="cursor:pointer" :aria-sort="sortKey === 'PRODUCTNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">PRODUCT <span>{{ sortKey === 'PRODUCTNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('LOSSREASONNAME')" style="cursor:pointer" :aria-sort="sortKey === 'LOSSREASONNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">原因 <span>{{ sortKey === 'LOSSREASONNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('EQUIPMENTNAME')" style="cursor:pointer" :aria-sort="sortKey === 'EQUIPMENTNAME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">EQUIPMENT <span>{{ sortKey === 'EQUIPMENTNAME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('REJECTCOMMENT')" style="cursor:pointer" :aria-sort="sortKey === 'REJECTCOMMENT' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">COMMENT <span>{{ sortKey === 'REJECTCOMMENT' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="th-expandable" @click="showRejectBreakdown = !showRejectBreakdown">
              扣帳報廢量 <span class="expand-icon">{{ showRejectBreakdown ? '▾' : '▸' }}</span>
            </th>
            <template v-if="showRejectBreakdown">
              <th class="th-sub">REJECT</th>
              <th class="th-sub">STANDBY</th>
              <th class="th-sub">QTYTOPROCESS</th>
              <th class="th-sub">INPROCESS</th>
              <th class="th-sub">PROCESSED</th>
            </template>
            <th @click="toggleSort('DEFECT_QTY')" style="cursor:pointer" :aria-sort="sortKey === 'DEFECT_QTY' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">不扣帳報廢量 <span>{{ sortKey === 'DEFECT_QTY' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('TXN_TIME')" style="cursor:pointer" :aria-sort="sortKey === 'TXN_TIME' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">報廢時間 <span>{{ sortKey === 'TXN_TIME' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in sortedData" :key="`${row.TXN_DAY}-${row.CONTAINERNAME}-${row.LOSSREASONNAME}-${idx}`">
            <td>{{ row.CONTAINERNAME || '' }}</td>
            <td>{{ row.WORKCENTERNAME }}</td>
            <td>{{ row.PRODUCTLINENAME }}</td>
            <td>{{ row.PJ_FUNCTION || '' }}</td>
            <td class="col-left">{{ row.PJ_TYPE }}</td>
            <td>{{ row.WORKFLOWNAME || '' }}</td>
            <td>{{ row.PRODUCTNAME || '' }}</td>
            <td>{{ row.LOSSREASONNAME }}</td>
            <td>{{ row.EQUIPMENTNAME || '' }}</td>
            <td>{{ row.REJECTCOMMENT || '' }}</td>
            <td>{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
            <template v-if="showRejectBreakdown">
              <td class="td-sub">{{ formatNumber(row.REJECT_QTY) }}</td>
              <td class="td-sub">{{ formatNumber(row.STANDBY_QTY) }}</td>
              <td class="td-sub">{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
              <td class="td-sub">{{ formatNumber(row.INPROCESS_QTY) }}</td>
              <td class="td-sub">{{ formatNumber(row.PROCESSED_QTY) }}</td>
            </template>
            <td>{{ formatNumber(row.DEFECT_QTY) }}</td>
            <td class="cell-nowrap">{{ row.TXN_TIME || row.TXN_DAY }}</td>
          </tr>
          <tr v-if="!sortedData || sortedData.length === 0">
            <td :colspan="showRejectBreakdown ? 18 : 13" class="placeholder">No data</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <button :disabled="pagination.page <= 1 || loading || paginating" @click="$emit('go-to-page', pagination.page - 1)">上一頁</button>
      <span class="page-info">
        第 {{ pagination.page }} / {{ pagination.totalPages }} 頁 · 共 {{ formatNumber(pagination.total) }} 筆
      </span>
      <button :disabled="pagination.page >= pagination.totalPages || loading || paginating" @click="$emit('go-to-page', pagination.page + 1)">下一頁</button>
    </div>
  </section>
</template>
