<script setup lang="ts">
import { computed, ref } from 'vue';

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

function sortLabel(key: string): string {
  if (sortKey.value !== key) return '⇕';
  return sortDirection.value === 'asc' ? '▲' : '▼';
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
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('CONTAINERNAME')" @click="toggleSort('CONTAINERNAME')" @keydown.enter.space.prevent="toggleSort('CONTAINERNAME')">批次ID <span class="sort-indicator">{{ sortLabel('CONTAINERNAME') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('PRODUCTLINENAME')" @click="toggleSort('PRODUCTLINENAME')" @keydown.enter.space.prevent="toggleSort('PRODUCTLINENAME')">Package <span class="sort-indicator">{{ sortLabel('PRODUCTLINENAME') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('WORKCENTERNAME')" @click="toggleSort('WORKCENTERNAME')" @keydown.enter.space.prevent="toggleSort('WORKCENTERNAME')">站點 <span class="sort-indicator">{{ sortLabel('WORKCENTERNAME') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('SPECNAME')" @click="toggleSort('SPECNAME')" @keydown.enter.space.prevent="toggleSort('SPECNAME')">製程規格 <span class="sort-indicator">{{ sortLabel('SPECNAME') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('LOSSREASONNAME')" @click="toggleSort('LOSSREASONNAME')" @keydown.enter.space.prevent="toggleSort('LOSSREASONNAME')">報廢原因 <span class="sort-indicator">{{ sortLabel('LOSSREASONNAME') }}</span></th>
            <th
              class="sortable-th"
              tabindex="0"
              :aria-sort="ariaSortFor('REJECT_TOTAL_QTY')"
              @click.exact="toggleSort('REJECT_TOTAL_QTY')"
              @keydown.enter.space.prevent="toggleSort('REJECT_TOTAL_QTY')"
            >
              總報廢量 <span class="sort-indicator">{{ sortLabel('REJECT_TOTAL_QTY') }}</span>
              <button class="expand-toggle" type="button" :aria-label="showRejectBreakdown ? '收合報廢細項' : '展開報廢細項'" @click.stop="showRejectBreakdown = !showRejectBreakdown" @keydown.enter.space.prevent.stop="showRejectBreakdown = !showRejectBreakdown">{{ showRejectBreakdown ? '▾' : '▸' }}</button>
            </th>
            <template v-if="showRejectBreakdown">
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('REJECT_QTY')" @click="toggleSort('REJECT_QTY')" @keydown.enter.space.prevent="toggleSort('REJECT_QTY')">REJECT <span class="sort-indicator">{{ sortLabel('REJECT_QTY') }}</span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('STANDBY_QTY')" @click="toggleSort('STANDBY_QTY')" @keydown.enter.space.prevent="toggleSort('STANDBY_QTY')">STANDBY <span class="sort-indicator">{{ sortLabel('STANDBY_QTY') }}</span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('QTYTOPROCESS_QTY')" @click="toggleSort('QTYTOPROCESS_QTY')" @keydown.enter.space.prevent="toggleSort('QTYTOPROCESS_QTY')">QTYTOPROCESS <span class="sort-indicator">{{ sortLabel('QTYTOPROCESS_QTY') }}</span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('INPROCESS_QTY')" @click="toggleSort('INPROCESS_QTY')" @keydown.enter.space.prevent="toggleSort('INPROCESS_QTY')">INPROCESS <span class="sort-indicator">{{ sortLabel('INPROCESS_QTY') }}</span></th>
              <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('PROCESSED_QTY')" @click="toggleSort('PROCESSED_QTY')" @keydown.enter.space.prevent="toggleSort('PROCESSED_QTY')">PROCESSED <span class="sort-indicator">{{ sortLabel('PROCESSED_QTY') }}</span></th>
            </template>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('DEFECT_QTY')" @click="toggleSort('DEFECT_QTY')" @keydown.enter.space.prevent="toggleSort('DEFECT_QTY')">不良品數 <span class="sort-indicator">{{ sortLabel('DEFECT_QTY') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('REJECTCOMMENT')" @click="toggleSort('REJECTCOMMENT')" @keydown.enter.space.prevent="toggleSort('REJECTCOMMENT')">備註 <span class="sort-indicator">{{ sortLabel('REJECTCOMMENT') }}</span></th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('EQUIPMENTNAME')" @click="toggleSort('EQUIPMENTNAME')" @keydown.enter.space.prevent="toggleSort('EQUIPMENTNAME')">
              報廢登錄設備
              <span class="cross-station-note" title="此設備為報廢事件登錄的設備，可能與查詢設備不同（跨站報廢）">(可能不同於查詢設備)</span>
              <span class="sort-indicator">{{ sortLabel('EQUIPMENTNAME') }}</span>
            </th>
            <th class="sortable-th" tabindex="0" :aria-sort="ariaSortFor('TXN_TIME')" @click="toggleSort('TXN_TIME')" @keydown.enter.space.prevent="toggleSort('TXN_TIME')">報廢時間 <span class="sort-indicator">{{ sortLabel('TXN_TIME') }}</span></th>
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
