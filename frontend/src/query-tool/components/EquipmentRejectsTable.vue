<script setup>
import ExportButton from './ExportButton.vue';
import { formatCellValue } from '../utils/values.js';

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
  exportDisabled: {
    type: Boolean,
    default: true,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['export']);

const columns = Object.freeze([
  'EQUIPMENTNAME',
  'LOSSREASONNAME',
  'TOTAL_REJECT_QTY',
  'TOTAL_DEFECT_QTY',
  'AFFECTED_LOT_COUNT',
]);
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title">報廢紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出報廢紀錄"
        @click="emit('export')"
      />
    </div>

    <p v-if="error" class="error-banner">
      {{ error }}
    </p>

    <div v-if="loading" class="placeholder">
      載入中...
    </div>

    <div v-else-if="rows.length === 0" class="placeholder">
      無報廢紀錄
    </div>

    <div v-else class="query-tool-table-wrap tall">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">
              {{ column }}
            </th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
