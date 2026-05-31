<script setup lang="ts">
import { onMounted, ref, reactive, computed } from 'vue';

import { ensureMesApiAvailable } from '../core/api';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import DailyTrendChart from './components/DailyTrendChart.vue';
import BigCategoryChart from './components/BigCategoryChart.vue';
import TopReasonsTable from './components/TopReasonsTable.vue';
import EquipmentDetail from './components/EquipmentDetail.vue';
import EventDetail from './components/EventDetail.vue';

import { useFilterState } from './composables/useFilterState';
import { useDowntimeData } from './composables/useDowntimeData';
import type { FilterState } from './types';

ensureMesApiAvailable();

const {
  state: filterState,
  updateAll,
  setDefaultDates,
  buildQueryBody,
} = useFilterState();

const {
  loading,
  error,
  summaryData,
  equipmentRows,
  eventData,
  filterOptions,
  loadOptions,
  executePrimaryQuery,
  applyView,
  loadEquipmentDetail,
  loadEventDetail,
  resetSummaryData,
} = useDowntimeData();

/** Active view tab: 'charts' | 'equipment' | 'events' */
const activeTab = ref<'charts' | 'equipment' | 'events'>('charts');

const isInitialLoad = ref(true);

/** draftFilters is a local reactive copy; filterState is the committed state managed by useFilterState */
const draftFilters = reactive<FilterState>({
  workcenter_groups: [],
  families: [],
  resource_ids: [],
  package_groups: [],
  big_categories: [],
  status_types: [],
  start_date: '',
  end_date: '',
  granularity: 'day',
  is_production: false,
  is_key: false,
  is_monitor: false,
});

function syncDraftFromState(): void {
  draftFilters.workcenter_groups = [...filterState.workcenter_groups];
  draftFilters.families = [...filterState.families];
  draftFilters.resource_ids = [...filterState.resource_ids];
  draftFilters.package_groups = [...filterState.package_groups];
  draftFilters.big_categories = [...filterState.big_categories];
  draftFilters.status_types = [...filterState.status_types];
  draftFilters.start_date = filterState.start_date;
  draftFilters.end_date = filterState.end_date;
  draftFilters.granularity = filterState.granularity;
  draftFilters.is_production = filterState.is_production;
  draftFilters.is_key = filterState.is_key;
  draftFilters.is_monitor = filterState.is_monitor;
}

async function runPrimaryQuery(): Promise<void> {
  const body = buildQueryBody();
  if (!body.start_date || !body.end_date) {
    return;
  }
  await executePrimaryQuery(body);
  if (activeTab.value === 'equipment') {
    await loadEquipmentDetail();
  } else if (activeTab.value === 'events') {
    await loadEventDetail(1, 50);
  }
}

/**
 * Handle intermediate draft-state changes (date inputs, dropdowns, granularity).
 * Updates draftFilters and useFilterState without firing a query.
 */
function handleUpdateState(patch: Partial<FilterState>): void {
  for (const key of Object.keys(patch) as Array<keyof FilterState>) {
    // Type-safe assignment into draftFilters
    (draftFilters as Record<string, unknown>)[key] = patch[key];
  }
  updateAll({ ...draftFilters });
}

async function handleFilterChange(next: FilterState): Promise<void> {
  updateAll(next);
  syncDraftFromState();
  await runPrimaryQuery();
}

async function handleClear(): Promise<void> {
  updateAll({
    workcenter_groups: [],
    families: [],
    resource_ids: [],
    package_groups: [],
    big_categories: [],
    status_types: [],
    start_date: draftFilters.start_date,
    end_date: draftFilters.end_date,
    granularity: 'day',
    is_production: false,
    is_key: false,
    is_monitor: false,
  });
  syncDraftFromState();
  await runPrimaryQuery();
}

async function handleTabChange(tab: 'charts' | 'equipment' | 'events'): Promise<void> {
  activeTab.value = tab;
  if (tab === 'equipment' && equipmentRows.value.length === 0) {
    await loadEquipmentDetail();
  } else if (tab === 'events' && eventData.rows.length === 0) {
    await loadEventDetail(1, 50);
  }
}

async function handlePageChange(page: number): Promise<void> {
  await loadEventDetail(page, eventData.pagination.page_size);
}

async function handleGranularityChange(next: FilterState): Promise<void> {
  updateAll(next);
  syncDraftFromState();
  if (activeTab.value === 'charts') {
    await applyView(next.granularity, runPrimaryQuery);
  }
}

const isChartTab = computed(() => activeTab.value === 'charts');
const isEquipmentTab = computed(() => activeTab.value === 'equipment');
const isEventsTab = computed(() => activeTab.value === 'events');

async function initPage(): Promise<void> {
  setDefaultDates();
  syncDraftFromState();

  try {
    await loadOptions();
  } catch {
    // Non-fatal: filter options missing
  }

  await runPrimaryQuery();
  isInitialLoad.value = false;
}

onMounted(() => {
  void initPage();
});
</script>

<template>
  <div class="theme-downtime-analysis">
    <div class="dashboard">
      <!-- Page header -->
      <header class="header-gradient downtime-header">
        <h1>設備停機分析</h1>
        <p class="header-subtitle">停機時數 UDT / SDT / EGT 趨勢 · 大類別分析 · 原因排行 · 設備明細 · 事件詳情</p>
      </header>

      <!-- Filter bar -->
      <FilterBar
        :state="draftFilters"
        :options="filterOptions"
        :loading="loading.querying || loading.options"
        @filter-change="handleFilterChange"
        @update-state="handleUpdateState"
        @clear="handleClear"
      />

      <!-- Error banner -->
      <ErrorBanner :message="error" :dismissible="false" />

      <!-- KPI cards -->
      <KpiCards :summary="summaryData.summary" />

      <!-- View tab buttons -->
      <div class="view-tabs" role="tablist" aria-label="檢視模式">
        <button
          type="button"
          role="tab"
          class="view-tab"
          :class="{ active: isChartTab }"
          :aria-selected="isChartTab"
          @click="handleTabChange('charts')"
        >
          圖表總覽
        </button>
        <button
          type="button"
          role="tab"
          class="view-tab"
          :class="{ active: isEquipmentTab }"
          :aria-selected="isEquipmentTab"
          @click="handleTabChange('equipment')"
        >
          設備明細
        </button>
        <button
          type="button"
          role="tab"
          class="view-tab"
          :class="{ active: isEventsTab }"
          :aria-selected="isEventsTab"
          @click="handleTabChange('events')"
        >
          事件明細
        </button>
      </div>

      <!-- Charts tab -->
      <div v-show="isChartTab" role="tabpanel" aria-label="圖表總覽">
        <div class="section-card">
          <div class="section-inner">
            <div class="chart-grid">
              <DailyTrendChart :rows="summaryData.daily_trend" />
              <BigCategoryChart :rows="summaryData.big_category" />
            </div>
          </div>
        </div>
        <div class="section-card">
          <div class="section-inner">
            <TopReasonsTable :rows="summaryData.top_reasons" />
          </div>
        </div>
      </div>

      <!-- Equipment detail tab -->
      <div v-show="isEquipmentTab" role="tabpanel" aria-label="設備明細">
        <div class="section-card">
          <div class="section-inner">
            <EquipmentDetail :rows="equipmentRows" />
          </div>
        </div>
      </div>

      <!-- Events detail tab -->
      <div v-show="isEventsTab" role="tabpanel" aria-label="事件明細">
        <div class="section-card">
          <div class="section-inner">
            <EventDetail
              :rows="eventData.rows"
              :pagination="eventData.pagination"
              @page-change="handlePageChange"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Page-level loading overlay -->
    <LoadingOverlay v-if="isInitialLoad || loading.initial" tier="page" />
  </div>
</template>
