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
  lotsPagination: {
    type: Object,
    default: () => ({ page: 1, per_page: 0, total: 0, total_pages: 1 }),
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
  'change-lots-page',
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
    <section class="card ui-card">
      <div class="card-body ui-card-body">
        <FilterToolbar>
          <label class="filter-group filter-group--equipment">
            <span class="filter-label">設備（可複選）</span>
            <MultiSelect
              :model-value="selectedEquipmentIds"
              :options="equipmentOptions"
              :disabled="loading.bootstrapping"
              searchable
              placeholder="請選擇設備"
              @update:model-value="emit('update:selected-equipment-ids', $event)"
            />
          </label>

          <label class="filter-group">
            <span class="filter-label">開始日期</span>
            <input
              type="date"
              class="query-tool-date-input"
              :value="startDate"
              @input="emit('update:start-date', $event.target.value)"
            />
          </label>

          <label class="filter-group">
            <span class="filter-label">結束日期</span>
            <input
              type="date"
              class="query-tool-date-input"
              :value="endDate"
              @input="emit('update:end-date', $event.target.value)"
            />
          </label>

          <template #actions>
            <button
              type="button"
              class="btn btn-ghost"
              @click="emit('reset-date-range')"
            >
              近 30 天
            </button>

            <button
              type="button"
              class="btn btn-primary"
              :disabled="loading[activeSubTab] || loading.timeline"
              @click="emit('query-active-sub-tab')"
            >
              {{ loading[activeSubTab] || loading.timeline ? '查詢中...' : '查詢' }}
            </button>
          </template>
        </FilterToolbar>

        <p v-if="errors.filters" class="error-banner error-banner--mt8">
          {{ errors.filters }}
        </p>
      </div>
    </section>

    <section class="card ui-card">
      <div class="card-body ui-card-body">
        <div class="query-tool-sub-tab-bar">
          <button
            v-for="tab in subTabs"
            :key="tab"
            type="button"
            class="query-tool-sub-tab"
            :class="{ active: tab === activeSubTab }"
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
      <div
        v-if="activeSubTab === 'lots' && (lotsPagination?.total_pages || 1) > 1"
        class="query-tool-pagination"
      >
        <span class="query-tool-muted">
          第 {{ lotsPagination.page }} / {{ lotsPagination.total_pages }} 頁，共
          {{ lotsPagination.total }} 筆
        </span>
        <div class="query-tool-pagination-actions">
          <button
            type="button"
            class="btn btn-ghost"
            :disabled="loading.lots || lotsPagination.page <= 1"
            @click="emit('change-lots-page', lotsPagination.page - 1)"
          >
            上一頁
          </button>
          <button
            type="button"
            class="btn btn-ghost"
            :disabled="loading.lots || lotsPagination.page >= lotsPagination.total_pages"
            @click="emit('change-lots-page', lotsPagination.page + 1)"
          >
            下一頁
          </button>
        </div>
      </div>

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
      </div>
    </section>
  </div>
</template>

<style scoped>
.filter-group--equipment {
  min-width: 320px;
}

.error-banner--mt8 {
  margin-top: theme('spacing.token.p8');
}
</style>
