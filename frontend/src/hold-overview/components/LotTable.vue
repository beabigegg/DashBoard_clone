<script setup>
import { computed } from 'vue';
import { useSortableTable } from '../../shared-composables/useSortableTable.js';

import Pagination from '../../shared-ui/components/PaginationControl.vue';

const props = defineProps({
  lots: {
    type: Array,
    default: () => [],
  },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 20, total: 0, totalPages: 1 }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
  hasActiveFilters: {
    type: Boolean,
    default: false,
  },
  filterText: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['clear-filters', 'prev-page', 'next-page']);

const lotsRef = computed(() => props.lots);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(lotsRef);

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function formatAge(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return `${value}天`;
}

const tableInfo = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const perPage = Number(props.pagination?.perPage || 20);
  const total = Number(props.pagination?.total || 0);

  if (total <= 0) {
    return 'No data';
  }

  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);
  return `顯示 ${start} - ${end} / ${formatNumber(total)}`;
});

const pageInfo = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const totalPages = Number(props.pagination?.totalPages || 1);
  return `Page ${page} / ${totalPages}`;
});
</script>

<template>
  <section class="table-section">
    <div class="table-header">
      <div class="table-title">Hold Lot Details</div>
      <div v-if="hasActiveFilters" class="filter-indicator">
        <span>篩選: {{ filterText }}</span>
        <span class="clear-btn" @click="emit('clear-filters')">×</span>
      </div>
      <div class="table-info">{{ tableInfo }}</div>
    </div>

    <div class="table-container">
      <table class="lot-table">
        <thead>
          <tr>
            <th @click="toggleSort('lotId')" style="cursor:pointer" :aria-sort="sortKey === 'lotId' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">LOTID <span>{{ sortKey === 'lotId' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('workorder')" style="cursor:pointer" :aria-sort="sortKey === 'workorder' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">WORKORDER <span>{{ sortKey === 'workorder' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('qty')" style="cursor:pointer" :aria-sort="sortKey === 'qty' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">QTY <span>{{ sortKey === 'qty' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('product')" style="cursor:pointer" :aria-sort="sortKey === 'product' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Product <span>{{ sortKey === 'product' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('package')" style="cursor:pointer" :aria-sort="sortKey === 'package' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Package <span>{{ sortKey === 'package' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('workcenter')" style="cursor:pointer" :aria-sort="sortKey === 'workcenter' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Workcenter <span>{{ sortKey === 'workcenter' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('holdReason')" style="cursor:pointer" :aria-sort="sortKey === 'holdReason' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold Reason <span>{{ sortKey === 'holdReason' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('age')" style="cursor:pointer" :aria-sort="sortKey === 'age' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Age <span>{{ sortKey === 'age' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('holdBy')" style="cursor:pointer" :aria-sort="sortKey === 'holdBy' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold By <span>{{ sortKey === 'holdBy' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('dept')" style="cursor:pointer" :aria-sort="sortKey === 'dept' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Dept <span>{{ sortKey === 'dept' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('holdComment')" style="cursor:pointer" :aria-sort="sortKey === 'holdComment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold Comment <span>{{ sortKey === 'holdComment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th @click="toggleSort('futureHoldComment')" style="cursor:pointer" :aria-sort="sortKey === 'futureHoldComment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Future Hold Comment <span>{{ sortKey === 'futureHoldComment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="12" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="12" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="sortedData.length === 0">
            <td colspan="12" class="placeholder">No data</td>
          </tr>
          <tr v-for="lot in sortedData" v-else :key="lot.lotId">
            <td>{{ lot.lotId || '-' }}</td>
            <td>{{ lot.workorder || '-' }}</td>
            <td>{{ formatNumber(lot.qty) }}</td>
            <td>{{ lot.product || '-' }}</td>
            <td>{{ lot.package || '-' }}</td>
            <td>{{ lot.workcenter || '-' }}</td>
            <td>{{ lot.holdReason || '-' }}</td>
            <td>{{ formatAge(lot.age) }}</td>
            <td>{{ lot.holdBy || '-' }}</td>
            <td>{{ lot.dept || '-' }}</td>
            <td>{{ lot.holdComment || '-' }}</td>
            <td>{{ lot.futureHoldComment || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      :visible="Number(pagination.totalPages || 1) > 1"
      :page="Number(pagination.page || 1)"
      :total-pages="Number(pagination.totalPages || 1)"
      :info-text="pageInfo"
      @prev="emit('prev-page')"
      @next="emit('next-page')"
    />
  </section>
</template>
