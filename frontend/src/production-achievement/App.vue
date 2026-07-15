<script setup lang="ts">
/**
 * 生產達成率 (Production Achievement Rate) report page.
 *
 * Change: production-achievement-overhaul (IP-8). Rewritten from a free-form
 * date-range + shift/station filter query into the design.md 2×2 view model:
 * 4-button mode switch (當日/前日/當月/自訂區間, default 當日) drives BOTH the
 * date window and which computed view renders — DailyView (當日/前日: rows =
 * PACKAGE_LF group, columns = D/N/合計/計畫/達成率) or CumulativeView
 * (當月/自訂區間: rows = PACKAGE_LF group, columns = 累計計畫/產出/差異/達成率),
 * sharing PlanAchievementStackedChart.vue for the chart. All auto-run — OD-3 —
 * no 查詢/清除篩選 buttons. OD-1: no shift filter (D/N are columns only).
 *
 * The station-group filter is a SINGLE-select — MultiSelect.vue's
 * `single-select` prop (additive opt-in, checkbox list becomes radio-style
 * and picking an option closes the dropdown immediately) is used instead of
 * the old fake-single-select idiom that let the underlying widget show
 * checkboxes while only the first checked value was ever applied — that
 * mismatch between "looks multi-select" and "behaves single-select" read as
 * broken to users.
 *
 * 設定 button navigates to the standalone /production-achievement-settings
 * mini-app (D4, no drawer entry); OD-7 mode/station preservation across that
 * round-trip is handled inside useProductionAchievement.ts (sessionStorage).
 */
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useProductionAchievement, type ProductionAchievementMode, type ProductionSourceMode } from './composables/useProductionAchievement';
import { navigateToRuntimeRoute } from '../core/shell-navigation';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import PlanAchievementStackedChart from './components/PlanAchievementStackedChart.vue';
import CumulativeTrendComboChart from './components/CumulativeTrendComboChart.vue';
import { formatQty, formatAchievementRate, achievementRateForChart } from './utils';
import type { DailyViewRow, CumulativeViewRow } from './composables/useProductionAchievementDuckDB';

const {
  filters,
  filterOptions,
  dailyRows,
  cumulativeRows,
  cumulativeTrend,
  viewKind,
  loading,
  error,
  hasQueried,
  asyncJobProgress,
  isExpandedSelection,
  fetchFilterOptions,
  runQuery,
  refreshQuery,
  setMode,
  setSource,
  setWorkcenterGroup,
  setRangeDates,
  cancelQuery,
  checkSettingsAccess,
} = useProductionAchievement();

const MODE_OPTIONS: { value: ProductionAchievementMode; label: string }[] = [
  { value: 'today', label: '當日' },
  { value: 'yesterday', label: '前日' },
  { value: 'month', label: '當月' },
  { value: 'range', label: '自訂區間' },
];

// PA-18: 產出 (equipment track-out, 焊接/成型 only) vs 轉出 (lot move-out, all
// stations). Data-source TAB — switching re-fetches a wholly different dataset.
const SOURCE_OPTIONS: { value: ProductionSourceMode; label: string }[] = [
  { value: 'output', label: '產出' },
  { value: 'moveout', label: '轉出' },
];

onMounted(() => {
  void fetchFilterOptions();
  void runQuery(); // OD-3: land on 當日 (or the OD-7 persisted mode) and auto-run immediately
});

// Avoid a zombie poll/timer if the user navigates away mid-query.
onUnmounted(() => {
  void cancelQuery();
});

// Full-page overlay only for the pre-poll phase — once the async job is
// enqueued, AsyncQueryProgress replaces it so the page stays interactive.
const showPageLoading = computed(() => loading.value && !asyncJobProgress.active);

// Once a query has run, only render the summary/chart/table when it actually
// SUCCEEDED (no error) — otherwise ErrorBanner above is the sole message,
// instead of also showing a contradictory "no matching data" empty table
// underneath a "service unavailable" banner. A genuine zero-row *success*
// still renders normally — DataTable's own empty-type="filter-empty" state.
const showResults = computed(() => hasQueried.value && !error.value);

function handleRangeStartChange(e: Event): void {
  const value = (e.target as HTMLInputElement).value;
  setRangeDates(value, filters.end_date);
}

function handleRangeEndChange(e: Event): void {
  const value = (e.target as HTMLInputElement).value;
  setRangeDates(filters.start_date, value);
}

// PA-17: pre-check permission before navigating -- a not-whitelisted user
// sees an inline message instead of a wasted round-trip into a page they
// can only read. Does not change the settings page's own route-level
// visibility (still readable via direct URL by any released user).
const settingsAccessMessage = ref('');
const settingsAccessChecking = ref(false);

async function goToSettings(): Promise<void> {
  if (settingsAccessChecking.value) return;
  settingsAccessMessage.value = '';
  settingsAccessChecking.value = true;
  try {
    const result = await checkSettingsAccess();
    if (result === 'allowed') {
      navigateToRuntimeRoute('/production-achievement-settings');
    } else if (result === 'denied') {
      settingsAccessMessage.value = '您沒有權限進入此設定頁面，請聯絡管理員申請權限';
    } else {
      settingsAccessMessage.value = '權限查詢失敗，請稍後再試';
    }
  } finally {
    settingsAccessChecking.value = false;
  }
}

function dismissSettingsAccessMessage(): void {
  settingsAccessMessage.value = '';
}

// 重新查詢 button: 當日/前日/當月 only (自訂區間 already re-runs on every date
// input change, so it doesn't need a separate manual trigger).
const showRefreshButton = computed(() => filters.mode !== 'range');

// PA-18: the actual-value noun follows the data source (產出 / 轉出) so the
// KPI/table labels read correctly in both TABs.
const metricNoun = computed(() => (filters.source === 'moveout' ? '轉出' : '產出'));

// ── Row helpers shared by table + chart + KPI (single source per OD-11) ────
type ViewRow = DailyViewRow | CumulativeViewRow;

const currentRows = computed<ViewRow[]>(() => (viewKind.value === 'daily' ? dailyRows.value : cumulativeRows.value));

function actualOf(row: ViewRow): number {
  return 'daily_output_qty' in row ? row.daily_output_qty : row.cumulative_actual_qty;
}
function planOf(row: ViewRow): number | null {
  return 'daily_plan_qty' in row ? row.daily_plan_qty : row.cumulative_plan_qty;
}
function rateOf(row: ViewRow): number | null {
  return 'achievement_rate' in row ? row.achievement_rate : row.cumulative_achievement_rate;
}
// PA-19: the per-package 大項小計 row (expanded 電鍍/切割 mode) is a ROLLUP of its
// 子站 leaf rows — it must be excluded from any SUM(actual) so the leaf rows are
// counted exactly once. It is the ONLY row carrying the 大項 plan, so plan sums
// key off it naturally.
function isSubtotalRow(row: ViewRow): boolean {
  return 'is_subtotal' in row && row.is_subtotal === true;
}

// ── KPI cards (OD-11): SUM(actual)/SUM(plan) over the SAME rows already
// rendered in the table/chart below — never an independent re-aggregation.
// actual sums the LEAF rows only (subtotal rows would double-count); plan sums
// the rows that carry a plan (subtotal rows in expanded mode, leaf rows in
// single-layer) — the two are consistent since a leaf never carries a plan in
// expanded mode. ──
const totalActual = computed(() =>
  currentRows.value.filter((r) => !isSubtotalRow(r)).reduce((sum, r) => sum + Number(actualOf(r) || 0), 0),
);
const rowsWithPlan = computed(() => currentRows.value.filter((r) => planOf(r) !== null));
const totalPlan = computed(() =>
  rowsWithPlan.value.length === 0 ? null : rowsWithPlan.value.reduce((sum, r) => sum + Number(planOf(r) || 0), 0),
);
const overallRate = computed(() => (totalPlan.value === null || totalPlan.value === 0 ? null : totalActual.value / totalPlan.value));

// ── PlanAchievementStackedChart (daily mode only: x=package group, D班/N班 stacked %) ──
// In expanded 大項 mode (PA-19) the達成率 lives on the per-package 大項小計 rows
// (子站 leaf rows have no plan), so the chart plots those — one bar per package,
// keyed on the plain package label (subtotals are already unique per package).
// Single-layer mode charts every row.
const chartRows = computed(() =>
  isExpandedSelection.value ? dailyRows.value.filter((r) => r.is_subtotal === true) : dailyRows.value,
);
const chartCategories = computed(() => chartRows.value.map((r) => r.package_lf_group));
// Y-axis stays % (single axis; 計畫 is the y=100 markLine, not a second
// scale). Each series carries its own qtyData so the chart's "% (QTY)"
// label/tooltip can distinguish D班/N班 individually (field-directed spec).
const chartSeries = computed(() => [
  {
    name: 'D班',
    colorVar: 'var(--pa-shift-d)',
    data: chartRows.value.map((r) => achievementRateForChart(r.daily_plan_qty ? r.d_output_qty / r.daily_plan_qty : null)),
    qtyData: chartRows.value.map((r) => r.d_output_qty),
  },
  {
    name: 'N班',
    colorVar: 'var(--pa-shift-n)',
    data: chartRows.value.map((r) => achievementRateForChart(r.daily_plan_qty ? r.n_output_qty / r.daily_plan_qty : null)),
    qtyData: chartRows.value.map((r) => r.n_output_qty),
  },
]);

// ── CumulativeTrendComboChart (當月/自訂區間 only: x=date, bar=每日產出數量, line=累計達成率) ──
const comboCategories = computed(() => cumulativeTrend.value.map((t) => t.output_date));
const comboQtyData = computed(() => cumulativeTrend.value.map((t) => t.actual_qty));
const comboRateData = computed(() => cumulativeTrend.value.map((t) => achievementRateForChart(t.cumulative_achievement_rate)));
</script>

<template>
  <div class="theme-production-achievement pa-app__page" data-testid="pa-app">
    <!-- Mode + station filter panel -->
    <div class="ui-card pa-filter-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
        <div class="pa-app__header-actions">
          <button
            v-if="showRefreshButton"
            type="button"
            class="ui-btn ui-btn--secondary ui-btn--sm"
            data-testid="pa-refresh-btn"
            :disabled="loading"
            @click="refreshQuery"
          >
            重新查詢
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--danger ui-btn--sm"
            data-testid="pa-settings-btn"
            :disabled="settingsAccessChecking"
            @click="goToSettings"
          >
            設定
          </button>
        </div>
      </div>
      <div class="ui-card-body pa-app__filter-panel">
        <ErrorBanner :message="settingsAccessMessage" @dismiss="dismissSettingsAccessMessage" />
        <div class="pa-app__source-switch" role="group" aria-label="資料來源">
          <button
            v-for="opt in SOURCE_OPTIONS"
            :key="opt.value"
            type="button"
            class="pa-app__source-btn"
            :class="{ 'pa-app__source-btn--active': filters.source === opt.value }"
            :aria-pressed="filters.source === opt.value"
            :data-testid="`pa-source-${opt.value}`"
            :disabled="loading"
            @click="setSource(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <div class="pa-app__mode-switch" role="group" aria-label="查詢模式">
          <button
            v-for="opt in MODE_OPTIONS"
            :key="opt.value"
            type="button"
            class="pa-app__mode-btn"
            :class="{ 'pa-app__mode-btn--active': filters.mode === opt.value }"
            :aria-pressed="filters.mode === opt.value"
            :data-testid="`pa-mode-${opt.value}`"
            @click="setMode(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>

        <div class="pa-app__filter-row">
          <div v-if="filters.mode === 'range'" class="ui-filter-group">
            <label for="pa-range-start" class="ui-filter-label">開始日期</label>
            <input
              id="pa-range-start"
              type="date"
              class="pa-app__input"
              data-testid="pa-range-start"
              :value="filters.start_date"
              @change="handleRangeStartChange"
            />
          </div>
          <div v-if="filters.mode === 'range'" class="ui-filter-group">
            <label for="pa-range-end" class="ui-filter-label">結束日期</label>
            <input
              id="pa-range-end"
              type="date"
              class="pa-app__input"
              data-testid="pa-range-end"
              :value="filters.end_date"
              @change="handleRangeEndChange"
            />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">站點群組</label>
            <MultiSelect
              data-testid="pa-workcenter-group"
              :model-value="filters.workcenter_group ? [filters.workcenter_group] : []"
              :options="filterOptions.workcenter_groups"
              placeholder="請選擇站點群組"
              :searchable="true"
              :single-select="true"
              @update:model-value="setWorkcenterGroup(($event as string[])[0] || '')"
            />
          </div>
        </div>
      </div>
    </div>

    <ErrorBanner :message="error || ''" :dismissible="false" />

    <!-- RQ async job progress (202 spool-miss path) — shared across all 4 modes (D5) -->
    <AsyncQueryProgress
      :active="asyncJobProgress.active"
      :progress="asyncJobProgress.progress"
      :pct="asyncJobProgress.pct"
      :elapsed-seconds="asyncJobProgress.elapsedSeconds"
      :status="asyncJobProgress.status"
      @cancel="cancelQuery"
    />

    <!-- Results — suppressed on error: ErrorBanner above is the sole message
         then, instead of also showing a contradictory empty table. -->
    <template v-if="showResults">
      <SummaryCardGroup :columns="3" data-testid="pa-kpi-cards">
        <SummaryCard :label="`實際${metricNoun}合計`" :value="totalActual" format="number" accent="brand" />
        <SummaryCard label="計畫合計" :value="totalPlan" format="number" accent="info" />
        <SummaryCard label="整體達成率" :value="overallRate !== null ? overallRate * 100 : null" format="percent" accent="success" />
      </SummaryCardGroup>

      <PlanAchievementStackedChart
        v-if="viewKind === 'daily'"
        title="每日達成率"
        :categories="chartCategories"
        :series="chartSeries"
        category-axis-name="Package Group"
      />
      <CumulativeTrendComboChart
        v-else
        title="累計達成率趨勢"
        :categories="comboCategories"
        :qty-data="comboQtyData"
        :rate-data="comboRateData"
        category-axis-name="日期"
      />

      <div class="ui-card pa-app__table-card">
        <div class="ui-card-header">
          <span class="ui-card-title">生產達成率明細</span>
        </div>
        <div class="ui-card-body">
          <DataTable
            v-if="viewKind === 'daily'"
            :data="(dailyRows as unknown as Record<string, unknown>[])"
            :loading="loading"
            empty-type="filter-empty"
            data-testid="pa-report-table"
          >
            <!-- Sorting is disabled in expanded 大項 mode so the per-package
                 子站→小計 grouping stays intact (a generic column sort would
                 scatter 大項小計 rows away from their子站). -->
            <DataTableColumn v-if="isExpandedSelection" column-key="workcenter_group" label="子站" :sortable="false" />
            <DataTableColumn column-key="package_lf_group" label="Package Group" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="d_output_qty" :label="`D班${metricNoun}`" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="n_output_qty" :label="`N班${metricNoun}`" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="daily_output_qty" :label="`每日${metricNoun}`" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="daily_plan_qty" label="每日計畫" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="achievement_rate" label="每日達成率" align="right" :sortable="!isExpandedSelection" />
            <template #cell="{ columnKey, value, row }">
              <span :class="{ 'pa-app__subtotal-cell': (row as Record<string, unknown>).is_subtotal === true }">
                <template v-if="columnKey === 'workcenter_group' && (row as Record<string, unknown>).is_subtotal === true">▸ 小計 {{ value }}</template>
                <template v-else-if="['d_output_qty', 'n_output_qty', 'daily_output_qty', 'daily_plan_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
                <template v-else-if="columnKey === 'achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
                <template v-else>{{ value }}</template>
              </span>
            </template>
          </DataTable>

          <DataTable
            v-else
            :data="(cumulativeRows as unknown as Record<string, unknown>[])"
            :loading="loading"
            empty-type="filter-empty"
            data-testid="pa-report-table"
          >
            <!-- Sort disabled in expanded 大項 mode — see the daily table above. -->
            <DataTableColumn v-if="isExpandedSelection" column-key="workcenter_group" label="子站" :sortable="false" />
            <DataTableColumn column-key="package_lf_group" label="Package Group" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="cumulative_plan_qty" label="累計計畫" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="cumulative_actual_qty" :label="`累計${metricNoun}`" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="cumulative_diff_qty" label="累計差異" align="right" :sortable="!isExpandedSelection" />
            <DataTableColumn column-key="cumulative_achievement_rate" label="累計達成率" align="right" :sortable="!isExpandedSelection" />
            <template #cell="{ columnKey, value, row }">
              <span :class="{ 'pa-app__subtotal-cell': (row as Record<string, unknown>).is_subtotal === true }">
                <template v-if="columnKey === 'workcenter_group' && (row as Record<string, unknown>).is_subtotal === true">▸ 小計 {{ value }}</template>
                <template v-else-if="['cumulative_plan_qty', 'cumulative_actual_qty', 'cumulative_diff_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
                <template v-else-if="columnKey === 'cumulative_achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
                <template v-else>{{ value }}</template>
              </span>
            </template>
          </DataTable>
        </div>
      </div>
    </template>

    <div v-else-if="!hasQueried && !loading" class="pa-app__empty-state" data-testid="pa-empty-state">
      正在載入生產達成率資料…
    </div>

    <LoadingOverlay v-if="showPageLoading" tier="page" />
  </div>
</template>
