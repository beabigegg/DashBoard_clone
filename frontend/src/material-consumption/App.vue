<script setup lang="ts">
/**
 * App.vue — material-consumption (料號用量報表)
 * Change: material-part-consumption
 *
 * Root element class: theme-material-consumption (required for CSS scoping Rule 6)
 * Orchestrates: FilterPanel → KpiCards → ConsumptionTrendChart → TypeBreakdownChart → DetailTable
 */
import { computed, onMounted, ref } from 'vue';
import { apiGet } from '../core/api';
import BlockLoadingState from '../shared-ui/components/BlockLoadingState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import ConsumptionTrendChart from './components/ConsumptionTrendChart.vue';
import DetailTable from './components/DetailTable.vue';
import FilterPanel from './components/FilterPanel.vue';
import TypeBreakdownChart from './components/TypeBreakdownChart.vue';
import { useConsumptionQuery } from './composables/useConsumptionQuery';
import type { QueryParams, Granularity } from './composables/useConsumptionQuery';

// --- Filter options state ---
const partOptions = ref<Array<{ name: string; description?: string | null }>>([]);
const filterOptionsLoading = ref(false);
const filterOptionsError = ref('');

// --- Active type filter (persists across granularity changes) ---
const currentTypes = ref<string[]>([]);

// --- Composable ---
const {
  queryId,
  kpi,
  trend,
  typeBreakdown,
  isSummaryLoading,
  isViewLoading,
  summaryError,
  currentGranularity,
  submitQuery,
  applyView,
  detailQueryId,
  detailRows,
  detailPagination,
  isDetailLoading,
  detailError,
  isDetailAsync,
  submitDetail,
  fetchPage,
  exportCsv,
} = useConsumptionQuery();

// typeOptions derived from the current query result — only types present in the queried data
const typeOptions = computed(() => {
  const seen = new Set<string>();
  for (const item of typeBreakdown.value) {
    const t = item.pj_type ?? '(未分類)';
    seen.add(t);
  }
  return [...seen].sort();
});

// --- Active tab ---
const activeTab = ref<'charts' | 'detail'>('charts');

// --- Current query params (stored for re-submit detail) ---
const currentQueryParams = ref<QueryParams | null>(null);

// --- Server-side sort state (resets on new query; drives DuckDB ORDER BY) ---
const activeSortKey = ref('');
const activeSortDir = ref('asc');

// --- Load filter options ---
async function loadFilterOptions() {
  filterOptionsLoading.value = true;
  filterOptionsError.value = '';
  try {
    const res = await apiGet<{
      parts: Array<{ name: string; description?: string | null }>;
    }>('/api/material-consumption/filter-options', { timeout: 30000 });

    if (!res.success) {
      filterOptionsError.value =
        (res as { error?: { message?: string } }).error?.message || '篩選條件載入失敗';
      return;
    }
    const data = res.data!;
    partOptions.value = data.parts ?? [];
  } catch (err) {
    filterOptionsError.value = err instanceof Error ? err.message : '篩選條件載入失敗';
  } finally {
    filterOptionsLoading.value = false;
  }
}

// --- Handle query submit ---
async function handleQuerySubmit(params: QueryParams) {
  currentQueryParams.value = params;
  activeTab.value = 'charts';
  // Reset sort state so header indicator clears on new query
  activeSortKey.value = '';
  activeSortDir.value = 'asc';
  await submitQuery(params);
  // Auto-trigger detail query after summary succeeds (no extra button needed)
  if (queryId.value) {
    void submitDetail(params);
  }
}

// --- Handle granularity change (NO re-query — AC-3 / MC-03) ---
async function handleGranularityChange(g: Granularity) {
  currentGranularity.value = g;
  if (!queryId.value) return;
  await applyView(g, currentTypes.value.length > 0 ? currentTypes.value : undefined);
}

// --- Handle type filter change (fires GET /view — NOT a new POST /query) ---
async function handleTypeChange(types: string[]) {
  currentTypes.value = types;
  if (!queryId.value) return; // no query submitted yet; skip API call
  await applyView(currentGranularity.value, types.length > 0 ? types : undefined);
}

// --- Handle reset ---
function handleReset() {
  currentQueryParams.value = null;
  currentTypes.value = [];
  activeSortKey.value = '';
  activeSortDir.value = 'asc';
}

// --- Handle page change (preserves current sort) ---
async function handlePageChange(page: number) {
  await fetchPage(page, activeSortKey.value, activeSortDir.value);
}

// --- Handle sort (server-side: re-fetch page 1 with new ORDER BY) ---
async function handleSort(payload: { key: string; direction: string }) {
  activeSortKey.value = payload.key;
  activeSortDir.value = payload.direction;
  await fetchPage(1, payload.key, payload.direction);
}

// --- Handle CSV export ---
async function handleExportCsv() {
  if (!currentQueryParams.value) return;
  await exportCsv(currentQueryParams.value);
}

// --- Lifecycle ---
onMounted(() => {
  loadFilterOptions();
});
</script>

<template>
  <div class="dashboard theme-material-consumption">

    <!-- Filter options error (inline) -->
    <ErrorBanner
      :message="filterOptionsError"
      @dismiss="filterOptionsError = ''"
    />

    <!-- Summary query error -->
    <ErrorBanner
      :message="summaryError"
      @dismiss="summaryError = ''"
    />

    <!-- Detail error -->
    <ErrorBanner
      :message="detailError"
      @dismiss="detailError = ''"
    />

    <!-- Initial page loading overlay -->
    <LoadingOverlay v-if="filterOptionsLoading" tier="page" />

    <!-- Filter panel -->
    <div class="ui-card filter-query-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
      </div>
      <div class="ui-card-body">
        <FilterPanel
          :part-options="partOptions"
          :loading="isSummaryLoading"
          @query-submit="handleQuerySubmit"
          @granularity-change="handleGranularityChange"
          @reset="handleReset"
        />
      </div>
    </div>

    <!-- Loading overlay for initial summary query (page-level: "初始化全局等待" only) -->
    <LoadingOverlay v-if="isSummaryLoading" tier="page" />

    <!-- Results section (shown after first successful query) -->
    <template v-if="queryId">
      <!-- KPI Cards -->
      <div class="ui-card kpi-cards">
        <div class="ui-card-body">
          <SummaryCardGroup :columns="5">
            <SummaryCard
              label="總實扣量"
              :value="kpi?.total_consumed ?? null"
              format="number"
            />
            <SummaryCard
              label="總應扣量"
              :value="kpi?.total_required ?? null"
              format="number"
            />
            <SummaryCard
              label="消耗效率"
              :value="kpi?.efficiency_pct ?? null"
              format="percent"
            />
            <SummaryCard
              label="LOT 數"
              :value="kpi?.lot_count ?? null"
              format="number"
            />
            <SummaryCard
              label="工單數"
              :value="kpi?.workorder_count ?? null"
              format="number"
            />
          </SummaryCardGroup>
        </div>
      </div>

      <!-- Type filter — post-query DuckDB view filter (no Oracle re-query, MC-03) -->
      <div v-if="typeOptions.length > 0" class="ui-card type-filter-card">
        <div class="ui-card-body type-filter-row">
          <span class="filter-label type-filter-label">Type 篩選</span>
          <div class="type-filter-select">
            <MultiSelect
              :model-value="currentTypes"
              :options="typeOptions"
              placeholder="全部類型"
              :disabled="isViewLoading || isSummaryLoading"
              @update:model-value="handleTypeChange"
            />
          </div>
        </div>
      </div>

      <!-- Tab navigation — WAI-ARIA tab widget (BLOCKING-2) -->
      <div class="tab-bar" role="tablist" aria-label="報表檢視">
        <button
          id="tab-charts"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'charts'"
          aria-controls="panel-charts"
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'charts' }"
          data-testid="tab-charts"
          @click="activeTab = 'charts'"
        >
          趨勢圖表
        </button>
        <button
          id="tab-detail"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'detail'"
          aria-controls="panel-detail"
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'detail' }"
          data-testid="tab-detail"
          @click="activeTab = 'detail'"
        >
          明細資料
        </button>
      </div>

      <!-- Charts tab panel -->
      <div
        id="panel-charts"
        role="tabpanel"
        aria-labelledby="tab-charts"
        v-show="activeTab === 'charts'"
      >
        <!-- Trend chart — block-level loading during granularity switch (BLOCKING-1) -->
        <div class="ui-card">
          <div class="ui-card-body">
            <BlockLoadingState v-if="isViewLoading" text="重新計算中..." />
            <ConsumptionTrendChart
              v-else
              :trend="trend"
              :loading="false"
              :part-options="partOptions"
            />
          </div>
        </div>

        <!-- Type breakdown chart — block-level loading during granularity switch (BLOCKING-1) -->
        <div class="ui-card">
          <div class="ui-card-body">
            <BlockLoadingState v-if="isViewLoading" text="重新計算中..." />
            <TypeBreakdownChart
              v-else
              :trend="trend"
              :loading="false"
              :part-options="partOptions"
            />
          </div>
        </div>
      </div>

      <!-- Detail tab panel -->
      <div
        id="panel-detail"
        role="tabpanel"
        aria-labelledby="tab-detail"
        v-show="activeTab === 'detail'"
      >
        <div class="ui-card">
          <div class="ui-card-body">
            <DetailTable
              :rows="detailRows"
              :pagination="detailPagination"
              :loading="isDetailLoading"
              :is-async="isDetailAsync"
              :detail-query-id="detailQueryId"
              :active-sort-key="activeSortKey"
              :active-sort-dir="activeSortDir"
              @page-change="handlePageChange"
              @sort="handleSort"
              @export-csv="handleExportCsv"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- Empty state: after query with no results -->
    <div
      v-else-if="!isSummaryLoading && !filterOptionsLoading && currentQueryParams"
      class="empty-state"
      data-testid="empty-state"
    >
      <p>查無資料，請調整查詢條件後重試</p>
    </div>
  </div>
</template>
