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
 * The station-group filter is a SINGLE-select — MultiSelect.vue has no native
 * single-select mode and is additive-only (16 consumers, CLAUDE.md), so this
 * reuses the same fake-single-select idiom the OLD App.vue already used
 * (`:model-value="x ? [x] : []"`).
 *
 * 設定 button navigates to the standalone /production-achievement-settings
 * mini-app (D4, no drawer entry); OD-7 mode/station preservation across that
 * round-trip is handled inside useProductionAchievement.ts (sessionStorage).
 */
import { computed, onMounted, onUnmounted } from 'vue';
import { useProductionAchievement, type ProductionAchievementMode } from './composables/useProductionAchievement';
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
import TargetEditPanel from './components/TargetEditPanel.vue';
import { formatQty, formatAchievementRate, achievementRateForChart } from './utils';
import type { DailyViewRow, CumulativeViewRow } from './composables/useProductionAchievementDuckDB';

const {
  filters,
  filterOptions,
  dailyRows,
  cumulativeRows,
  cumulativeTrend,
  viewKind,
  targets,
  loading,
  error,
  hasQueried,
  editForbidden,
  editError,
  editSaving,
  asyncJobProgress,
  fetchFilterOptions,
  fetchTargets,
  runQuery,
  setMode,
  setWorkcenterGroup,
  setRangeDates,
  saveTarget,
  cancelQuery,
} = useProductionAchievement();

const MODE_OPTIONS: { value: ProductionAchievementMode; label: string }[] = [
  { value: 'today', label: '當日' },
  { value: 'yesterday', label: '前日' },
  { value: 'month', label: '當月' },
  { value: 'range', label: '自訂區間' },
];

onMounted(() => {
  void fetchFilterOptions();
  void fetchTargets();
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

function goToSettings(): void {
  navigateToRuntimeRoute('/production-achievement-settings');
}

async function handleSaveTarget(payload: { shift_code: string; workcenter_group: string; target_qty: number }): Promise<void> {
  await saveTarget(payload);
}

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

// ── KPI cards (OD-11): SUM(actual)/SUM(plan) over the SAME rows already
// rendered in the table/chart below — never an independent re-aggregation. ──
const totalActual = computed(() => currentRows.value.reduce((sum, r) => sum + Number(actualOf(r) || 0), 0));
const rowsWithPlan = computed(() => currentRows.value.filter((r) => planOf(r) !== null));
const totalPlan = computed(() =>
  rowsWithPlan.value.length === 0 ? null : rowsWithPlan.value.reduce((sum, r) => sum + Number(planOf(r) || 0), 0),
);
const overallRate = computed(() => (totalPlan.value === null || totalPlan.value === 0 ? null : totalActual.value / totalPlan.value));

// ── Chart series (shared PlanAchievementStackedChart — daily x=package group, cumulative x=date) ──
const chartCategories = computed(() =>
  viewKind.value === 'daily' ? dailyRows.value.map((r) => r.package_lf_group) : cumulativeTrend.value.map((t) => t.output_date),
);
const chartSeries = computed(() => {
  if (viewKind.value === 'daily') {
    return [
      { name: 'D班', colorVar: 'var(--pa-shift-d)', data: dailyRows.value.map((r) => achievementRateForChart(r.daily_plan_qty ? r.d_output_qty / r.daily_plan_qty : null)) },
      { name: 'N班', colorVar: 'var(--pa-shift-n)', data: dailyRows.value.map((r) => achievementRateForChart(r.daily_plan_qty ? r.n_output_qty / r.daily_plan_qty : null)) },
    ];
  }
  return [{ name: '達成率', colorVar: 'var(--pa-cumulative-rate)', data: cumulativeTrend.value.map((t) => achievementRateForChart(t.achievement_rate)) }];
});
</script>

<template>
  <div class="theme-production-achievement pa-app__page" data-testid="pa-app">
    <!-- Mode + station filter panel -->
    <div class="ui-card pa-filter-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
        <button type="button" class="ui-btn ui-btn--secondary ui-btn--sm" data-testid="pa-settings-btn" @click="goToSettings">
          設定
        </button>
      </div>
      <div class="ui-card-body pa-app__filter-panel">
        <div class="pa-app__mode-switch" role="group" aria-label="查詢模式">
          <button
            v-for="opt in MODE_OPTIONS"
            :key="opt.value"
            type="button"
            class="ui-btn ui-btn--sm"
            :class="filters.mode === opt.value ? 'ui-btn--primary' : 'ui-btn--secondary'"
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

    <!-- Target-value management (always visible per api-contract.md row 258 — no permission gate on read).
         Unchanged panel/wiring — the legacy shift-based target table is untouched by this change. -->
    <TargetEditPanel
      :targets="targets"
      :edit-forbidden="editForbidden"
      :edit-error="editError"
      :edit-saving="editSaving"
      :workcenter-group-options="filterOptions.workcenter_groups"
      @save="handleSaveTarget"
    />

    <!-- Results — suppressed on error: ErrorBanner above is the sole message
         then, instead of also showing a contradictory empty table. -->
    <template v-if="showResults">
      <SummaryCardGroup :columns="3" data-testid="pa-kpi-cards">
        <SummaryCard label="實際產出合計" :value="totalActual" format="number" accent="brand" />
        <SummaryCard label="計畫合計" :value="totalPlan" format="number" accent="info" />
        <SummaryCard label="整體達成率" :value="overallRate !== null ? overallRate * 100 : null" format="percent" accent="success" />
      </SummaryCardGroup>

      <PlanAchievementStackedChart
        :title="viewKind === 'daily' ? '每日達成率' : '累計達成率趨勢'"
        :categories="chartCategories"
        :series="chartSeries"
        :category-axis-name="viewKind === 'daily' ? '包裝群組' : '日期'"
      />

      <div class="ui-card">
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
            <DataTableColumn column-key="package_lf_group" label="包裝群組" sortable />
            <DataTableColumn column-key="d_output_qty" label="D班產出" align="right" sortable />
            <DataTableColumn column-key="n_output_qty" label="N班產出" align="right" sortable />
            <DataTableColumn column-key="daily_output_qty" label="每日產出" align="right" sortable />
            <DataTableColumn column-key="daily_plan_qty" label="每日計畫" align="right" sortable />
            <DataTableColumn column-key="achievement_rate" label="每日達成率" align="right" sortable />
            <template #cell="{ columnKey, value }">
              <template v-if="['d_output_qty', 'n_output_qty', 'daily_output_qty', 'daily_plan_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
              <template v-else-if="columnKey === 'achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
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
            <DataTableColumn column-key="package_lf_group" label="包裝群組" sortable />
            <DataTableColumn column-key="cumulative_plan_qty" label="累計計畫" align="right" sortable />
            <DataTableColumn column-key="cumulative_actual_qty" label="累計產出" align="right" sortable />
            <DataTableColumn column-key="cumulative_diff_qty" label="累計差異" align="right" sortable />
            <DataTableColumn column-key="cumulative_achievement_rate" label="累計達成率" align="right" sortable />
            <template #cell="{ columnKey, value }">
              <template v-if="['cumulative_plan_qty', 'cumulative_actual_qty', 'cumulative_diff_qty'].includes(columnKey)">{{ formatQty(value as number | null) }}</template>
              <template v-else-if="columnKey === 'cumulative_achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
              <template v-else>{{ value }}</template>
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
