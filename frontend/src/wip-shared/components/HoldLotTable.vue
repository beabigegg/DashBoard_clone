<script setup lang="ts">
import { computed } from 'vue';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next';
import { useSortableTable } from '../../shared-composables/useSortableTable';
import type { DataRow } from '../../shared-composables/useSortableTable';

import Pagination from '../../shared-ui/components/PaginationControl.vue';

const props = defineProps<{
  lots?: DataRow[];
  pagination?: { page: number; perPage: number; total: number; totalPages: number };
  loading?: boolean;
  errorMessage?: string;
  hasActiveFilters?: boolean;
  filterText?: string;
  paginating?: boolean;
  title?: string;
}>();

const emit = defineEmits(['clear-filters', 'prev-page', 'next-page']);
const lotsRef = computed((): DataRow[] => props.lots ?? []);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(lotsRef);

function sortIconFor(key: string) {
  if (sortKey.value !== key) return ArrowUpDown;
  return sortDirection.value === 'asc' ? ArrowUp : ArrowDown;
}

function ariaSortFor(key: string): 'none' | 'ascending' | 'descending' {
  if (sortKey.value !== key) {
    return 'none';
  }
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function formatAge(value: unknown): string {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return `${value}天`;
}

function formatHoldTime(value: unknown): string {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  const match = String(value).match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/);
  return match ? `${match[1]} ${match[2]}` : String(value);
}

function formatHoldDuration(value: unknown): string {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  const totalHours = Number(value);
  if (!Number.isFinite(totalHours) || totalHours < 0) {
    return '-';
  }
  const days = Math.floor(totalHours / 24);
  const hours = Math.floor(totalHours % 24);
  if (days > 0) {
    return hours > 0 ? `${days}天${hours}小時` : `${days}天`;
  }
  if (hours > 0) {
    return `${hours}小時`;
  }
  const minutes = Math.round((totalHours * 60) % 60);
  return minutes > 0 ? `${minutes}分` : '<1分';
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
      <div class="table-title">{{ title ?? 'Hold Lot Details' }}</div>
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
            <th class="sortable-th" @click="toggleSort('lotId')" :aria-sort="ariaSortFor('lotId')"><span class="th-sort-inner">LOTID <component :is="sortIconFor('lotId')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'lotId' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('workorder')" :aria-sort="ariaSortFor('workorder')"><span class="th-sort-inner">WORKORDER <component :is="sortIconFor('workorder')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'workorder' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('qty')" :aria-sort="ariaSortFor('qty')"><span class="th-sort-inner">QTY <component :is="sortIconFor('qty')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'qty' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('product')" :aria-sort="ariaSortFor('product')"><span class="th-sort-inner">Product <component :is="sortIconFor('product')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'product' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('package')" :aria-sort="ariaSortFor('package')"><span class="th-sort-inner">Package <component :is="sortIconFor('package')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'package' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('workcenter')" :aria-sort="ariaSortFor('workcenter')"><span class="th-sort-inner">Workcenter <component :is="sortIconFor('workcenter')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'workcenter' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('holdReason')" :aria-sort="ariaSortFor('holdReason')"><span class="th-sort-inner">Hold Reason <component :is="sortIconFor('holdReason')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'holdReason' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('spec')" :aria-sort="ariaSortFor('spec')"><span class="th-sort-inner">Spec <component :is="sortIconFor('spec')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'spec' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('age')" :aria-sort="ariaSortFor('age')"><span class="th-sort-inner">Age <component :is="sortIconFor('age')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'age' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('holdTime')" :aria-sort="ariaSortFor('holdTime')"><span class="th-sort-inner">Hold Time <component :is="sortIconFor('holdTime')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'holdTime' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('holdDurationHours')" :aria-sort="ariaSortFor('holdDurationHours')"><span class="th-sort-inner">Hold Duration <component :is="sortIconFor('holdDurationHours')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'holdDurationHours' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('holdBy')" :aria-sort="ariaSortFor('holdBy')"><span class="th-sort-inner">Hold By <component :is="sortIconFor('holdBy')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'holdBy' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('dept')" :aria-sort="ariaSortFor('dept')"><span class="th-sort-inner">Dept <component :is="sortIconFor('dept')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'dept' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('holdComment')" :aria-sort="ariaSortFor('holdComment')"><span class="th-sort-inner">Hold Comment <component :is="sortIconFor('holdComment')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'holdComment' }" :size="13" /></span></th>
            <th class="sortable-th" @click="toggleSort('futureHoldComment')" :aria-sort="ariaSortFor('futureHoldComment')"><span class="th-sort-inner">Future Hold Comment <component :is="sortIconFor('futureHoldComment')" class="sort-icon" :class="{ 'sort-icon--active': sortKey === 'futureHoldComment' }" :size="13" /></span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="15" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="15" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="sortedData.length === 0">
            <td colspan="15" class="placeholder">No data</td>
          </tr>
          <tr v-for="lot in sortedData" v-else :key="lot.lotId as string">
            <td>{{ lot.lotId || '-' }}</td>
            <td>{{ lot.workorder || '-' }}</td>
            <td>{{ formatNumber(lot.qty) }}</td>
            <td>{{ lot.product || '-' }}</td>
            <td>{{ lot.package || '-' }}</td>
            <td>{{ lot.workcenter || '-' }}</td>
            <td>{{ lot.holdReason || '-' }}</td>
            <td>{{ lot.spec || '-' }}</td>
            <td>{{ formatAge(lot.age) }}</td>
            <td>{{ formatHoldTime(lot.holdTime) }}</td>
            <td>{{ formatHoldDuration(lot.holdDurationHours) }}</td>
            <td>{{ lot.holdBy || '-' }}</td>
            <td>{{ lot.dept || '-' }}</td>
            <td>{{ lot.holdComment || '-' }}</td>
            <td>{{ lot.futureHoldComment || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      :visible="Number(pagination?.totalPages || 1) > 1"
      :page="Number(pagination?.page || 1)"
      :total-pages="Number(pagination?.totalPages || 1)"
      :info-text="pageInfo"
      @prev="emit('prev-page')"
      @next="emit('next-page')"
    />
  </section>
</template>
