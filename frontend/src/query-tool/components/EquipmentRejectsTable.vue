<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next';

import { useSortableTable } from '../../shared-composables/useSortableTable';
import { formatDateTime, parseDateTime } from '../utils/values';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import ExportButton from './ExportButton.vue';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  emptyText: {
    type: String,
    default: '無報廢資料',
  },
  exportDisabled: {
    type: Boolean,
    default: true,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
  truncated: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['export']);

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
  PRODUCTLINENAME: string | null;
  WORKCENTERNAME: string;
  SPECNAME: string;
  LOSSREASONNAME: string;
  EQUIPMENTNAME: string;
  REJECTCOMMENT: string;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  REJECT_QTY: number;
  STANDBY_QTY: number;
  QTYTOPROCESS_QTY: number;
  INPROCESS_QTY: number;
  PROCESSED_QTY: number;
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
    PRODUCTLINENAME: row?.PRODUCTLINENAME != null ? String(row.PRODUCTLINENAME).trim() || null : null,
    WORKCENTERNAME: normalizeText(row?.WORKCENTERNAME),
    SPECNAME: normalizeText(row?.SPECNAME),
    LOSSREASONNAME: normalizeText(row?.LOSSREASONNAME),
    EQUIPMENTNAME: normalizeText(row?.EQUIPMENTNAME),
    REJECTCOMMENT: normalizeText(row?.REJECTCOMMENT || row?.COMMENTS),
    REJECT_TOTAL_QTY: rejectTotalQty,
    DEFECT_QTY: defectQty,
    REJECT_QTY: rejectQty,
    STANDBY_QTY: standbyQty,
    QTYTOPROCESS_QTY: qtyToProcessQty,
    INPROCESS_QTY: inProcessQty,
    PROCESSED_QTY: processedQty,
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
    // TXN_TIME desc
    if (a.TXN_DAY_SORT !== b.TXN_DAY_SORT) {
      return b.TXN_DAY_SORT - a.TXN_DAY_SORT;
    }
    // WORKCENTERNAME asc
    if (a.WORKCENTERNAME !== b.WORKCENTERNAME) {
      return a.WORKCENTERNAME.localeCompare(b.WORKCENTERNAME, 'zh-Hant');
    }
    // REJECT_TOTAL_QTY desc
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
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">報廢紀錄（明細）</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出報廢紀錄"
        @click="emit('export')"
      />
    </div>

    <div v-if="error" class="bg-red-50 border border-red-200 text-red-800 px-3 py-2 rounded text-sm mb-2" role="alert">{{ error }}</div>

    <div v-if="truncated" class="bg-yellow-50 border border-yellow-300 text-yellow-800 px-3 py-2 rounded text-sm mb-2" role="status">
      資料已截斷，僅顯示部分結果。請縮小查詢範圍以取得完整資料。
    </div>

    <BlockLoadingState v-if="loading" />

    <div v-else-if="displayRows.length === 0" class="placeholder">
      {{ emptyText }}
    </div>

    <div v-else class="query-tool-table-wrap">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('CONTAINERNAME')" @click="toggleSort('CONTAINERNAME')" @keydown.enter.space.prevent="toggleSort('CONTAINERNAME')"><span class="qt-th-inner">批次ID <component :is="sortIcon('CONTAINERNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'CONTAINERNAME' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('PRODUCTLINENAME')" @click="toggleSort('PRODUCTLINENAME')" @keydown.enter.space.prevent="toggleSort('PRODUCTLINENAME')"><span class="qt-th-inner">Package <component :is="sortIcon('PRODUCTLINENAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PRODUCTLINENAME' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('WORKCENTERNAME')" @click="toggleSort('WORKCENTERNAME')" @keydown.enter.space.prevent="toggleSort('WORKCENTERNAME')"><span class="qt-th-inner">站點 <component :is="sortIcon('WORKCENTERNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'WORKCENTERNAME' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('SPECNAME')" @click="toggleSort('SPECNAME')" @keydown.enter.space.prevent="toggleSort('SPECNAME')"><span class="qt-th-inner">製程規格 <component :is="sortIcon('SPECNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'SPECNAME' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('LOSSREASONNAME')" @click="toggleSort('LOSSREASONNAME')" @keydown.enter.space.prevent="toggleSort('LOSSREASONNAME')"><span class="qt-th-inner">報廢原因 <component :is="sortIcon('LOSSREASONNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'LOSSREASONNAME' }" :size="13" /></span></th>
            <th
              class="sortable-th"
              tabindex="0"
              :aria-sort="ariaSortFor('REJECT_TOTAL_QTY')"
              @click.exact="toggleSort('REJECT_TOTAL_QTY')"
              @keydown.enter.space.prevent="toggleSort('REJECT_TOTAL_QTY')"
            >
              <span class="qt-th-inner">扣帳報廢量 <component :is="sortIcon('REJECT_TOTAL_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECT_TOTAL_QTY' }" :size="13" /></span>
              <button class="expand-toggle" type="button" :aria-label="showRejectBreakdown ? '收合報廢細項' : '展開報廢細項'" @click.stop="showRejectBreakdown = !showRejectBreakdown" @keydown.enter.space.prevent.stop="showRejectBreakdown = !showRejectBreakdown">{{ showRejectBreakdown ? '▾' : '▸' }}</button>
            </th>
            <template v-if="showRejectBreakdown">
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('REJECT_QTY')" @click="toggleSort('REJECT_QTY')" @keydown.enter.space.prevent="toggleSort('REJECT_QTY')"><span class="qt-th-inner">REJECT <component :is="sortIcon('REJECT_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECT_QTY' }" :size="13" /></span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('STANDBY_QTY')" @click="toggleSort('STANDBY_QTY')" @keydown.enter.space.prevent="toggleSort('STANDBY_QTY')"><span class="qt-th-inner">STANDBY <component :is="sortIcon('STANDBY_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'STANDBY_QTY' }" :size="13" /></span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('QTYTOPROCESS_QTY')" @click="toggleSort('QTYTOPROCESS_QTY')" @keydown.enter.space.prevent="toggleSort('QTYTOPROCESS_QTY')"><span class="qt-th-inner">QTYTOPROCESS <component :is="sortIcon('QTYTOPROCESS_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'QTYTOPROCESS_QTY' }" :size="13" /></span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('INPROCESS_QTY')" @click="toggleSort('INPROCESS_QTY')" @keydown.enter.space.prevent="toggleSort('INPROCESS_QTY')"><span class="qt-th-inner">INPROCESS <component :is="sortIcon('INPROCESS_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'INPROCESS_QTY' }" :size="13" /></span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('PROCESSED_QTY')" @click="toggleSort('PROCESSED_QTY')" @keydown.enter.space.prevent="toggleSort('PROCESSED_QTY')"><span class="qt-th-inner">PROCESSED <component :is="sortIcon('PROCESSED_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'PROCESSED_QTY' }" :size="13" /></span></th>
            </template>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('DEFECT_QTY')" @click="toggleSort('DEFECT_QTY')" @keydown.enter.space.prevent="toggleSort('DEFECT_QTY')"><span class="qt-th-inner">不扣帳報廢量 <component :is="sortIcon('DEFECT_QTY')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'DEFECT_QTY' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('REJECTCOMMENT')" @click="toggleSort('REJECTCOMMENT')" @keydown.enter.space.prevent="toggleSort('REJECTCOMMENT')"><span class="qt-th-inner">備註 <component :is="sortIcon('REJECTCOMMENT')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'REJECTCOMMENT' }" :size="13" /></span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('EQUIPMENTNAME')" @click="toggleSort('EQUIPMENTNAME')" @keydown.enter.space.prevent="toggleSort('EQUIPMENTNAME')">
              <span class="qt-th-inner">報廢登錄設備 <span class="cross-station-note" title="此設備為報廢事件登錄的設備，可能與查詢設備不同（跨站報廢）">(可能不同於查詢設備)</span> <component :is="sortIcon('EQUIPMENTNAME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'EQUIPMENTNAME' }" :size="13" /></span>
            </th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('TXN_TIME')" @click="toggleSort('TXN_TIME')" @keydown.enter.space.prevent="toggleSort('TXN_TIME')"><span class="qt-th-inner">報廢時間 <component :is="sortIcon('TXN_TIME')" class="qt-sort-icon" :class="{ 'qt-sort-icon--active': sortKey === 'TXN_TIME' }" :size="13" /></span></th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, idx) in displayRows"
            :key="`${row.TXN_TIME_RAW}-${row.CONTAINERNAME}-${row.LOSSREASONNAME}-${idx}`"
          >
            <td>{{ row.CONTAINERNAME }}</td>
            <td>{{ row.PRODUCTLINENAME || '-' }}</td>
            <td>{{ row.WORKCENTERNAME || '-' }}</td>
            <td>{{ row.SPECNAME || '-' }}</td>
            <td>{{ row.LOSSREASONNAME || '-' }}</td>
            <td>{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
            <template v-if="showRejectBreakdown">
              <td>{{ formatNumber(row.REJECT_QTY) }}</td>
              <td>{{ formatNumber(row.STANDBY_QTY) }}</td>
              <td>{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.INPROCESS_QTY) }}</td>
              <td>{{ formatNumber(row.PROCESSED_QTY) }}</td>
            </template>
            <td>{{ formatNumber(row.DEFECT_QTY) }}</td>
            <td>{{ row.REJECTCOMMENT || '-' }}</td>
            <td>{{ row.EQUIPMENTNAME || '-' }}</td>
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

.cross-station-note {
  font-size: 0.75em;
  font-weight: normal;
  opacity: 0.7;
  margin-left: 4px;
  white-space: nowrap;
}

</style>
