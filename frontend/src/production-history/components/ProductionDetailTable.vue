<script setup>
const props = defineProps({
  rows: { type: Array, default: () => [] },
  pagination: {
    type: Object,
    default: () => ({ page: 1, per_page: 25, total_rows: 0, total_pages: 0 }),
  },
  loading: { type: Boolean, default: false },
  exportUrl: { type: String, default: null },
});

const emit = defineEmits(['page-change']);

const COLUMNS = [
  { key: 'lot_id',        label: 'LotID' },
  { key: 'pj_type',       label: 'Type' },
  { key: 'bop',           label: 'BOP' },
  { key: 'work_order',    label: 'WorkOrder' },
  { key: 'wafer_lot',     label: 'WaferLot' },
  { key: 'workcenter',    label: 'WorkCenter' },
  { key: 'spec',          label: 'Spec' },
  { key: 'equipment_name',label: 'EquipName' },
  { key: 'trackin_time',  label: 'TrackIn' },
  { key: 'trackout_time', label: 'TrackOut' },
  { key: 'trackin_qty',   label: 'InQTY' },
  { key: 'trackout_qty',  label: 'OutQTY' },
];

function formatTs(value) {
  if (!value) return '';
  try {
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return d.toLocaleString('zh-TW', { hour12: false });
  } catch {
    return String(value);
  }
}

function cellValue(row, key) {
  const v = row[key];
  if (key === 'trackin_time' || key === 'trackout_time') return formatTs(v);
  return v ?? '';
}
</script>

<template>
  <div class="ui-card">
    <div class="ui-card-header" style="display:flex;align-items:center;justify-content:space-between;">
      <span class="ui-card-title">明細資料</span>
      <div style="display:flex;align-items:center;gap:12px;">
        <span class="ph-detail-count">
          共 {{ pagination.total_rows.toLocaleString() }} 筆
        </span>
        <a
          v-if="exportUrl"
          :href="exportUrl"
          class="ui-btn ui-btn--ghost"
          download
        >
          匯出 CSV
        </a>
      </div>
    </div>

    <div
      class="detail-table-wrap ui-table-wrap"
      :class="{ 'is-loading': loading }"
    >
      <table class="detail-table">
        <thead>
          <tr>
            <th v-for="col in COLUMNS" :key="col.key">
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="COLUMNS.length" class="placeholder">載入中…</td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="COLUMNS.length" class="placeholder">無資料</td>
          </tr>
          <tr v-for="(row, idx) in rows" v-else :key="idx">
            <td v-for="col in COLUMNS" :key="col.key">
              {{ cellValue(row, col.key) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="pagination.total_pages > 1" class="pagination">
      <button
        :disabled="pagination.page <= 1 || loading"
        @click="emit('page-change', pagination.page - 1)"
      >
        上一頁
      </button>
      <span class="page-info">
        {{ pagination.page }} / {{ pagination.total_pages }}
      </span>
      <button
        :disabled="pagination.page >= pagination.total_pages || loading"
        @click="emit('page-change', pagination.page + 1)"
      >
        下一頁
      </button>
    </div>
  </div>
</template>
