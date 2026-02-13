<script setup>
import { computed } from 'vue';

import MultiSelect from '../../resource-shared/components/MultiSelect.vue';
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

const columns = computed(() =>
  Object.keys(props.rows[0] || {}).filter((col) => !HIDDEN_COLUMNS.has(col)),
);

const workcenterOptions = computed(() => {
  return props.workcenterGroups.map((group) => {
    const name = typeof group === 'string' ? group : group?.name || group?.WORKCENTER_GROUP || '';
    return {
      value: String(name),
      label: String(name),
    };
  }).filter((option) => option.value);
});
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div class="mb-2 flex flex-wrap items-end justify-between gap-2">
      <h4 class="text-sm font-semibold text-slate-800">歷程資料</h4>

      <label class="min-w-[260px] text-xs text-slate-500">
        <span class="mb-1 block font-medium">站點群組篩選</span>
        <MultiSelect
          :model-value="selectedWorkcenterGroups"
          :options="workcenterOptions"
          placeholder="全部群組"
          searchable
          :disabled="loading"
          @update:model-value="emit('update:workcenterGroups', $event)"
        />
      </label>
    </div>

    <div v-if="loading" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      歷程資料讀取中...
    </div>

    <div v-else-if="rows.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      無歷程資料
    </div>

    <div v-else class="max-h-[360px] overflow-auto rounded-card border border-stroke-soft">
      <table class="min-w-full border-collapse text-xs">
        <thead class="sticky top-0 z-10 bg-slate-100 text-slate-700">
          <tr>
            <th
              v-for="column in columns"
              :key="column"
              class="whitespace-nowrap border-b border-stroke-soft px-2 py-1.5 text-left font-semibold"
            >
              {{ column }}
            </th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="(row, rowIndex) in rows"
            :key="row.HISTORYMAINLINEID || row.TRACKINTIMESTAMP || rowIndex"
            class="odd:bg-white even:bg-slate-50"
          >
            <td
              v-for="column in columns"
              :key="`${rowIndex}-${column}`"
              class="whitespace-nowrap border-b border-stroke-soft/70 px-2 py-1.5 text-slate-700"
            >
              {{ formatCellValue(row[column]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
