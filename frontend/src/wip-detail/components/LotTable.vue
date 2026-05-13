<script setup lang="ts">
import { computed } from 'vue';
import { useSortableTable } from '../../shared-composables/useSortableTable';

import Pagination from '../../shared-ui/components/PaginationControl.vue';

const props = defineProps({
  data: {
    type: Object,
    default: () => ({
      lots: [],
      specs: [],
      pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 1 },
    }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  paginating: {
    type: Boolean,
    default: false,
  },
  activeStatus: {
    type: String,
    default: null,
  },
  selectedLotId: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['select-lot', 'prev-page', 'next-page']);

type LotRow = {
  lotId?: unknown;
  wipStatus?: unknown;
  holdReason?: unknown;
  equipment?: unknown;
  package?: unknown;
  spec?: unknown;
  qty?: unknown;
  [key: string]: unknown;
};

const lotsRef = computed<LotRow[]>(() => (props.data.lots || []) as LotRow[]);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(lotsRef);

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function statusClass(status: unknown): string {
  const normalized = String(status || 'QUEUE').toLowerCase();
  return `wip-status-${normalized}`;
}

function lotKey(lot: LotRow): string {
  return String(lot.lotId ?? '');
}

function statusText(lot: Record<string, unknown>): string {
  if (lot?.wipStatus === 'HOLD' && lot?.holdReason) {
    return `HOLD (${lot.holdReason})`;
  }
  return String(lot?.wipStatus || 'QUEUE');
}

const tableTitle = computed(() => {
  if (!props.activeStatus) {
    return 'Lot Details';
  }

  if (props.activeStatus === 'quality-hold') {
    return 'Lot Details - 品質異常 Hold Only';
  }
  if (props.activeStatus === 'non-quality-hold') {
    return 'Lot Details - 非品質異常 Hold Only';
  }

  return `Lot Details - ${props.activeStatus.toUpperCase()} Only`;
});

const tableInfo = computed(() => {
  const pagination = props.data.pagination || {};
  const total = Number(pagination.total_count || 0);

  if (total <= 0) {
    return 'No data';
  }

  const page = Number(pagination.page || 1);
  const pageSize = Number(pagination.page_size || 20);
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `Showing ${start} - ${end} of ${formatNumber(total)}`;
});

const pageInfo = computed(() => {
  const pagination = props.data.pagination || {};
  return `Page ${pagination.page || 1} / ${pagination.total_pages || 1}`;
});
</script>

<template>
  <section class="table-section">
    <div class="table-header">
      <div class="table-title">{{ tableTitle }}</div>
      <div class="table-info">{{ tableInfo }}</div>
    </div>

    <div class="table-container" :class="{ paginating: paginating }">
      <div v-if="loading" class="placeholder">Loading...</div>
      <div v-else-if="!sortedData || sortedData.length === 0" class="placeholder">No data available</div>
      <table v-else>
        <thead>
          <tr>
            <th class="fixed-col cursor-pointer" @click="toggleSort('lotId')" :aria-sort="sortKey === 'lotId' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">LOT ID <span>{{ sortKey === 'lotId' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="fixed-col cursor-pointer" @click="toggleSort('equipment')" :aria-sort="sortKey === 'equipment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Equipment <span>{{ sortKey === 'equipment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="fixed-col cursor-pointer" @click="toggleSort('wipStatus')" :aria-sort="sortKey === 'wipStatus' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">WIP Status <span>{{ sortKey === 'wipStatus' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="fixed-col cursor-pointer" @click="toggleSort('package')" :aria-sort="sortKey === 'package' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Package <span>{{ sortKey === 'package' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th v-for="spec in data.specs" :key="spec" class="spec-col">{{ spec }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in sortedData" :key="lotKey(lot)">
            <td class="fixed-col">
              <button
                type="button"
                class="lot-id-link"
                :class="{ active: selectedLotId === String(lot.lotId ?? '') }"
                @click="emit('select-lot', String(lot.lotId ?? ''))"
              >
                {{ lot.lotId || '-' }}
              </button>
            </td>
            <td class="fixed-col">{{ lot.equipment || '-' }}</td>
            <td class="fixed-col" :class="statusClass(lot.wipStatus)">{{ statusText(lot) }}</td>
            <td class="fixed-col">{{ lot.package || '-' }}</td>
            <td
              v-for="spec in data.specs"
              :key="`${lotKey(lot)}-${spec}`"
              class="spec-cell"
              :class="{ 'has-data': lot.spec === spec }"
            >
              <template v-if="lot.spec === spec">{{ formatNumber(lot.qty) }}</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      :visible="Number(data.pagination?.total_pages || 1) > 1"
      :page="Number(data.pagination?.page || 1)"
      :total-pages="Number(data.pagination?.total_pages || 1)"
      :info-text="pageInfo"
      @prev="emit('prev-page')"
      @next="emit('next-page')"
    />
  </section>
</template>
