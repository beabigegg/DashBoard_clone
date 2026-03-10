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
  <div>
    <div v-if="loading" class="placeholder">
      讀取中...
    </div>

    <div v-else-if="sortedRows.length === 0" class="placeholder">
      {{ emptyText }}
    </div>

    <div v-else class="query-tool-table-wrap">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th>LOT ID</th>
            <th>WORKCENTER</th>
            <th>Package</th>
            <th>FUNCTION</th>
            <th>TYPE</th>
            <th>PRODUCT</th>
            <th>原因</th>
            <th>EQUIPMENT</th>
            <th>COMMENT</th>
            <th
              class="row-clickable"
              @click="showRejectBreakdown = !showRejectBreakdown"
            >
              扣帳報廢量 <span>{{ showRejectBreakdown ? '▾' : '▸' }}</span>
            </th>
            <template v-if="showRejectBreakdown">
              <th>REJECT</th>
              <th>STANDBY</th>
              <th>QTYTOPROCESS</th>
              <th>INPROCESS</th>
              <th>PROCESSED</th>
            </template>
            <th>不扣帳報廢量</th>
            <th>報廢時間</th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, idx) in sortedRows"
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
.row-clickable {
  cursor: pointer;
}
</style>
