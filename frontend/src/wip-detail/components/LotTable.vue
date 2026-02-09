<script setup>
import { computed } from 'vue';

import Pagination from '../../wip-shared/components/Pagination.vue';

const props = defineProps({
  data: {
    type: Object,
    default: () => ({
      lots: [],
      specs: [],
      pagination: { page: 1, page_size: 100, total_count: 0, total_pages: 1 },
    }),
  },
  loading: {
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

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function statusClass(status) {
  const normalized = String(status || 'QUEUE').toLowerCase();
  return `wip-status-${normalized}`;
}

function statusText(lot) {
  if (lot?.wipStatus === 'HOLD' && lot?.holdReason) {
    return `HOLD (${lot.holdReason})`;
  }
  return lot?.wipStatus || 'QUEUE';
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
  const pageSize = Number(pagination.page_size || 100);
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

    <div class="table-container">
      <div v-if="loading" class="placeholder">Loading...</div>
      <div v-else-if="!data.lots || data.lots.length === 0" class="placeholder">No data available</div>
      <table v-else>
        <thead>
          <tr>
            <th class="fixed-col">LOT ID</th>
            <th class="fixed-col">Equipment</th>
            <th class="fixed-col">WIP Status</th>
            <th class="fixed-col">Package</th>
            <th v-for="spec in data.specs" :key="spec" class="spec-col">{{ spec }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in data.lots" :key="lot.lotId">
            <td class="fixed-col">
              <button
                type="button"
                class="lot-id-link"
                :class="{ active: selectedLotId === lot.lotId }"
                @click="emit('select-lot', lot.lotId)"
              >
                {{ lot.lotId || '-' }}
              </button>
            </td>
            <td class="fixed-col">{{ lot.equipment || '-' }}</td>
            <td class="fixed-col" :class="statusClass(lot.wipStatus)">{{ statusText(lot) }}</td>
            <td class="fixed-col">{{ lot.package || '-' }}</td>
            <td
              v-for="spec in data.specs"
              :key="`${lot.lotId}-${spec}`"
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
