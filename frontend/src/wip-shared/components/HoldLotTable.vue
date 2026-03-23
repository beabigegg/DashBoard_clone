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
  paginating: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: 'Hold Lot Details',
  },
});

const emit = defineEmits(['clear-filters', 'prev-page', 'next-page']);
const lotsRef = computed(() => props.lots);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(lotsRef);

function currentSortLabel(key) {
  if (sortKey.value !== key) {
    return '⇕';
  }
  return sortDirection.value === 'asc' ? '▲' : '▼';
}

function ariaSortFor(key) {
  if (sortKey.value !== key) {
    return 'none';
  }
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

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
      <div class="table-title">{{ title }}</div>
      <div v-if="hasActiveFilters" class="filter-indicator">
        <span>篩選: {{ filterText }}</span>
        <span class="clear-btn" @click="emit('clear-filters')">×</span>
      </div>
      <div class="table-info">{{ tableInfo }}</div>
    </div>

    <div class="table-container" :class="{ paginating: paginating }">
      <table class="lot-table">
        <thead>
          <tr>
            <th class="cursor-pointer" @click="toggleSort('lotId')" :aria-sort="ariaSortFor('lotId')">LOTID <span>{{ currentSortLabel('lotId') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('workorder')" :aria-sort="ariaSortFor('workorder')">WORKORDER <span>{{ currentSortLabel('workorder') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('qty')" :aria-sort="ariaSortFor('qty')">QTY <span>{{ currentSortLabel('qty') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('product')" :aria-sort="ariaSortFor('product')">Product <span>{{ currentSortLabel('product') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('package')" :aria-sort="ariaSortFor('package')">Package <span>{{ currentSortLabel('package') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('workcenter')" :aria-sort="ariaSortFor('workcenter')">Workcenter <span>{{ currentSortLabel('workcenter') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdReason')" :aria-sort="ariaSortFor('holdReason')">Hold Reason <span>{{ currentSortLabel('holdReason') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('spec')" :aria-sort="ariaSortFor('spec')">Spec <span>{{ currentSortLabel('spec') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('age')" :aria-sort="ariaSortFor('age')">Age <span>{{ currentSortLabel('age') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdBy')" :aria-sort="ariaSortFor('holdBy')">Hold By <span>{{ currentSortLabel('holdBy') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('dept')" :aria-sort="ariaSortFor('dept')">Dept <span>{{ currentSortLabel('dept') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdComment')" :aria-sort="ariaSortFor('holdComment')">Hold Comment <span>{{ currentSortLabel('holdComment') }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('futureHoldComment')" :aria-sort="ariaSortFor('futureHoldComment')">Future Hold Comment <span>{{ currentSortLabel('futureHoldComment') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="13" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="13" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="sortedData.length === 0">
            <td colspan="13" class="placeholder">No data</td>
          </tr>
          <tr v-for="lot in sortedData" v-else :key="lot.lotId">
            <td>{{ lot.lotId || '-' }}</td>
            <td>{{ lot.workorder || '-' }}</td>
            <td>{{ formatNumber(lot.qty) }}</td>
            <td>{{ lot.product || '-' }}</td>
            <td>{{ lot.package || '-' }}</td>
            <td>{{ lot.workcenter || '-' }}</td>
            <td>{{ lot.holdReason || '-' }}</td>
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
