<script setup lang="ts">
import { ref } from 'vue';

import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import FilterToolbar from '../../shared-ui/components/FilterToolbar.vue';

import EquipmentLotsTable from './EquipmentLotsTable.vue';
import EquipmentRejectsTable from './EquipmentRejectsTable.vue';
import ExportButton from './ExportButton.vue';
import LotJobsTable from './LotJobsTable.vue';
import LotTimeline from './LotTimeline.vue';

const props = defineProps({
  equipmentOptions: {
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
  exporting: {
    type: Object,
    required: true,
  },
  canExportSubTab: {
    type: Function,
    required: true,
  },
  pageSizeOptions: {
    type: Array,
    default: () => [25, 50, 100, 200],
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
  'change-lots-page-size',
  'export-sub-tab',
]);

const tabMeta = Object.freeze({
  lots: '生產紀錄',
  jobs: '維修紀錄',
  rejects: '報廢紀錄',
});

const subTabs = Object.keys(tabMeta);

const showTimelineModal = ref(false);
</script>

<template>
  <div class="space-y-3">
    <section class="card ui-card">
      <div class="card-body ui-card-body">
        <FilterToolbar>
          <label class="filter-group filter-group--equipment">
            <span class="filter-label">設備（可複選）</span>
            <MultiSelect
              :model-value="selectedEquipmentIds as (string | number)[]"
              :options="equipmentOptions as (string | number | Record<string, unknown>)[]"
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
              data-testid="start-date"
              :value="startDate"
              @input="emit('update:start-date', ($event.target as HTMLInputElement).value)"
            />
          </label>

          <label class="filter-group">
            <span class="filter-label">結束日期</span>
            <input
              type="date"
              class="query-tool-date-input"
              data-testid="end-date"
              :value="endDate"
              @input="emit('update:end-date', ($event.target as HTMLInputElement).value)"
            />
          </label>

          <template #actions>
            <button
              type="button"
              class="ui-btn ui-btn--ghost"
              @click="emit('reset-date-range')"
            >
              近 30 天
            </button>

            <button
              type="button"
              class="ui-btn ui-btn--primary"
              data-testid="submit-btn"
              :disabled="loading[activeSubTab] || loading.timeline"
              @click="emit('query-active-sub-tab')"
            >
              {{ loading[activeSubTab] || loading.timeline ? '查詢中...' : '查詢' }}
            </button>
          </template>
        </FilterToolbar>

        <ErrorBanner :message="errors.filters" />
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
            {{ (tabMeta as Record<string, string>)[tab] }}
          </button>
        </div>

      <template v-if="activeSubTab === 'lots'">
        <div v-if="lotsRows.length > 0" class="query-tool-section-header">
          <span></span>
          <button
            type="button"
            class="ui-btn ui-btn--ghost ui-btn--sm"
            @click="showTimelineModal = true"
          >
            查看生產 Timeline
          </button>
        </div>
        <EquipmentLotsTable
          :rows="lotsRows"
          :loading="loading.lots"
          :error="errors.lots"
          :export-disabled="!canExportSubTab('lots')"
          :exporting="exporting.lots"
          @export="emit('export-sub-tab', 'lots')"
        />
        <div
          v-if="(lotsPagination?.total || 0) > 0"
          class="query-tool-pagination"
        >
          <span class="query-tool-muted">
            第 {{ lotsPagination.page }} / {{ lotsPagination.total_pages }} 頁，共
            {{ lotsPagination.total }} 筆
          </span>
          <label class="query-tool-page-size">
            每頁
            <select
              :value="lotsPagination.per_page"
              @change="emit('change-lots-page-size', Number(($event.target as HTMLSelectElement).value))"
            >
              <option v-for="size in pageSizeOptions" :key="(size as PropertyKey)" :value="size">{{ size }}</option>
            </select>
            筆
          </label>
          <div class="query-tool-pagination-actions">
            <button
              type="button"
              class="ui-btn ui-btn--ghost"
              :disabled="loading.lots || lotsPagination.page <= 1"
              data-testid="page-prev"
              @click="emit('change-lots-page', lotsPagination.page - 1)"
            >
              上一頁
            </button>
            <button
              type="button"
              class="ui-btn ui-btn--ghost"
              :disabled="loading.lots || lotsPagination.page >= lotsPagination.total_pages"
              data-testid="page-next"
              @click="emit('change-lots-page', lotsPagination.page + 1)"
            >
              下一頁
            </button>
          </div>
        </div>
      </template>

      <template v-if="activeSubTab === 'jobs'">
        <div class="query-tool-section-header">
          <h4 class="card-title ui-card-title">維修紀錄</h4>
          <ExportButton
            :disabled="!canExportSubTab('jobs')"
            :loading="exporting.jobs"
            label="匯出維修紀錄"
            @click="emit('export-sub-tab', 'jobs')"
          />
        </div>
        <ErrorBanner :message="errors.jobs" />
        <LotJobsTable
          :rows="jobsRows"
          :loading="loading.jobs"
        />
      </template>

      <EquipmentRejectsTable
        v-if="activeSubTab === 'rejects'"
        :rows="rejectsRows"
        :loading="loading.rejects"
        :error="errors.rejects"
        :export-disabled="!canExportSubTab('rejects')"
        :exporting="exporting.rejects"
        @export="emit('export-sub-tab', 'rejects')"
      />
      </div>
    </section>

    <Teleport to="body">
      <div class="theme-query-tool">
        <div
          v-if="showTimelineModal"
          class="lineage-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="LOT 生產 Timeline"
          @keydown.esc="showTimelineModal = false"
          @click.self="showTimelineModal = false"
        >
          <div class="lineage-modal-container">
            <div class="lineage-modal-header">
              <h2 class="lineage-modal-title">LOT 生產 Timeline</h2>
              <button
                type="button"
                class="lineage-modal-close"
                aria-label="關閉 Timeline 視窗"
                title="關閉（Esc）"
                @click="showTimelineModal = false"
              >✕</button>
            </div>
            <div class="lineage-modal-body" style="padding: 16px;">
              <LotTimeline
                :history-rows="lotsRows"
                :pagination="lotsPagination"
              />
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.filter-group--equipment {
  min-width: 320px;
}
</style>
