<script setup lang="ts">
/**
 * 生產達成率 (Production Achievement Rate) report page.
 *
 * Ordinary filterable report — NOT an auto-refresh/big-screen kanban
 * (explicit non-goal, implementation-plan.md IP-7). Modeled on
 * production-history's filter + DataTable/chart pattern.
 *
 * production-achievement-async-spool (ADR-0016): GET .../report is now an
 * always-async spool-backed endpoint (api-contract.md rows 256-261,
 * data-shape-contract.md §3.28) — a spool miss enqueues a background job and
 * polls via the shared AsyncQueryProgress component; a spool hit computes
 * PA-06/PA-07 client-side in DuckDB-WASM (useProductionAchievementDuckDB).
 * The rendered row shape is unchanged — only the data path changed.
 */
import { computed, onMounted, onUnmounted } from 'vue';
import { useProductionAchievement } from './composables/useProductionAchievement';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import AchievementChart from './components/AchievementChart.vue';
import TargetEditPanel from './components/TargetEditPanel.vue';
import { formatQty, formatAchievementRate } from './utils';
import type { ProductionAchievementReportRow } from './composables/useProductionAchievement';

const {
  filters,
  filterOptions,
  rows,
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
  saveTarget,
  resetFilters,
  cancelQuery,
} = useProductionAchievement();

onMounted(async () => {
  await Promise.all([fetchFilterOptions(), fetchTargets()]);
});

// Avoid a zombie poll/timer if the user navigates away mid-query.
onUnmounted(() => {
  void cancelQuery();
});

// Full-page overlay only for the pre-poll phase — once the async job is
// enqueued, AsyncQueryProgress replaces it so the page stays interactive.
const showPageLoading = computed(() => loading.value && !asyncJobProgress.active);

// FIX 1 (UX-1): once a query has run, only render the summary/chart/table
// when it actually SUCCEEDED (no error) — otherwise ErrorBanner above is the
// sole message, instead of also showing a contradictory "no matching data"
// empty table underneath a "service unavailable" banner. A genuine
// zero-row *success* (hasQueried && !error && rows.length === 0) still
// renders normally — DataTable's own empty-type="filter-empty" state.
const showResults = computed(() => hasQueried.value && !error.value);

async function handleQuery(): Promise<void> {
  if (loading.value) return;
  await runQuery();
}

function handleClearFilters(): void {
  resetFilters();
}

async function handleSaveTarget(payload: { shift_code: string; workcenter_group: string; target_qty: number }): Promise<void> {
  await saveTarget(payload);
}

// ── Summary cards ──────────────────────────────────────────────────────────
const totalActual = computed(() =>
  (rows.value || []).reduce((sum: number, r: ProductionAchievementReportRow) => sum + Number(r.actual_output_qty || 0), 0),
);
const groupsWithTarget = computed(() =>
  (rows.value || []).filter((r: ProductionAchievementReportRow) => r.target_qty !== null && r.target_qty !== undefined),
);
const overallAchievementRate = computed(() => {
  const targetSum = groupsWithTarget.value.reduce((sum: number, r: ProductionAchievementReportRow) => sum + Number(r.target_qty || 0), 0);
  if (targetSum === 0) return null;
  const actualSumForTargeted = groupsWithTarget.value.reduce(
    (sum: number, r: ProductionAchievementReportRow) => sum + Number(r.actual_output_qty || 0),
    0,
  );
  return actualSumForTargeted / targetSum;
});
const groupCount = computed(() => new Set((rows.value || []).map((r: ProductionAchievementReportRow) => r.workcenter_group)).size);
</script>

<template>
  <div class="theme-production-achievement pa-app__page" data-testid="pa-app">
    <!-- Filter panel -->
    <div class="ui-card pa-filter-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
      </div>
      <div class="ui-card-body pa-app__filter-panel">
        <div class="pa-app__filter-row">
          <div class="ui-filter-group">
            <label for="pa-start-date" class="ui-filter-label">開始日期 <span class="pa-app__required">*</span></label>
            <input id="pa-start-date" v-model="filters.start_date" type="date" class="pa-app__input" data-testid="pa-start-date" />
          </div>
          <div class="ui-filter-group">
            <label for="pa-end-date" class="ui-filter-label">結束日期 <span class="pa-app__required">*</span></label>
            <input id="pa-end-date" v-model="filters.end_date" type="date" class="pa-app__input" data-testid="pa-end-date" />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">班別</label>
            <MultiSelect
              data-testid="pa-shift-code"
              :model-value="filters.shift_code ? [filters.shift_code] : []"
              :options="filterOptions.shift_codes"
              placeholder="全部"
              :searchable="false"
              @update:model-value="filters.shift_code = ($event as string[])[0] || ''"
            />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">站點群組</label>
            <MultiSelect
              data-testid="pa-workcenter-group"
              :model-value="filters.workcenter_group ? [filters.workcenter_group] : []"
              :options="filterOptions.workcenter_groups"
              placeholder="全部"
              :searchable="true"
              @update:model-value="filters.workcenter_group = ($event as string[])[0] || ''"
            />
          </div>
        </div>

        <div class="pa-app__filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--secondary"
            :disabled="loading"
            data-testid="pa-clear-filters"
            @click="handleClearFilters"
          >
            清除篩選
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            :disabled="loading"
            data-testid="pa-query-btn"
            @click="handleQuery"
          >
            {{ loading ? '查詢中…' : '查詢' }}
          </button>
        </div>
      </div>
    </div>

    <ErrorBanner :message="error || ''" :dismissible="false" />

    <!-- RQ async job progress (202 spool-miss path) — replaces the generic
         loading overlay while the worker fans out; data-shape-contract.md §3.28.4 -->
    <AsyncQueryProgress
      :active="asyncJobProgress.active"
      :progress="asyncJobProgress.progress"
      :pct="asyncJobProgress.pct"
      :elapsed-seconds="asyncJobProgress.elapsedSeconds"
      :status="asyncJobProgress.status"
      @cancel="cancelQuery"
    />

    <!-- Target-value management (always visible per api-contract.md row 258 — no permission gate on read) -->
    <TargetEditPanel
      :targets="targets"
      :edit-forbidden="editForbidden"
      :edit-error="editError"
      :edit-saving="editSaving"
      :workcenter-group-options="filterOptions.workcenter_groups"
      :shift-code-options="filterOptions.shift_codes"
      @save="handleSaveTarget"
    />

    <!-- Results — suppressed on error (FIX 1): ErrorBanner above is the sole
         message then, instead of also showing a contradictory empty table. -->
    <template v-if="showResults">
      <SummaryCardGroup :columns="4">
        <SummaryCard label="實際產出總量" :value="totalActual" format="number" accent="brand" />
        <SummaryCard label="整體達成率" :value="overallAchievementRate !== null ? overallAchievementRate * 100 : null" format="percent" accent="success" />
        <SummaryCard label="站點群組數" :value="groupCount" format="number" accent="info" />
        <SummaryCard label="資料筆數" :value="rows.length" format="number" accent="neutral" />
      </SummaryCardGroup>

      <AchievementChart :rows="rows" />

      <div class="ui-card">
        <div class="ui-card-header">
          <span class="ui-card-title">生產達成率明細</span>
        </div>
        <div class="ui-card-body">
          <DataTable :data="(rows as unknown as Record<string, unknown>[])" :loading="loading" empty-type="filter-empty" data-testid="pa-report-table">
            <DataTableColumn column-key="output_date" label="日期" sortable />
            <DataTableColumn column-key="shift_code" label="班別" sortable />
            <DataTableColumn column-key="workcenter_group" label="站點群組" sortable />
            <DataTableColumn column-key="actual_output_qty" label="實際產出" align="right" sortable />
            <DataTableColumn column-key="target_qty" label="目標值" align="right" sortable />
            <DataTableColumn column-key="achievement_rate" label="達成率" align="right" sortable />
            <template #cell="{ columnKey, value }">
              <template v-if="columnKey === 'actual_output_qty'">{{ formatQty(value as number) }}</template>
              <template v-else-if="columnKey === 'target_qty'">{{ formatQty(value as number | null) }}</template>
              <template v-else-if="columnKey === 'achievement_rate'">{{ formatAchievementRate(value as number | null) }}</template>
              <template v-else>{{ value }}</template>
            </template>
          </DataTable>
        </div>
      </div>
    </template>

    <div v-else-if="!hasQueried && !loading" class="pa-app__empty-state" data-testid="pa-empty-state">
      請選擇日期區間後按「查詢」
    </div>

    <LoadingOverlay v-if="showPageLoading" tier="page" />
  </div>
</template>
