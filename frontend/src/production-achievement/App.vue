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
 *
 * Change: production-achievement-column-pivot (X-direction 子站 grouping).
 * Expanded (大項) mode (電鍍/切割) used to render Y-direction (row-based): one
 * row per (Package Group,子站) leaf pair PLUS a per-package 大項小計 subtotal
 * row. It now renders X-direction (column-based), matching the Excel
 * reference report: one row per Package Group with separate COLUMNS per子站
 * (e.g. "掛鍍 D班轉出", "條鍍 D班轉出", ...) plus trailing columns for the
 * 大項-level totals — DataTable.vue's row/column model has no notion of
 * per-substation COLUMNS (only rows), so this is a bespoke hand-rolled
 * `<table>` local to this page (see the `pa-app__expanded-*` markup below),
 * NOT a DataTable extension. The single-layer (`!isExpandedSelection`)
 * DataTable path is completely untouched.
 *
 * Change: production-achievement-sync-time. Small freshness readout in the
 * 查詢條件 card header ("同步時間" / "資料最新一筆時間", data-testid
 * `pa-freshness`) sourced from useProductionAchievement's syncTimeLabel/
 * latestDataTimestampLabel — both already null-safe (em-dash fallback) and
 * reset at the start of every runQuery(), so they only ever reflect the
 * MOST RECENTLY completed successful query, never a stale prior one shown
 * through a subsequent in-flight/failed query. Shown uniformly across all 4
 * modes (當日/前日/當月/自訂區間) since the backend returns both fields on
 * every 200 spool-hit regardless of mode — there is no mode-specific gating.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useProductionAchievement, type ProductionAchievementMode, type ProductionSourceMode } from './composables/useProductionAchievement';
import { navigateToRuntimeRoute } from '../core/shell-navigation';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
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
  expandedSubstations,
  syncTimeLabel,
  latestDataTimestampLabel,
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

// -- KPI cards (OD-11): SUM(actual)/SUM(plan) over the SAME rows already
// rendered in the table/chart below -- never an independent re-aggregation.
// Change: production-achievement-column-pivot -- every row (both single-layer
// AND expanded 大項 mode) is now uniformly at the package-total grain (no more
// leaf-vs-subtotal distinction to filter out), so this sums ALL rows directly.
const totalActual = computed(() => currentRows.value.reduce((sum, r) => sum + Number(actualOf(r) || 0), 0));
const rowsWithPlan = computed(() => currentRows.value.filter((r) => planOf(r) !== null));
const totalPlan = computed(() =>
  rowsWithPlan.value.length === 0 ? null : rowsWithPlan.value.reduce((sum, r) => sum + Number(planOf(r) || 0), 0),
);
const overallRate = computed(() => (totalPlan.value === null || totalPlan.value === 0 ? null : totalActual.value / totalPlan.value));

// -- PlanAchievementStackedChart (daily mode only: x=package group, D班/N班 stacked %) --
// Change: production-achievement-column-pivot -- dailyRows.value is now already
// exactly one row per package in BOTH single-layer and expanded 大項 mode (the
// achievement_rate/d_achievement_rate/n_achievement_rate fields always carry
// the package-total, whichever mode), so no per-mode filtering is needed here
// anymore.
const chartRows = computed(() => dailyRows.value);
const chartCategories = computed(() => chartRows.value.map((r) => r.package_lf_group));
// Y-axis stays % (single axis; 計畫 is the y=100 markLine, not a second
// scale). Each series carries its own qtyData so the chart's "% (QTY)"
// label/tooltip can distinguish D班/N班 individually (field-directed spec).
//
// PA-21 fix: each shift's rate divides by its OWN shift_plan_qty
// (CEIL(daily_plan_qty / 2), computed in useProductionAchievementDuckDB.ts)
// via the pre-computed d_/n_achievement_rate fields, not the FULL daily plan
// — dividing a single shift's output by the whole day's target under-counted
// achievement by roughly half.
const chartSeries = computed(() => [
  {
    name: 'D班',
    colorVar: 'var(--pa-shift-d)',
    data: chartRows.value.map((r) => achievementRateForChart(r.d_achievement_rate)),
    qtyData: chartRows.value.map((r) => r.d_output_qty),
  },
  {
    name: 'N班',
    colorVar: 'var(--pa-shift-n)',
    data: chartRows.value.map((r) => achievementRateForChart(r.n_achievement_rate)),
    qtyData: chartRows.value.map((r) => r.n_output_qty),
  },
]);

// ── CumulativeTrendComboChart (當月/自訂區間 only: x=date, bar=每日產出數量, line=累計達成率) ──
const comboCategories = computed(() => cumulativeTrend.value.map((t) => t.output_date));
const comboQtyData = computed(() => cumulativeTrend.value.map((t) => t.actual_qty));
const comboRateData = computed(() => cumulativeTrend.value.map((t) => achievementRateForChart(t.cumulative_achievement_rate)));

// ── Column-pivoted expanded (大項) detail table (production-achievement
// -column-pivot) — bespoke markup, NOT DataTable (see the script-block header
// comment). Each row's `substations` array is matched to `expandedSubstations`
// (the shared ordered列表) BY NAME, defensively, in case the array a row
// carries is ever in a different order than the header's — never assumed to
// be positionally aligned. A substation missing from a row's own
// `substations` array (should not normally happen — every substation under
// the selected 大項 is always represented, defaulting to 0 in the SQL pivot)
// also defaults to 0 here as a second line of defense.
const DAILY_SUBSTATION_FIELDS = ['d_output_qty', 'n_output_qty', 'daily_output_qty'] as const;
type DailySubstationField = (typeof DAILY_SUBSTATION_FIELDS)[number];

function substationDailyValue(row: DailyViewRow, substation: string, field: DailySubstationField): number {
  const entry = (row.substations || []).find((s) => s.workcenter_group === substation);
  return entry ? entry[field] : 0;
}

function substationCumulativeValue(row: CumulativeViewRow, substation: string): number {
  const entry = (row.substations || []).find((s) => s.workcenter_group === substation);
  return entry ? entry.cumulative_actual_qty : 0;
}

// colspan for the expanded-table empty-state row: 1 (Package Group) + 3 per
// substation (D/N/每日 or 累計, daily has 3 cols per sub, cumulative has 1) +
// the trailing parent-total columns.
const dailyExpandedColspan = computed(() => 1 + expandedSubstations.value.length * 3 + 7);
const cumulativeExpandedColspan = computed(() => 1 + expandedSubstations.value.length + 4);
</script>

<template>
  <div class="theme-production-achievement pa-app__page" data-testid="pa-app">
    <!-- Mode + station filter panel -->
    <div class="ui-card pa-filter-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
        <div class="pa-app__header-actions">
          <div class="pa-app__freshness" data-testid="pa-freshness">
            <span class="pa-app__freshness-item">同步時間：{{ syncTimeLabel }}</span>
            <span class="pa-app__freshness-item">資料最新一筆時間：{{ latestDataTimestampLabel }}</span>
          </div>
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
        <SummaryCard :label="`實際${metricNoun}合計 (K)`" :value="totalActual" format="number" accent="brand" />
        <SummaryCard label="計畫合計 (K)" :value="totalPlan" format="number" accent="info" />
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
          <!-- Single-layer station (未展開): unchanged DataTable path. -->
          <template v-if="!isExpandedSelection">
            <DataTable
              v-if="viewKind === 'daily'"
              :data="(dailyRows as unknown as Record<string, unknown>[])"
              :loading="loading"
              empty-type="filter-empty"
              data-testid="pa-report-table"
            >
              <DataTableColumn column-key="package_lf_group" label="Package Group" />
              <DataTableColumn column-key="d_output_qty" :label="`D班${metricNoun} (K)`" align="right" />
              <DataTableColumn column-key="n_output_qty" :label="`N班${metricNoun} (K)`" align="right" />
              <DataTableColumn column-key="daily_output_qty" :label="`每日${metricNoun} (K)`" align="right" />
              <DataTableColumn column-key="daily_plan_qty" label="每日計畫 (K)" align="right" />
              <!-- 班達成率 (PA-21): each shift's output ÷ its own shift target
                   (CEIL(每日計畫/2)) — the same values the grouped chart bars plot,
                   shown per-shift alongside the whole-day 每日達成率. -->
              <DataTableColumn column-key="d_achievement_rate" label="D班達成率" align="right" />
              <DataTableColumn column-key="n_achievement_rate" label="N班達成率" align="right" />
              <DataTableColumn column-key="achievement_rate" label="每日達成率" align="right" />
              <template #cell="{ columnKey, value }">
                <template v-if="['d_output_qty', 'n_output_qty', 'daily_output_qty', 'daily_plan_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
                <template v-else-if="['achievement_rate', 'd_achievement_rate', 'n_achievement_rate'].includes(columnKey)">{{ formatAchievementRate(value as number | null) }}</template>
                <template v-else>{{ value }}</template>
              </template>
            </DataTable>

            <DataTable
              v-else
              :data="(cumulativeRows as unknown as Record<string, unknown>[])"
              :loading="loading"
              empty-type="filter-empty"
              data-testid="pa-report-table"
            >
              <DataTableColumn column-key="package_lf_group" label="Package Group" />
              <DataTableColumn column-key="cumulative_plan_qty" label="累計計畫 (K)" align="right" />
              <DataTableColumn column-key="cumulative_actual_qty" :label="`累計${metricNoun} (K)`" align="right" />
              <DataTableColumn column-key="cumulative_diff_qty" label="累計差異 (K)" align="right" />
              <DataTableColumn column-key="cumulative_achievement_rate" label="累計達成率" align="right" />
              <template #cell="{ columnKey, value }">
                <template v-if="['cumulative_plan_qty', 'cumulative_actual_qty', 'cumulative_diff_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
                <template v-else-if="columnKey === 'cumulative_achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
                <template v-else>{{ value }}</template>
              </template>
            </DataTable>
          </template>

          <!-- Expanded 大項 (電鍍/切割): bespoke column-pivoted table — one row per
               Package Group, separate COLUMNS per子站 (production-achievement
               -column-pivot; NOT DataTable, see script-block header comment). -->
          <template v-else>
            <div v-if="viewKind === 'daily'" class="pa-app__expanded-table-wrap">
              <table class="pa-app__expanded-table" data-testid="pa-expanded-daily-table">
                <thead>
                  <tr>
                    <th class="pa-app__expanded-th pa-app__expanded-th--sticky">Package Group</th>
                    <template v-for="sub in expandedSubstations" :key="`h-${sub}`">
                      <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ sub }} D班{{ metricNoun }} (K)</th>
                      <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ sub }} N班{{ metricNoun }} (K)</th>
                      <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ sub }} 每日{{ metricNoun }} (K)</th>
                    </template>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ filters.workcenter_group }} D班{{ metricNoun }}總計 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ filters.workcenter_group }} N班{{ metricNoun }}總計 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ filters.workcenter_group }} 每日{{ metricNoun }}總計 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">每日計畫 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">D班達成率</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">N班達成率</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">每日達成率</th>
                  </tr>
                </thead>
                <tbody v-if="dailyRows.length">
                  <tr v-for="row in dailyRows" :key="row.package_lf_group" class="pa-app__expanded-row" data-testid="pa-expanded-row">
                    <td class="pa-app__expanded-td pa-app__expanded-td--sticky">{{ row.package_lf_group }}</td>
                    <template v-for="sub in expandedSubstations" :key="`d-${row.package_lf_group}-${sub}`">
                      <td class="pa-app__expanded-td pa-app__expanded-td--right">{{ formatQty(substationDailyValue(row, sub, 'd_output_qty')) }}</td>
                      <td class="pa-app__expanded-td pa-app__expanded-td--right">{{ formatQty(substationDailyValue(row, sub, 'n_output_qty')) }}</td>
                      <td class="pa-app__expanded-td pa-app__expanded-td--right">{{ formatQty(substationDailyValue(row, sub, 'daily_output_qty')) }}</td>
                    </template>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.d_output_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.n_output_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.daily_output_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.daily_plan_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatAchievementRate(row.d_achievement_rate) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatAchievementRate(row.n_achievement_rate) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatAchievementRate(row.achievement_rate) }}</td>
                  </tr>
                </tbody>
                <tbody v-else>
                  <tr>
                    <td :colspan="dailyExpandedColspan" class="pa-app__expanded-empty-cell">
                      <EmptyState type="filter-empty" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else class="pa-app__expanded-table-wrap">
              <table class="pa-app__expanded-table" data-testid="pa-expanded-cumulative-table">
                <thead>
                  <tr>
                    <th class="pa-app__expanded-th pa-app__expanded-th--sticky">Package Group</th>
                    <th v-for="sub in expandedSubstations" :key="`h-${sub}`" class="pa-app__expanded-th pa-app__expanded-th--right">{{ sub }} 累計{{ metricNoun }} (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">累計計畫 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">{{ filters.workcenter_group }} 累計{{ metricNoun }}總計 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">累計差異 (K)</th>
                    <th class="pa-app__expanded-th pa-app__expanded-th--right">累計達成率</th>
                  </tr>
                </thead>
                <tbody v-if="cumulativeRows.length">
                  <tr v-for="row in cumulativeRows" :key="row.package_lf_group" class="pa-app__expanded-row" data-testid="pa-expanded-row">
                    <td class="pa-app__expanded-td pa-app__expanded-td--sticky">{{ row.package_lf_group }}</td>
                    <td v-for="sub in expandedSubstations" :key="`c-${row.package_lf_group}-${sub}`" class="pa-app__expanded-td pa-app__expanded-td--right">
                      {{ formatQty(substationCumulativeValue(row, sub)) }}
                    </td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.cumulative_plan_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.cumulative_actual_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatQty(row.cumulative_diff_qty) }}</td>
                    <td class="pa-app__expanded-td pa-app__expanded-td--right pa-app__expanded-td--total">{{ formatAchievementRate(row.cumulative_achievement_rate) }}</td>
                  </tr>
                </tbody>
                <tbody v-else>
                  <tr>
                    <td :colspan="cumulativeExpandedColspan" class="pa-app__expanded-empty-cell">
                      <EmptyState type="filter-empty" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </div>
    </template>

    <div v-else-if="!hasQueried && !loading" class="pa-app__empty-state" data-testid="pa-empty-state">
      正在載入生產達成率資料…
    </div>

    <LoadingOverlay v-if="showPageLoading" tier="page" />
  </div>
</template>
