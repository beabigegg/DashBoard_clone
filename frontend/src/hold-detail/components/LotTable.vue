<script setup>
import { computed } from 'vue';

import Pagination from '../../wip-shared/components/Pagination.vue';

const props = defineProps({
  lots: {
    type: Array,
    default: () => [],
  },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 50, total: 0, totalPages: 1 }),
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
  const perPage = Number(props.pagination?.perPage || 50);
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
      <div class="table-title">Lot Details</div>
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
            <th>LOTID</th>
            <th>WORKORDER</th>
            <th>QTY</th>
            <th>Product</th>
            <th>Package</th>
            <th>Workcenter</th>
            <th>Spec</th>
            <th>Age</th>
            <th>Hold By</th>
            <th>Dept</th>
            <th>Hold Comment</th>
            <th>Future Hold Comment</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="12" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="12" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="lots.length === 0">
            <td colspan="12" class="placeholder">No data</td>
          </tr>
          <tr v-for="lot in lots" v-else :key="lot.lotId">
            <td>{{ lot.lotId || '-' }}</td>
            <td>{{ lot.workorder || '-' }}</td>
            <td>{{ formatNumber(lot.qty) }}</td>
            <td>{{ lot.product || '-' }}</td>
            <td>{{ lot.package || '-' }}</td>
            <td>{{ lot.workcenter || '-' }}</td>
            <td>{{ lot.spec || '-' }}</td>
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
