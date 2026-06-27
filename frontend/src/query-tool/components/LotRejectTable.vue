<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next';

import { useSortableTable } from '../../shared-composables/useSortableTable';
import { formatDateTime, parseDateTime } from '../utils/values';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyText: {
    type: String,
    default: '無報廢資料',
  },
});

const showRejectBreakdown = ref(false);

function toNumber(value: unknown, defaultValue = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : defaultValue;
}

function formatNumber(value: unknown): string {
  return toNumber(value).toLocaleString('zh-TW');
}

function normalizeText(value: unknown, fallback = ''): string {
  const text = String(value || '').trim();
  return text || fallback;
}

interface NormalizedRejectRow extends Record<string, unknown> {
  CONTAINERNAME: string;
  WORKCENTERNAME: string;
  PRODUCTLINENAME: string;
  PJ_FUNCTION: string;
  PJ_TYPE: string;
  PRODUCTNAME: string;
  LOSSREASONNAME: string;
  EQUIPMENTNAME: string;
  REJECTCOMMENT: string;
  REJECT_TOTAL_QTY: number;
  REJECT_QTY: number;
  STANDBY_QTY: number;
  QTYTOPROCESS_QTY: number;
  INPROCESS_QTY: number;
  PROCESSED_QTY: number;
  DEFECT_QTY: number;
  TXN_TIME_RAW: unknown;
  TXN_TIME: string;
  TXN_DAY_SORT: number;
  WORKCENTERSEQUENCE_GROUP: number;
}

function normalizeRejectRow(rawRow: unknown): NormalizedRejectRow {
  const row = rawRow as Record<string, unknown>;
  const rejectQty = toNumber(row?.REJECT_QTY ?? row?.REJECTQTY);
  const standbyQty = toNumber(row?.STANDBY_QTY ?? row?.STANDBYQTY);
  const qtyToProcessQty = toNumber(row?.QTYTOPROCESS_QTY ?? row?.QTYTOPROCESS);
  const inProcessQty = toNumber(row?.INPROCESS_QTY ?? row?.INPROCESSQTY);
  const processedQty = toNumber(row?.PROCESSED_QTY ?? row?.PROCESSEDQTY);

  const computedRejectTotal = rejectQty + standbyQty + qtyToProcessQty + inProcessQty + processedQty;
  const rejectTotalQty = toNumber(row?.REJECT_TOTAL_QTY, computedRejectTotal);
  const defectQty = toNumber(row?.DEFECT_QTY);

  const txnTimeRaw = row?.TXN_TIME || row?.TXNDATE || row?.TXN_DAY || '';
  const txnDate = parseDateTime(txnTimeRaw);

  return {
    CONTAINERNAME: normalizeText(row?.CONTAINERNAME, normalizeText(row?.CONTAINERID)),
    WORKCENTERNAME: normalizeText(row?.WORKCENTERNAME),
    PRODUCTLINENAME: normalizeText(row?.PRODUCTLINENAME),
    PJ_FUNCTION: normalizeText(row?.PJ_FUNCTION),
    PJ_TYPE: normalizeText(row?.PJ_TYPE),
    PRODUCTNAME: normalizeText(row?.PRODUCTNAME),
    LOSSREASONNAME: normalizeText(row?.LOSSREASONNAME),
    EQUIPMENTNAME: normalizeText(row?.EQUIPMENTNAME),
    REJECTCOMMENT: normalizeText(row?.REJECTCOMMENT || row?.COMMENTS),
    REJECT_TOTAL_QTY: rejectTotalQty,
    REJECT_QTY: rejectQty,
    STANDBY_QTY: standbyQty,
    QTYTOPROCESS_QTY: qtyToProcessQty,
    INPROCESS_QTY: inProcessQty,
    PROCESSED_QTY: processedQty,
    DEFECT_QTY: defectQty,
    TXN_TIME_RAW: txnTimeRaw,
    TXN_TIME: txnDate ? formatDateTime(txnDate) : normalizeText(txnTimeRaw),
    TXN_DAY_SORT: txnDate ? txnDate.getTime() : 0,
    WORKCENTERSEQUENCE_GROUP: toNumber(row?.WORKCENTERSEQUENCE_GROUP, 999),
  };
}

const normalizedRows = computed(() => {
  return (props.rows || []).map(normalizeRejectRow);
});

const defaultSorted = computed(() => {
  return [...normalizedRows.value].sort((a: NormalizedRejectRow, b: NormalizedRejectRow) => {
    if (a.TXN_DAY_SORT !== b.TXN_DAY_SORT) {
      return b.TXN_DAY_SORT - a.TXN_DAY_SORT;
    }
    if (a.WORKCENTERSEQUENCE_GROUP !== b.WORKCENTERSEQUENCE_GROUP) {
      return a.WORKCENTERSEQUENCE_GROUP - b.WORKCENTERSEQUENCE_GROUP;
    }
    if (a.WORKCENTERNAME !== b.WORKCENTERNAME) {
      return a.WORKCENTERNAME.localeCompare(b.WORKCENTERNAME, 'zh-Hant');
    }
    if (a.REJECT_TOTAL_QTY !== b.REJECT_TOTAL_QTY) {
      return b.REJECT_TOTAL_QTY - a.REJECT_TOTAL_QTY;
    }
    return a.CONTAINERNAME.localeCompare(b.CONTAINERNAME, 'zh-Hant');
  });
});

const { sortKey, sortDirection, sortedData: displayRows, toggleSort } = useSortableTable(defaultSorted);

function sortIcon(key: string) {
  if (sortKey.value !== key) return ArrowUpDown;
  return sortDirection.value === 'asc' ? ArrowUp : ArrowDown;
}

function ariaSortFor(key: string): 'none' | 'ascending' | 'descending' {
  if (sortKey.value !== key) return 'none';
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}
</script>

<template>
  <div>
    <BlockLoadingState v-if="loading" />

    <div v-else-if="displayRows.length === 0" class="placeholder">
      {{ emptyText }}
    </div>

    <div v-else class="query-tool-table-wrap">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th class="sortable-th" :aria-sort="ariaSortFor('CONTAINERNAME')" @click="toggleSort('CONTAINERNAME')">LOT ID <component :is="sortIcon('CONTAINERNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'CONTAINERNAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('WORKCENTERNAME')" @click="toggleSort('WORKCENTERNAME')">WORKCENTER <component :is="sortIcon('WORKCENTERNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'WORKCENTERNAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('PRODUCTLINENAME')" @click="toggleSort('PRODUCTLINENAME')">Package <component :is="sortIcon('PRODUCTLINENAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PRODUCTLINENAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('PJ_FUNCTION')" @click="toggleSort('PJ_FUNCTION')">FUNCTION <component :is="sortIcon('PJ_FUNCTION')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PJ_FUNCTION' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('PJ_TYPE')" @click="toggleSort('PJ_TYPE')">TYPE <component :is="sortIcon('PJ_TYPE')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PJ_TYPE' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('PRODUCTNAME')" @click="toggleSort('PRODUCTNAME')">PRODUCT <component :is="sortIcon('PRODUCTNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PRODUCTNAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('LOSSREASONNAME')" @click="toggleSort('LOSSREASONNAME')">原因 <component :is="sortIcon('LOSSREASONNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'LOSSREASONNAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('EQUIPMENTNAME')" @click="toggleSort('EQUIPMENTNAME')">EQUIPMENT <component :is="sortIcon('EQUIPMENTNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'EQUIPMENTNAME' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('REJECTCOMMENT')" @click="toggleSort('REJECTCOMMENT')">COMMENT <component :is="sortIcon('REJECTCOMMENT')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECTCOMMENT' }" :size="13" /></th>
            <th
              class="sortable-th"
              :aria-sort="ariaSortFor('REJECT_TOTAL_QTY')"
              @click.exact="toggleSort('REJECT_TOTAL_QTY')"
            >
              扣帳報廢量 <component :is="sortIcon('REJECT_TOTAL_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECT_TOTAL_QTY' }" :size="13" />
              <span class="expand-toggle" @click.stop="showRejectBreakdown = !showRejectBreakdown">{{ showRejectBreakdown ? '▾' : '▸' }}</span>
            </th>
            <template v-if="showRejectBreakdown">
              <th class="sortable-th" :aria-sort="ariaSortFor('REJECT_QTY')" @click="toggleSort('REJECT_QTY')">REJECT <component :is="sortIcon('REJECT_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECT_QTY' }" :size="13" /></th>
              <th class="sortable-th" :aria-sort="ariaSortFor('STANDBY_QTY')" @click="toggleSort('STANDBY_QTY')">STANDBY <component :is="sortIcon('STANDBY_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'STANDBY_QTY' }" :size="13" /></th>
              <th class="sortable-th" :aria-sort="ariaSortFor('QTYTOPROCESS_QTY')" @click="toggleSort('QTYTOPROCESS_QTY')">QTYTOPROCESS <component :is="sortIcon('QTYTOPROCESS_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'QTYTOPROCESS_QTY' }" :size="13" /></th>
              <th class="sortable-th" :aria-sort="ariaSortFor('INPROCESS_QTY')" @click="toggleSort('INPROCESS_QTY')">INPROCESS <component :is="sortIcon('INPROCESS_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'INPROCESS_QTY' }" :size="13" /></th>
              <th class="sortable-th" :aria-sort="ariaSortFor('PROCESSED_QTY')" @click="toggleSort('PROCESSED_QTY')">PROCESSED <component :is="sortIcon('PROCESSED_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PROCESSED_QTY' }" :size="13" /></th>
            </template>
            <th class="sortable-th" :aria-sort="ariaSortFor('DEFECT_QTY')" @click="toggleSort('DEFECT_QTY')">不扣帳報廢量 <component :is="sortIcon('DEFECT_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'DEFECT_QTY' }" :size="13" /></th>
            <th class="sortable-th" :aria-sort="ariaSortFor('TXN_TIME')" @click="toggleSort('TXN_TIME')">報廢時間 <component :is="sortIcon('TXN_TIME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'TXN_TIME' }" :size="13" /></th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, idx) in displayRows"
            :key="`${row.TXN_TIME_RAW}-${row.CONTAINERNAME}-${row.LOSSREASONNAME}-${idx}`"
          >
            <td>{{ row.CONTAINERNAME }}</td>
            <td>{{ row.WORKCENTERNAME || '-' }}</td>
            <td>{{ row.PRODUCTLINENAME || '-' }}</td>
            <td>{{ row.PJ_FUNCTION || '-' }}</td>
            <td>{{ row.PJ_TYPE || '-' }}</td>
            <td>{{ row.PRODUCTNAME || '-' }}</td>
            <td>{{ row.LOSSREASONNAME || '-' }}</td>
            <td>{{ row.EQUIPMENTNAME || '-' }}</td>
            <td>{{ row.REJECTCOMMENT || '-' }}</td>
            <td>{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
            <template v-if="showRejectBreakdown">
              <td>{{ formatNumber(row.REJECT_QTY) }}</td>
              <td>{{ formatNumber(row.STANDBY_QTY) }}</td>
              <td>{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.INPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.PROCESSED_QTY) }}</td>
            </template>
            <td>{{ formatNumber(row.DEFECT_QTY) }}</td>
            <td>{{ row.TXN_TIME || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.expand-toggle {
  cursor: pointer;
  margin-left: 4px;
  opacity: 0.6;
}

.expand-toggle:hover {
  opacity: 1;
}
</style>
