<script setup>
import { computed, ref } from 'vue';

const props = defineProps({
  lots: {
    type: Array,
    default: () => [],
  },
  activeFilter: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['clear-filter']);

const sortKey = ref('wait_hours');
const sortDirection = ref('desc');

const BUCKET_LABELS = {
  lt_6h: '<6hr',
  '6h_12h': '6-12hr',
  '12h_24h': '12-24hr',
  gt_24h: '>24hr',
};

const HEADERS = [
  { key: 'lot_id', label: 'LOT ID' },
  { key: 'package', label: 'Package' },
  { key: 'product', label: 'Product' },
  { key: 'qty', label: 'QTY' },
  { key: 'step', label: '站點' },
  { key: 'workorder', label: 'Workorder' },
  { key: 'move_in_time', label: 'Move In' },
  { key: 'wait_hours', label: 'Wait (hr)' },
  { key: 'bucket', label: '區間' },
  { key: 'status', label: '狀態' },
];

function normalizeForSort(value, key) {
  if (key === 'qty' || key === 'wait_hours') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (value == null) {
    return '';
  }
  return String(value).toUpperCase();
}

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    return;
  }
  sortKey.value = key;
  sortDirection.value = key === 'wait_hours' ? 'desc' : 'asc';
}

const sortedLots = computed(() => {
  const rows = Array.isArray(props.lots) ? [...props.lots] : [];
  const direction = sortDirection.value === 'asc' ? 1 : -1;
  const key = sortKey.value;

  rows.sort((left, right) => {
    const leftValue = normalizeForSort(left?.[key], key);
    const rightValue = normalizeForSort(right?.[key], key);
    if (leftValue < rightValue) return -1 * direction;
    if (leftValue > rightValue) return 1 * direction;
    return 0;
  });

  return rows;
});

function formatValue(value, fallback = '-') {
  if (value == null || value === '') {
    return fallback;
  }
  return String(value);
}

function formatQty(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '-';
  }
  return parsed.toLocaleString('zh-TW');
}

function formatWait(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '-';
  }
  return parsed.toFixed(1);
}

function formatTime(value) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
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

function bucketLabel(value) {
  return BUCKET_LABELS[value] || value || '-';
}

function bucketClass(value) {
  return `bucket-${String(value || '').replace(/[^a-z0-9]+/gi, '-')}`;
}

function currentSortLabel(columnKey) {
  if (sortKey.value !== columnKey) {
    return '';
  }
  return sortDirection.value === 'asc' ? '▲' : '▼';
}
</script>

<template>
  <div class="lot-table-wrap">
    <div v-if="activeFilter" class="filter-chip" @click="emit('clear-filter')">
      已套用圖表篩選，點擊清除
    </div>

    <div class="lot-table-scroll">
      <table class="lot-table">
        <thead>
          <tr>
            <th v-for="header in HEADERS" :key="header.key">
              <button
                type="button"
                class="sort-button"
                @click="toggleSort(header.key)"
              >
                {{ header.label }}
                <span class="sort-indicator">{{ currentSortLabel(header.key) }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in sortedLots" :key="`${lot.lot_id}-${lot.step}-${lot.move_in_time}`">
            <td>{{ formatValue(lot.lot_id) }}</td>
            <td>{{ formatValue(lot.package) }}</td>
            <td>{{ formatValue(lot.product) }}</td>
            <td class="cell-number">{{ formatQty(lot.qty) }}</td>
            <td>{{ formatValue(lot.step) }}</td>
            <td>{{ formatValue(lot.workorder) }}</td>
            <td>{{ formatTime(lot.move_in_time) }}</td>
            <td class="cell-number">{{ formatWait(lot.wait_hours) }}</td>
            <td>
              <span class="bucket-pill" :class="bucketClass(lot.bucket)">
                {{ bucketLabel(lot.bucket) }}
              </span>
            </td>
            <td>{{ formatValue(lot.status) }}</td>
          </tr>
          <tr v-if="sortedLots.length === 0">
            <td class="table-empty" :colspan="HEADERS.length">目前無符合條件的 LOT</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
