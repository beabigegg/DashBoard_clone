<script setup>
import { computed, ref } from 'vue';

import { formatDateTime, parseDateTime } from '../utils/values.js';

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

function toNumber(value, defaultValue = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : defaultValue;
}

function formatNumber(value) {
  return toNumber(value).toLocaleString('zh-TW');
}

function normalizeText(value, fallback = '') {
  const text = String(value || '').trim();
  return text || fallback;
}

function normalizeRejectRow(row) {
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

const sortedRows = computed(() => {
  return [...normalizedRows.value].sort((a, b) => {
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
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div v-if="loading" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      讀取中...
    </div>

    <div v-else-if="sortedRows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      {{ emptyText }}
    </div>

    <div v-else class="max-h-[420px] overflow-auto rounded-card border border-stroke-soft">
      <table class="min-w-full border-collapse text-xs">
        <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
          <tr>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">LOT</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">WORKCENTER</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">Package</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">FUNCTION</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">TYPE</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">PRODUCT</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">原因</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">EQUIPMENT</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">COMMENT</th>
            <th
              class="cursor-pointer whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold hover:text-brand-700"
              @click="showRejectBreakdown = !showRejectBreakdown"
            >
              扣帳報廢量 <span>{{ showRejectBreakdown ? '▾' : '▸' }}</span>
            </th>
            <template v-if="showRejectBreakdown">
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">REJECT</th>
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">STANDBY</th>
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">QTYTOPROCESS</th>
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">INPROCESS</th>
              <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">PROCESSED</th>
            </template>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">不扣帳報廢量</th>
            <th class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold">報廢時間</th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, idx) in sortedRows"
            :key="`${row.TXN_TIME_RAW}-${row.CONTAINERNAME}-${row.LOSSREASONNAME}-${idx}`"
            class="odd:bg-white even:bg-slate-50"
          >
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.CONTAINERNAME }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.WORKCENTERNAME || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.PRODUCTLINENAME || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.PJ_FUNCTION || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.PJ_TYPE || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.PRODUCTNAME || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.LOSSREASONNAME || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.EQUIPMENTNAME || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.REJECTCOMMENT || '-' }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
            <template v-if="showRejectBreakdown">
              <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.REJECT_QTY) }}</td>
              <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.STANDBY_QTY) }}</td>
              <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
              <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.INPROCESS_QTY) }}</td>
              <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.PROCESSED_QTY) }}</td>
            </template>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ formatNumber(row.DEFECT_QTY) }}</td>
            <td class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700">{{ row.TXN_TIME || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
