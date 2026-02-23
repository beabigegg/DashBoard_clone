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
  'CONTAINERID',
  'CONTAINERNAME',
  'SPECNAME',
  'TRACKINTIMESTAMP',
  'TRACKOUTTIMESTAMP',
  'TRACKINQTY',
  'TRACKOUTQTY',
  'EQUIPMENTNAME',
  'WORKCENTERNAME',
]);
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title">生產紀錄</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出生產紀錄"
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
      無生產紀錄
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
          <tr v-for="(row, rowIndex) in rows" :key="row.HISTORYMAINLINEID || rowIndex">
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
