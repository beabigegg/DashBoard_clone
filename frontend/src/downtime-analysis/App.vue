<script setup lang="ts">
import { onMounted, ref, reactive, computed } from 'vue';

import { ensureMesApiAvailable } from '../core/api';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';

import FilterBar from './components/FilterBar.vue';
import KpiCards from './components/KpiCards.vue';
import DailyTrendChart from './components/DailyTrendChart.vue';
import BigCategoryChart from './components/BigCategoryChart.vue';
import TopReasonsTable from './components/TopReasonsTable.vue';
import StatusMachineJobTable from './components/StatusMachineJobTable.vue';
// EquipmentDetail and EventDetail are intentionally NOT imported (DQ-6: kept on disk for rollback)

import { useFilterState } from './composables/useFilterState';
import { useDowntimeData } from './composables/useDowntimeData';
import { useDowntimeDuckDB } from './composables/useDowntimeDuckDB';
import type { FilterState, ChartFilter, TierThreeEntry } from './types';
import { CATEGORY_PALETTE } from './constants';

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
  duckdbSpoolUrls,
  asyncJobProgress,
  loadOptions,
  executePrimaryQuery,
  cancelAsyncJob,
  applyView,
  loadAllEquipmentDetail,
  loadChartFilterView,
  loadMachineStatusEvents,
  exportEquipmentDetailCsv,
  resetSummaryData,
} = useDowntimeData();

/**
 * Browser DuckDB composable — activated when server returns browser-DuckDB shape
 * (DOWNTIME_BROWSER_DUCKDB=true → response has base_spool_url + jobs_spool_url + taxonomy).
 * When active, all view queries are served locally (zero API round-trips, AC-5).
 */
const duckdb = useDowntimeDuckDB();
const duckdbError = ref('');
const duckdbLoading = ref(false);

/** Chart cross-filter state (distinct from committed FilterState) */
const chartFilter = ref<ChartFilter>({ big_category: null, status_types: null });

/** Tier 3 lazy-load cache: key = `${resource_id}|${status_type}` */
const tierThreeCache = reactive<Record<string, TierThreeEntry>>({});

const isInitialLoad = ref(true);
const exportingEquipment = ref(false);

/** Maps category name → palette color, ranked by hours desc (consistent with treemap order) */
const categoryColorMap = computed<Record<string, string>>(() => {
  const sorted = [...summaryData.big_category].sort((a, b) => b.hours - a.hours);
  const map: Record<string, string> = {};
  sorted.forEach((r, i) => {
    map[r.category] = CATEGORY_PALETTE[i % CATEGORY_PALETTE.length] as string;
  });
  return map;
});

/** Clear the Tier 3 cache (on re-query or chartFilter change per DQ-3) */
function clearTierThreeCache(): void {
  for (const key of Object.keys(tierThreeCache)) {
    delete tierThreeCache[key];
  }
}

async function handleExportEquipment(): Promise<void> {
  exportingEquipment.value = true;
  try {
    if (duckdb.state.value === 'ready') {
      // Browser-blob CSV from DuckDB (design.md D2: CSV equals exactly what user sees)
      const filters = {
        resourceIds: filterState.resource_ids.length > 0 ? filterState.resource_ids : undefined,
        bigCategories: chartFilter.value.big_category ? [chartFilter.value.big_category] : undefined,
        statusTypes: chartFilter.value.status_types && chartFilter.value.status_types.length > 0
          ? chartFilter.value.status_types
          : undefined,
      };
      try {
        await duckdb.exportCsv(filters, 'equipment');
      } catch (err) {
        // E-3: surface export failures to the user rather than silently swallowing them
        duckdbError.value = '匯出失敗，請重試';
      }
      return;
    }
    await exportEquipmentDetailCsv();
  } finally {
    exportingEquipment.value = false;
  }
}

/** draftFilters is a local reactive copy; filterState is the committed state managed by useFilterState */
const draftFilters = reactive<FilterState>({
  workcenter_groups: [],
  locations: [],
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
  draftFilters.locations = [...filterState.locations];
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
  // R-1: guard against double-activation while a parquet load/merge or async job is already in flight
  if (duckdb.state.value === 'loading') {
    return;
  }

  const body = buildQueryBody();
  if (!body.start_date || !body.end_date) {
    return;
  }
  // Clear cross-filter and Tier 3 cache on re-query (DQ-3)
  chartFilter.value = { big_category: null, status_types: null };
  clearTierThreeCache();
  duckdbError.value = '';

  // Deactivate any existing DuckDB session before re-query
  if (duckdb.state.value === 'ready') {
    duckdb.deactivate();
  }

  await executePrimaryQuery(body);

  // Browser-DuckDB path: server returned spool URLs → activate DuckDB-WASM
  if (duckdbSpoolUrls.value) {
    duckdbLoading.value = true;
    try {
      await duckdb.activate(
        duckdbSpoolUrls.value.base_spool_url,
        duckdbSpoolUrls.value.jobs_spool_url,
        duckdbSpoolUrls.value.taxonomy,
        duckdbSpoolUrls.value.resource_lookup ?? {}
      );
      // Populate view data from local DuckDB (zero round-trips)
      await refreshDuckdbViews();
    } catch (err) {
      duckdbError.value = duckdb.errorMessage.value || String((err as Error)?.message ?? err);
    } finally {
      duckdbLoading.value = false;
    }
    return; // Skip legacy equipment-detail API call
  }

  // Flag-off / legacy path: load equipment detail from server
  await loadAllEquipmentDetail({ big_category: null, status_types: null });
}

/**
 * Refresh all view data from local DuckDB (called after activate() and on filter changes).
 * Replaces server API calls to /view, /equipment-detail, /event-detail.
 * Zero API round-trips per filter change (AC-5).
 */
async function refreshDuckdbViews(): Promise<void> {
  if (duckdb.state.value !== 'ready') return;

  const filters = {
    resourceIds: filterState.resource_ids.length > 0 ? filterState.resource_ids : undefined,
    bigCategories: chartFilter.value.big_category ? [chartFilter.value.big_category] : undefined,
    statusTypes: chartFilter.value.status_types && chartFilter.value.status_types.length > 0
      ? chartFilter.value.status_types
      : undefined,
  };

  try {
    const [kpi, trend, categories, equipment, topReasons] = await Promise.all([
      duckdb.queryKpi(filters),
      duckdb.queryDailyTrend(filters),
      duckdb.queryBigCategory(filters),
      duckdb.queryEquipmentDetail(filters, 1, 1000),
      duckdb.queryTopReasons(filters, 10),
    ]);

    // Map DuckDB KPI result to summaryData.summary shape
    summaryData.summary = {
      total_hours: kpi.total_hours,
      udt_hours: kpi.udt_hours,
      sdt_hours: kpi.sdt_hours,
      egt_hours: kpi.egt_hours,
      event_count: kpi.event_count,
      avg_event_min: kpi.avg_event_min,
    };

    // Map DuckDB trend rows to summaryData.daily_trend shape
    summaryData.daily_trend = trend.map((r) => ({
      date: r.date,
      udt_hours: r.udt_hours,
      sdt_hours: r.sdt_hours,
      egt_hours: r.egt_hours,
      total_hours: r.total_hours,
    }));

    // Map BigCategory rows
    summaryData.big_category = categories.map((r) => ({
      category: r.category,
      hours: r.hours,
      event_count: r.event_count,
      pct: r.pct,
    }));

    // ES-1: populate top_reasons from DuckDB so TopReasonsTable is not permanently blank in DuckDB mode
    summaryData.top_reasons = topReasons.map((r) => ({
      reason: r.reason,
      status: r.status,
      big_category: r.big_category,
      hours: r.total_hours,
      event_count: r.event_count,
      avg_min: r.avg_min,
    }));

    // Map equipment detail rows
    equipmentData.rows = equipment.data.map((r) => ({
      resource_id: r.resource_id,
      resource_name: r.resource_name ?? null,
      workcenter: r.workcenter ?? null,
      family: r.family ?? null,
      udt_hours: r.udt_hours,
      sdt_hours: r.sdt_hours,
      egt_hours: r.egt_hours,
      total_hours: r.total_hours,
      event_count: r.event_count,
      udt_event_count: r.udt_event_count,
      sdt_event_count: r.sdt_event_count,
      egt_event_count: r.egt_event_count,
      top_reason: null,
    }));
    equipmentData.pagination = {
      page: equipment.page,
      page_size: equipment.page_size,
      total_rows: equipment.total,
      total_pages: equipment.total_pages,
    };
  } catch (err) {
    duckdbError.value = String((err as Error)?.message ?? err);
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

function handleDimensionClosed(dimension: string): void {
  // Cross-filter: reload options when a dropdown closes.
  // Exclude the dimension that just closed from its own filter param so
  // the backend doesn't narrow that dimension's options by its own selection.
  const optionsFilter = { ...(draftFilters as Record<string, unknown>) };
  optionsFilter[dimension] = [];
  void loadOptions(optionsFilter as Record<string, unknown>);
}

async function handleFilterChange(next: FilterState): Promise<void> {
  updateAll(next);
  syncDraftFromState();
  void loadOptions({ ...next });
  await runPrimaryQuery();
}

async function handleClear(): Promise<void> {
  updateAll({
    workcenter_groups: [],
    locations: [],
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
  if (duckdb.state.value === 'ready') {
    // DuckDB path: granularity is not used (daily grouping only per design), re-run views
    await refreshDuckdbViews();
    return;
  }
  await applyView(next.granularity, runPrimaryQuery);
}

/** BigCategoryChart sector click: toggle big_category filter, reload equipment, clear Tier 3 */
async function handleCategoryClick(category: string | null): Promise<void> {
  chartFilter.value.big_category = category;
  clearTierThreeCache();
  if (duckdb.state.value === 'ready') {
    // Zero round-trip: re-run DuckDB views with updated chart filter (AC-5)
    await refreshDuckdbViews();
    return;
  }
  await loadAllEquipmentDetail(chartFilter.value);
}

/** DailyTrendChart legend click: toggle status_types filter, reload equipment + chart views, clear Tier 3 */
async function handleStatusClick(statusTypes: string[] | null): Promise<void> {
  chartFilter.value.status_types = statusTypes;
  clearTierThreeCache();
  if (duckdb.state.value === 'ready') {
    // Zero round-trip: re-run DuckDB views with updated chart filter (AC-5)
    await refreshDuckdbViews();
    return;
  }
  await Promise.all([
    loadAllEquipmentDetail(chartFilter.value),
    loadChartFilterView(statusTypes),
  ]);
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
    if (duckdb.state.value === 'ready') {
      // Browser DuckDB path: query event detail locally (zero round-trip)
      const result = await duckdb.queryEventDetail(
        {
          resourceIds: [resourceId],
          statusTypes: [statusType],
          bigCategories: chartFilter.value.big_category ? [chartFilter.value.big_category] : undefined,
        },
        1,
        200
      );
      // Map to EventDetailRow shape expected by StatusMachineJobTable
      tierThreeCache[key] = {
        rows: result.data.map((e) => ({
          event_id: e.event_id,
          resource_id: e.resource_id,
          resource_name: duckdbSpoolUrls.value?.resource_lookup?.[e.resource_id]?.resource_name ?? null,
          status: e.status,
          reason: e.reason,
          category: e.category,
          start_ts: e.start_ts,
          end_ts: e.end_ts,
          hours: e.hours,
          match_source: e.match_source,
          job: e.job ? {
            job_id: e.job.job_id,
            job_order_name: e.job.job_order_name,
            job_model: e.job.job_model,
            symptom: e.job.symptom,
            cause: e.job.cause,
            repair: e.job.repair,
            wait_min: e.job.wait_min,
            repair_min: e.job.repair_min,
            wait_assign_min: e.job.wait_assign_min,
            wait_ack_min: e.job.wait_ack_min,
            inspect_min: e.job.inspect_min,
            close_wait_min: e.job.close_wait_min,
            job_create_date: e.job.job_create_date,
            job_complete_date: e.job.job_complete_date,
            handler: e.job.handler,
            match_ambiguous: e.job.match_ambiguous,
          } : null,
        })),
        loading: false,
        loaded: true,
        error: '',
      };
      return;
    }
    // Legacy server path
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
        @dimension-closed="handleDimensionClosed"
        @update-state="handleUpdateState"
        @clear="handleClear"
      />

      <!-- Error banner: legacy API error -->
      <ErrorBanner :message="error" :dismissible="false" />

      <!-- DuckDB error banner: WASM init / parquet fetch / merge failure (AC-7, D3, E-1) -->
      <!-- Copy is classified by errorKind for actionable user guidance -->
      <ErrorBanner
        v-if="duckdb.state.value === 'error' || duckdbError"
        :message="duckdbError || (
          duckdb.errorKind.value === 'fetch'     ? '資料快取已過期，請重新查詢' :
          duckdb.errorKind.value === 'wasm_init' ? '瀏覽器分析加速初始化失敗，請使用 Chrome 或 Edge' :
          duckdb.errorKind.value === 'compute'   ? '本地資料處理失敗，請縮小日期範圍後重試' :
          duckdb.errorMessage.value || '分析資料載入失敗'
        )"
        :dismissible="false"
        aria-label="DuckDB 分析錯誤"
      />

      <!-- Async query progress bar (shown when POST /api/downtime-analysis/query returns 202) -->
      <!-- AC-5: only shown for long-range queries; short-range path is unchanged -->
      <AsyncQueryProgress
        :active="asyncJobProgress.active"
        :progress="asyncJobProgress.progress"
        :pct="asyncJobProgress.pct"
        :elapsed-seconds="asyncJobProgress.elapsedSeconds"
        :status="asyncJobProgress.status"
        :can-cancel="true"
        @cancel="cancelAsyncJob"
      />

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
              :category-color-map="categoryColorMap"
              @click-category="handleCategoryClick"
            />
          </div>
        </div>
      </div>

      <!-- Top reasons table -->
      <div class="section-card">
        <div class="section-inner">
          <TopReasonsTable :rows="summaryData.top_reasons" :category-color-map="categoryColorMap" />
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

    <!-- Page-level loading overlay: initial page load or DuckDB parquet download/merge -->
    <LoadingOverlay v-if="(isInitialLoad || loading.initial || duckdbLoading) && !asyncJobProgress.active" tier="page" />
  </div>
</template>
