<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue';

import { ensureMesApiAvailable } from '../core/api';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import DailyTrendChart from './components/DailyTrendChart.vue';
import BigCategoryChart from './components/BigCategoryChart.vue';
import TopReasonsTable from './components/TopReasonsTable.vue';
import StatusMachineJobTable from './components/StatusMachineJobTable.vue';
// EquipmentDetail and EventDetail are intentionally NOT imported (DQ-6: kept on disk for rollback)

import { useFilterState } from './composables/useFilterState';
import { useDowntimeData } from './composables/useDowntimeData';
import type { FilterState, ChartFilter, TierThreeEntry } from './types';

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
  equipmentData,
  filterOptions,
  loadOptions,
  executePrimaryQuery,
  applyView,
  loadAllEquipmentDetail,
  loadMachineStatusEvents,
  exportEquipmentDetailCsv,
  resetSummaryData,
} = useDowntimeData();

/** Chart cross-filter state (distinct from committed FilterState) */
const chartFilter = ref<ChartFilter>({ big_category: null, status_types: null });

/** Tier 3 lazy-load cache: key = `${resource_id}|${status_type}` */
const tierThreeCache = reactive<Record<string, TierThreeEntry>>({});

const isInitialLoad = ref(true);
const exportingEquipment = ref(false);

/** Clear the Tier 3 cache (on re-query or chartFilter change per DQ-3) */
function clearTierThreeCache(): void {
  for (const key of Object.keys(tierThreeCache)) {
    delete tierThreeCache[key];
  }
}

async function handleExportEquipment(): Promise<void> {
  exportingEquipment.value = true;
  try {
    await exportEquipmentDetailCsv();
  } finally {
    exportingEquipment.value = false;
  }
}

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
  // Clear cross-filter and Tier 3 cache on re-query (DQ-3)
  chartFilter.value = { big_category: null, status_types: null };
  clearTierThreeCache();

  await executePrimaryQuery(body);
  await loadAllEquipmentDetail({ big_category: null, status_types: null });
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

async function handleGranularityChange(next: FilterState): Promise<void> {
  updateAll(next);
  syncDraftFromState();
  await applyView(next.granularity, runPrimaryQuery);
}

/** BigCategoryChart sector click: toggle big_category filter, reload equipment, clear Tier 3 */
async function handleCategoryClick(category: string | null): Promise<void> {
  chartFilter.value.big_category = category;
  clearTierThreeCache();
  await loadAllEquipmentDetail(chartFilter.value);
}

/** DailyTrendChart legend click: toggle status_types filter, reload equipment, clear Tier 3 */
async function handleStatusClick(statusTypes: string[] | null): Promise<void> {
  chartFilter.value.status_types = statusTypes;
  clearTierThreeCache();
  await loadAllEquipmentDetail(chartFilter.value);
}

/** Tier 2 machine row expand: lazy-load events for this machine+status */
async function handleExpandMachine(payload: { resourceId: string; statusType: string }): Promise<void> {
  const { resourceId, statusType } = payload;
  const key = `${resourceId}|${statusType}`;
  const cached = tierThreeCache[key];
  // Skip if already loaded or currently loading
  if (cached?.loaded || cached?.loading) return;
  tierThreeCache[key] = { rows: [], loading: true, loaded: false, error: '' };
  try {
    const rows = await loadMachineStatusEvents(resourceId, statusType, chartFilter.value);
    tierThreeCache[key] = { rows, loading: false, loaded: true, error: '' };
  } catch (e) {
    tierThreeCache[key] = { rows: [], loading: false, loaded: false, error: String(e instanceof Error ? e.message : e) };
  }
}

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

      <!-- KPI cards (clickable: UDT/SDT/EGT toggle chart cross-filter) -->
      <div class="kpi-section">
        <KpiCards
          :summary="summaryData.summary"
          :selected-status-types="chartFilter.status_types"
          @click-status="handleStatusClick"
        />
      </div>

      <!-- Charts section -->
      <div class="section-card">
        <div class="section-inner">
          <div class="chart-grid">
            <DailyTrendChart
              :rows="summaryData.daily_trend"
              :selected-status-types="chartFilter.status_types"
              @click-status="handleStatusClick"
            />
            <BigCategoryChart
              :rows="summaryData.big_category"
              :selected-category="chartFilter.big_category"
              @click-category="handleCategoryClick"
            />
          </div>
        </div>
      </div>

      <!-- Top reasons table -->
      <div class="section-card">
        <div class="section-inner">
          <TopReasonsTable :rows="summaryData.top_reasons" />
        </div>
      </div>

      <!-- Active chart filter chips -->
      <div
        v-if="chartFilter.big_category || chartFilter.status_types?.length"
        class="chart-filter-chips"
        aria-label="已套用的圖表篩選"
      >
        <span v-if="chartFilter.big_category" class="filter-chip">
          類別：{{ chartFilter.big_category }}
          <button
            type="button"
            class="chip-clear"
            aria-label="清除類別篩選"
            @click="handleCategoryClick(null)"
          >×</button>
        </span>
        <span v-if="chartFilter.status_types?.length" class="filter-chip">
          狀態：{{ chartFilter.status_types.join('/') }}
          <button
            type="button"
            class="chip-clear"
            aria-label="清除狀態篩選"
            @click="handleStatusClick(null)"
          >×</button>
        </span>
      </div>

      <!-- Three-tier expandable equipment table -->
      <div class="section-card">
        <div class="section-inner">
          <StatusMachineJobTable
            :equipment-rows="equipmentData.rows"
            :summary-data="summaryData.summary"
            :tier-three-cache="tierThreeCache"
            :chart-filter="chartFilter"
            :loading="loading.equipment"
            :exporting="exportingEquipment"
            @expand-machine="handleExpandMachine"
            @export="handleExportEquipment"
          />
        </div>
      </div>
    </div>

    <!-- Page-level loading overlay -->
    <LoadingOverlay v-if="isInitialLoad || loading.initial" tier="page" />
  </div>
</template>
