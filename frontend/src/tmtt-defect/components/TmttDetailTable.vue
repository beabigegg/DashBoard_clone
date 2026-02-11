<script setup>
import { computed } from 'vue';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  sortState: {
    type: Object,
    default: () => ({ column: '', asc: true }),
  },
});

const emit = defineEmits(['sort']);

const columns = computed(() => [
  { key: 'CONTAINERNAME', label: 'LOT ID' },
  { key: 'PJ_TYPE', label: 'TYPE' },
  { key: 'PRODUCTLINENAME', label: 'PACKAGE' },
  { key: 'WORKFLOW', label: 'WORKFLOW' },
  { key: 'FINISHEDRUNCARD', label: '完工流水碼' },
  { key: 'TMTT_EQUIPMENTNAME', label: 'TMTT設備' },
  { key: 'MOLD_EQUIPMENTNAME', label: 'MOLD設備' },
  { key: 'INPUT_QTY', label: '投入數', numeric: true },
  { key: 'PRINT_DEFECT_QTY', label: '印字不良', numeric: true, danger: true },
  { key: 'PRINT_DEFECT_RATE', label: '印字不良率(%)', numeric: true, danger: true, decimal: 4 },
  { key: 'LEAD_DEFECT_QTY', label: '腳型不良', numeric: true, warning: true },
  { key: 'LEAD_DEFECT_RATE', label: '腳型不良率(%)', numeric: true, warning: true, decimal: 4 },
]);

function formatNumber(value, decimal = null) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0';
  if (Number.isInteger(decimal) && decimal >= 0) {
    return n.toFixed(decimal);
  }
  return n.toLocaleString('zh-TW');
}

function sortIndicator(key) {
  if (props.sortState?.column !== key) {
    return '';
  }
  return props.sortState?.asc ? '▲' : '▼';
}

function cellClass(column) {
  const classes = [];
  if (column.numeric) classes.push('is-numeric');
  if (column.danger) classes.push('is-danger');
  if (column.warning) classes.push('is-warning');
  return classes;
}
</script>

<template>
  <div class="tmtt-detail-table-wrap">
    <table class="tmtt-detail-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">
            <button type="button" class="tmtt-sort-btn" @click="emit('sort', column.key)">
              {{ column.label }}
              <span class="tmtt-sort-indicator">{{ sortIndicator(column.key) }}</span>
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length" class="tmtt-empty-row">無資料</td>
        </tr>
        <tr v-for="(row, index) in rows" v-else :key="`${row.CONTAINERNAME || 'row'}-${index}`">
          <td
            v-for="column in columns"
            :key="`${row.CONTAINERNAME || 'row'}-${column.key}-${index}`"
            :class="cellClass(column)"
          >
            <template v-if="column.numeric">{{ formatNumber(row[column.key], column.decimal) }}</template>
            <template v-else>{{ row[column.key] || '' }}</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
