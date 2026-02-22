<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 50, total: 0, totalPages: 1 }),
  },
  loading: { type: Boolean, default: false },
  detailReason: { type: String, default: '' },
});

defineEmits(['go-to-page', 'clear-reason']);

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="card">
    <div class="card-header">
      <div class="card-title">
        明細列表
        <span v-if="detailReason" class="detail-reason-badge">
          原因: {{ detailReason }}
          <button type="button" class="badge-clear" @click="$emit('clear-reason')">×</button>
        </span>
      </div>
    </div>
    <div class="card-body detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>LOT</th>
            <th>WORKCENTER_GROUP</th>
            <th>WORKCENTER</th>
            <th>Package</th>
            <th>PJ_TYPE</th>
            <th>PJ_FUNCTION</th>
            <th>PRODUCT</th>
            <th>原因</th>
            <th>扣帳報廢量</th>
            <th>不扣帳報廢量</th>
            <th>REJECT_QTY</th>
            <th>STANDBY_QTY</th>
            <th>QTYTOPROCESS</th>
            <th>INPROCESS</th>
            <th>PROCESSED</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in items" :key="`${row.TXN_DAY}-${row.WORKCENTERNAME}-${row.CONTAINERNAME}-${row.LOSSREASONNAME}-${idx}`">
            <td>{{ row.TXN_DAY }}</td>
            <td>{{ row.CONTAINERNAME || '' }}</td>
            <td>{{ row.WORKCENTER_GROUP }}</td>
            <td>{{ row.WORKCENTERNAME }}</td>
            <td>{{ row.PRODUCTLINENAME }}</td>
            <td>{{ row.PJ_TYPE }}</td>
            <td>{{ row.PJ_FUNCTION || '' }}</td>
            <td>{{ row.PRODUCTNAME || '' }}</td>
            <td>{{ row.LOSSREASONNAME }}</td>
            <td>{{ formatNumber(row.REJECT_TOTAL_QTY) }}</td>
            <td>{{ formatNumber(row.DEFECT_QTY) }}</td>
            <td>{{ formatNumber(row.REJECT_QTY) }}</td>
            <td>{{ formatNumber(row.STANDBY_QTY) }}</td>
            <td>{{ formatNumber(row.QTYTOPROCESS_QTY) }}</td>
            <td>{{ formatNumber(row.INPROCESS_QTY) }}</td>
            <td>{{ formatNumber(row.PROCESSED_QTY) }}</td>
          </tr>
          <tr v-if="!items || items.length === 0">
            <td colspan="16" class="placeholder">No data</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <button :disabled="pagination.page <= 1 || loading" @click="$emit('go-to-page', pagination.page - 1)">上一頁</button>
      <span class="page-info">
        第 {{ pagination.page }} / {{ pagination.totalPages }} 頁 · 共 {{ formatNumber(pagination.total) }} 筆
      </span>
      <button :disabled="pagination.page >= pagination.totalPages || loading" @click="$emit('go-to-page', pagination.page + 1)">下一頁</button>
    </div>
  </section>
</template>
