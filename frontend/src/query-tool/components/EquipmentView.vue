<script setup>
import MultiSelect from '../../resource-shared/components/MultiSelect.vue';
import FilterToolbar from '../../shared-ui/components/FilterToolbar.vue';

import EquipmentJobsPanel from './EquipmentJobsPanel.vue';
import EquipmentLotsTable from './EquipmentLotsTable.vue';
import EquipmentRejectsTable from './EquipmentRejectsTable.vue';
import EquipmentTimeline from './EquipmentTimeline.vue';

const props = defineProps({
  equipmentOptions: {
    type: Array,
    default: () => [],
  },
  equipmentRawOptions: {
    type: Array,
    default: () => [],
  },
  selectedEquipmentIds: {
    type: Array,
    default: () => [],
  },
  startDate: {
    type: String,
    default: '',
  },
  endDate: {
    type: String,
    default: '',
  },
  activeSubTab: {
    type: String,
    default: 'lots',
  },
  loading: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
  },
  lotsRows: {
    type: Array,
    default: () => [],
  },
  jobsRows: {
    type: Array,
    default: () => [],
  },
  rejectsRows: {
    type: Array,
    default: () => [],
  },
  statusRows: {
    type: Array,
    default: () => [],
  },
  exporting: {
    type: Object,
    required: true,
  },
  canExportSubTab: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits([
  'update:selected-equipment-ids',
  'update:start-date',
  'update:end-date',
  'reset-date-range',
  'query-active-sub-tab',
  'change-sub-tab',
  'export-sub-tab',
]);

const tabMeta = Object.freeze({
  lots: '生產紀錄',
  jobs: '維修紀錄',
  rejects: '報廢紀錄',
  timeline: 'Timeline',
});

const subTabs = Object.keys(tabMeta);
</script>

<template>
  <div class="space-y-3">
    <section class="rounded-card border border-stroke-soft bg-white p-3 shadow-soft">
      <FilterToolbar>
        <label class="flex min-w-[320px] flex-col gap-1 text-xs text-slate-500">
          <span class="font-medium">設備（可複選）</span>
          <MultiSelect
            :model-value="selectedEquipmentIds"
            :options="equipmentOptions"
            :disabled="loading.bootstrapping"
            searchable
            placeholder="請選擇設備"
            @update:model-value="emit('update:selected-equipment-ids', $event)"
          />
        </label>

        <label class="flex min-w-[180px] flex-col gap-1 text-xs text-slate-500">
          <span class="font-medium">開始日期</span>
          <input
            type="date"
            class="h-9 rounded-card border border-stroke-soft bg-white px-3 text-sm text-slate-700 outline-none focus:border-brand-500"
            :value="startDate"
            @input="emit('update:start-date', $event.target.value)"
          />
        </label>

        <label class="flex min-w-[180px] flex-col gap-1 text-xs text-slate-500">
          <span class="font-medium">結束日期</span>
          <input
            type="date"
            class="h-9 rounded-card border border-stroke-soft bg-white px-3 text-sm text-slate-700 outline-none focus:border-brand-500"
            :value="endDate"
            @input="emit('update:end-date', $event.target.value)"
          />
        </label>

        <template #actions>
          <button
            type="button"
            class="h-9 rounded-card border border-stroke-soft bg-white px-3 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
            @click="emit('reset-date-range')"
          >
            近 30 天
          </button>

          <button
            type="button"
            class="h-9 rounded-card bg-brand-500 px-4 text-sm font-medium text-white transition hover:bg-brand-600"
            :disabled="loading[activeSubTab] || loading.timeline"
            @click="emit('query-active-sub-tab')"
          >
            {{ loading[activeSubTab] || loading.timeline ? '查詢中...' : '查詢' }}
          </button>
        </template>
      </FilterToolbar>

      <p v-if="errors.filters" class="mt-2 rounded-card border border-state-danger/40 bg-rose-50 px-3 py-2 text-xs text-state-danger">
        {{ errors.filters }}
      </p>
    </section>

    <section class="rounded-card border border-stroke-soft bg-white p-3 shadow-soft">
      <div class="mb-3 flex flex-wrap gap-2 border-b border-stroke-soft pb-2">
        <button
          v-for="tab in subTabs"
          :key="tab"
          type="button"
          class="rounded-card border px-3 py-1.5 text-xs font-medium transition"
          :class="tab === activeSubTab
            ? 'border-brand-500 bg-brand-50 text-brand-700'
            : 'border-transparent bg-surface-muted/70 text-slate-600 hover:border-stroke-soft hover:text-slate-800'"
          @click="emit('change-sub-tab', tab)"
        >
          {{ tabMeta[tab] }}
        </button>
      </div>

      <EquipmentLotsTable
        v-if="activeSubTab === 'lots'"
        :rows="lotsRows"
        :loading="loading.lots"
        :error="errors.lots"
        :export-disabled="!canExportSubTab('lots')"
        :exporting="exporting.lots"
        @export="emit('export-sub-tab', 'lots')"
      />

      <EquipmentJobsPanel
        v-else-if="activeSubTab === 'jobs'"
        :rows="jobsRows"
        :loading="loading.jobs"
        :error="errors.jobs"
        :export-disabled="!canExportSubTab('jobs')"
        :exporting="exporting.jobs"
        @export="emit('export-sub-tab', 'jobs')"
      />

      <EquipmentRejectsTable
        v-else-if="activeSubTab === 'rejects'"
        :rows="rejectsRows"
        :loading="loading.rejects"
        :error="errors.rejects"
        :export-disabled="!canExportSubTab('rejects')"
        :exporting="exporting.rejects"
        @export="emit('export-sub-tab', 'rejects')"
      />

      <EquipmentTimeline
        v-else
        :status-rows="statusRows"
        :lots-rows="lotsRows"
        :jobs-rows="jobsRows"
        :equipment-options="equipmentRawOptions"
        :selected-equipment-ids="selectedEquipmentIds"
        :start-date="startDate"
        :end-date="endDate"
        :loading="loading.timeline"
        :error="errors.timeline"
        :export-disabled="!canExportSubTab('timeline')"
        :exporting="exporting.timeline"
        @export="emit('export-sub-tab', 'timeline')"
      />
    </section>
  </div>
</template>
