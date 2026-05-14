<script setup lang="ts">
import { computed } from 'vue';

import { useSortableTable } from '../../shared-composables/useSortableTable';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import { formatCellValue } from '../utils/values';

const props = defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  workcenterGroups: {
    type: Array,
    default: () => [],
  },
  selectedWorkcenterGroups: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['update:workcenterGroups']);

const HIDDEN_COLUMNS = new Set(['CONTAINERID', 'EQUIPMENTID', 'RESOURCEID']);

const COLUMN_LABELS = Object.freeze({
  CONTAINERNAME: 'LOT ID',
  PJ_TYPE: 'TYPE',
  PJ_BOP: 'BOP',
  PJ_WORKORDER: 'WORKORDER',
});

const columns = computed(() =>
  Object.keys(props.rows[0] || {}).filter((col) => !HIDDEN_COLUMNS.has(col)),
);

const rowsRef = computed(() => props.rows as Record<string, unknown>[]);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(rowsRef);

function sortLabel(key: string): string {
  if (sortKey.value !== key) return '⇕';
  return sortDirection.value === 'asc' ? '▲' : '▼';
}

function ariaSortFor(key: string): 'none' | 'ascending' | 'descending' {
  if (sortKey.value !== key) return 'none';
  return sortDirection.value === 'asc' ? 'ascending' : 'descending';
}

const workcenterOptions = computed(() => {
  return props.workcenterGroups.map((rawGroup) => {
    const group = rawGroup as Record<string, unknown>;
    const name = typeof rawGroup === 'string' ? rawGroup : String(group?.name || group?.WORKCENTER_GROUP || '');
    return {
      value: name,
      label: name,
    };
  }).filter((option) => option.value);
});
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">歷程資料</h4>

      <label class="filter-group filter-group--wide">
        <span class="filter-label">站點群組篩選</span>
        <MultiSelect
          :model-value="selectedWorkcenterGroups as (string | number)[]"
          :options="workcenterOptions"
          placeholder="全部群組"
          searchable
          :disabled="loading"
          @update:model-value="emit('update:workcenterGroups', $event)"
        />
      </label>
    </div>

    <BlockLoadingState v-if="loading" text="歷程資料讀取中..." />

    <div v-else-if="rows.length === 0" class="placeholder">
      無歷程資料
    </div>

    <div v-else class="query-tool-table-wrap short">
      <table class="query-tool-table">
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column"
              class="sortable-th"
              :aria-sort="ariaSortFor(column)"
              @click="toggleSort(column)"
            >
              {{ (COLUMN_LABELS as Record<string, string>)[column] || column }}
              <span class="sort-indicator">{{ sortLabel(column) }}</span>
            </th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, rowIndex) in sortedData"
            :key="(row.HISTORYMAINLINEID || row.TRACKINTIMESTAMP || rowIndex) as PropertyKey"
          >
            <td v-for="column in columns" :key="`${rowIndex}-${column}`">
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.filter-group--wide {
  min-width: 260px;
}
</style>
