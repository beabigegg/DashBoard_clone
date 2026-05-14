<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import {
  useProductionHistory,
  validateQueryMode,
  buildModePayload,
  type SupplementaryFilterField,
  type MatrixFilter,
  type QueryMode,
} from './composables/useProductionHistory';
import { useFirstTierFilters, type CachedFilterField } from './composables/useFirstTierFilters';
import { ref } from 'vue';
import { useRequestGuard } from '../shared-composables/useRequestGuard';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import ProductionMatrix from './components/ProductionMatrix.vue';
import ProductionDetailTable from './components/ProductionDetailTable.vue';

const {
  loading,
  error,
  datasetId,
  datasetMeta,
  matrixTree,
  matrixMonthColumns,
  matrixLoading,
  matrixFilter,
  supplementaryOptions,
  supplementaryFilter,
  stagedFilter,
  supplementaryOptionsLoading,
  detailRows,
  pagination,
  detailLoading,
  overloadError,
  expiredDataset,
  runQuery,
  fetchPage,
  applyMatrixFilter,
  stageSupplementaryFilter,
  exportCsv: doExportCsv,
  resetResults,
} = useProductionHistory();

// ── First-tier cached cross-filter + wildcard composable ───────────────────
const firstTier = useFirstTierFilters();

const { nextRequestId, isStaleRequest } = useRequestGuard();

// ── Query mode tabs ────────────────────────────────────────────────────────
// The active tab is the SINGLE SOURCE OF TRUTH for which payload fields are
// submitted (proposal.md cross-cutting concern). Tab A = classification,
// Tab B = identifier. Switching tabs clears any pending validation message.
const queryMode = ref<QueryMode>('classification');

function switchMode(mode: QueryMode): void {
  if (queryMode.value === mode) return;
  queryMode.value = mode;
  formError.value = '';
}

// ── Tablist keyboard contract (WAI-ARIA tabs pattern) ──────────────────────
// ArrowLeft/ArrowRight cycle between the two tabs; Home/End jump to first/last.
// Activation follows focus (the standard automatic-activation tabs variant):
// the handler both moves DOM focus and calls switchMode for the target tab.
const MODE_ORDER: QueryMode[] = ['classification', 'identifier'];
const MODE_TAB_IDS: Record<QueryMode, string> = {
  classification: 'ph-mode-tab-classification-btn',
  identifier: 'ph-mode-tab-identifier-btn',
};

function focusMode(mode: QueryMode): void {
  switchMode(mode);
  const el = document.getElementById(MODE_TAB_IDS[mode]);
  if (el) el.focus();
}

function onTablistKeydown(event: KeyboardEvent): void {
  const idx = MODE_ORDER.indexOf(queryMode.value);
  if (idx === -1) return;
  let target: QueryMode | null = null;
  switch (event.key) {
    case 'ArrowLeft':
    case 'ArrowUp':
      target = MODE_ORDER[(idx - 1 + MODE_ORDER.length) % MODE_ORDER.length];
      break;
    case 'ArrowRight':
    case 'ArrowDown':
      target = MODE_ORDER[(idx + 1) % MODE_ORDER.length];
      break;
    case 'Home':
      target = MODE_ORDER[0];
      break;
    case 'End':
      target = MODE_ORDER[MODE_ORDER.length - 1];
      break;
    default:
      return;
  }
  event.preventDefault();
  focusMode(target);
}

// ── Pruning notice (UI-UX REC-02) ──────────────────────────────────────────
// Surfaces fail-open silent drops to the user for ~3 s after a cross-filter
// fetch removes selections. Maps internal field keys to user-visible labels.
const PRUNED_LABELS: Record<CachedFilterField, string> = {
  pj_types: 'Type',
  packages: 'Package',
  bops: 'BOP',
  pj_functions: 'Function',
};
const prunedNotice = ref('');
let _prunedNoticeTimer: ReturnType<typeof setTimeout> | null = null;
const prunedNoticeLabels = computed(() =>
  firstTier.prunedFields.value.map((f) => PRUNED_LABELS[f]).join('、'),
);
watch(
  () => firstTier.prunedFields.value.slice(),
  (fields) => {
    if (!fields.length) {
      prunedNotice.value = '';
      if (_prunedNoticeTimer !== null) {
        clearTimeout(_prunedNoticeTimer);
        _prunedNoticeTimer = null;
      }
      return;
    }
    prunedNotice.value = `篩選自動調整：${prunedNoticeLabels.value}`;
    if (_prunedNoticeTimer !== null) clearTimeout(_prunedNoticeTimer);
    _prunedNoticeTimer = setTimeout(() => {
      _prunedNoticeTimer = null;
      firstTier.clearPrunedFields();
    }, 3000);
  },
);

onMounted(async () => {
  // Load full distinct option set at mount (empty selection → returns indices).
  await firstTier.fetchFilterOptions();
});

// ── Primary query state ────────────────────────────────────────────────────
const formStartDate = ref('');
const formEndDate = ref('');
const formError = ref('');

// Default 30-day window — also the target of the 清除篩選 date reset.
function defaultDateRange(): { start: string; end: string } {
  const today = new Date();
  const end = today.toISOString().slice(0, 10);
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  return { start: monthAgo.toISOString().slice(0, 10), end };
}

// ── Validation + payload (mode-gated) ──────────────────────────────────────
const hasIdentifierToken = computed(() => {
  const w = firstTier.parsedWildcards();
  return w.mfg_orders.length > 0 || w.lot_ids.length > 0 || w.wafer_lots.length > 0;
});

function validate(): boolean {
  formError.value = validateQueryMode(queryMode.value, {
    pjTypes: firstTier.selection.pj_types,
    startDate: formStartDate.value,
    endDate: formEndDate.value,
    hasIdentifierToken: hasIdentifierToken.value,
  });
  return formError.value === '';
}

async function handleQuery(): Promise<void> {
  if (loading.value) return;
  if (!validate()) return;
  const requestId = nextRequestId();
  // Build the payload from the ACTIVE tab only — stale Tab A dates must not
  // leak into a Tab B submit, and vice versa.
  const payload = buildModePayload(
    queryMode.value,
    firstTier.buildQueryFragment(),
    { startDate: formStartDate.value, endDate: formEndDate.value },
  );
  await runQuery(payload);
  if (isStaleRequest(requestId)) return;
}

// ── Clear all filters (清除篩選) ────────────────────────────────────────────
// Resets first-tier MultiSelect selections + all 3 wildcard textareas, the
// date range (back to the default 30-day window), any post-query
// supplementary/matrix filter, and the results back to the empty state.
function handleClearFilters(): void {
  firstTier.clearAll();
  const { start, end } = defaultDateRange();
  formStartDate.value = start;
  formEndDate.value = end;
  formError.value = '';
  resetResults();
}

// ── Supplementary filter change handler (stage only, apply on 查詢) ────────
function onSupplementaryChange(field: SupplementaryFilterField, values: string[]): void {
  stageSupplementaryFilter(field, values);
}

// ── Matrix interaction ─────────────────────────────────────────────────────
async function handleMatrixSelect({ filter }: { filter: Partial<MatrixFilter> }): Promise<void> {
  await applyMatrixFilter(filter);
}

async function handleClearMatrixFilter(): Promise<void> {
  await applyMatrixFilter({ workcenter_group: '', spec: '', equipment_id: '', month: '' });
}

// ── Export ─────────────────────────────────────────────────────────────────
async function exportCsv(): Promise<void> {
  try {
    await doExportCsv();
  } catch (err) {
    // error is shown via the ErrorBanner bound to `error` in the composable
    console.error('Export failed', err);
  }
}

// ── Defaults ───────────────────────────────────────────────────────────────
{
  const { start, end } = defaultDateRange();
  formStartDate.value = start;
  formEndDate.value = end;
}
</script>

<template>
  <div class="dashboard theme-production-history">
    <PageHeader
      title="生產歷程查詢"
      :show-refresh="false"
    />

    <!-- Filter panel -->
    <div class="ui-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
      </div>
      <div class="ui-card-body ph-app__filter-panel">
        <!-- Query-mode tabs -->
        <div
          class="ph-mode-tabs"
          role="tablist"
          aria-label="查詢模式"
          @keydown="onTablistKeydown"
        >
          <button
            id="ph-mode-tab-classification-btn"
            type="button"
            role="tab"
            class="ph-mode-tab"
            :class="{ 'ph-mode-tab--active': queryMode === 'classification' }"
            :aria-selected="queryMode === 'classification'"
            :tabindex="queryMode === 'classification' ? 0 : -1"
            aria-controls="ph-mode-panel-classification"
            data-testid="ph-mode-tab-classification"
            @click="switchMode('classification')"
          >
            依產品分類查詢
          </button>
          <button
            id="ph-mode-tab-identifier-btn"
            type="button"
            role="tab"
            class="ph-mode-tab"
            :class="{ 'ph-mode-tab--active': queryMode === 'identifier' }"
            :aria-selected="queryMode === 'identifier'"
            :tabindex="queryMode === 'identifier' ? 0 : -1"
            aria-controls="ph-mode-panel-identifier"
            data-testid="ph-mode-tab-identifier"
            @click="switchMode('identifier')"
          >
            依識別碼查詢
          </button>
        </div>

        <!-- First-tier filter-options API error (UI-UX REC-01) -->
        <div
          v-if="firstTier.error.value"
          class="ph-first-tier__error"
          role="alert"
          aria-live="polite"
          data-testid="ph-first-tier-error"
        >
          {{ firstTier.error.value }}：請稍後重試,或切換至「依識別碼查詢」分頁輸入查詢條件。
        </div>

        <!-- Transient auto-prune notice (UI-UX REC-02) -->
        <div
          v-if="prunedNotice"
          class="ph-first-tier__pruned-notice"
          role="status"
          aria-live="polite"
          data-testid="ph-first-tier-pruned-notice"
        >
          {{ prunedNotice }}
        </div>

        <!-- ── Tab A: 依產品分類查詢 ─────────────────────────────────── -->
        <div
          v-show="queryMode === 'classification'"
          id="ph-mode-panel-classification"
          role="tabpanel"
          aria-labelledby="ph-mode-tab-classification-btn"
          :hidden="queryMode !== 'classification'"
          data-testid="ph-mode-panel-classification"
        >
          <!-- Row 1: 4 cached MultiSelects (Type / Package / BOP / Function) -->
          <div class="ph-first-tier__multiselect-grid">
            <div class="ui-filter-group">
              <label class="ui-filter-label">Type <span class="ph-app__required">*</span></label>
              <MultiSelect
                data-testid="ph-first-tier-type"
                :model-value="firstTier.selection.pj_types"
                :options="firstTier.options.value.pj_types"
                :loading="firstTier.loading.value"
                :searchable="true"
                placeholder="選擇 Type"
                @update:model-value="firstTier.setSelection('pj_types', $event)"
              />
            </div>
            <div class="ui-filter-group">
              <label class="ui-filter-label">Package</label>
              <MultiSelect
                data-testid="ph-first-tier-package"
                :model-value="firstTier.selection.packages"
                :options="firstTier.options.value.packages"
                :loading="firstTier.loading.value"
                :searchable="true"
                placeholder="全部"
                @update:model-value="firstTier.setSelection('packages', $event)"
              />
            </div>
            <div class="ui-filter-group">
              <label class="ui-filter-label">BOP</label>
              <MultiSelect
                data-testid="ph-first-tier-bop"
                :model-value="firstTier.selection.bops"
                :options="firstTier.options.value.bops"
                :loading="firstTier.loading.value"
                :searchable="true"
                placeholder="全部"
                @update:model-value="firstTier.setSelection('bops', $event)"
              />
            </div>
            <div class="ui-filter-group">
              <label class="ui-filter-label">Function</label>
              <MultiSelect
                data-testid="ph-first-tier-function"
                :model-value="firstTier.selection.pj_functions"
                :options="firstTier.options.value.pj_functions"
                :loading="firstTier.loading.value"
                :searchable="true"
                placeholder="全部"
                @update:model-value="firstTier.setSelection('pj_functions', $event)"
              />
            </div>
          </div>

          <!-- Row 2: date range -->
          <div class="ph-app__filter-row">
            <div class="ui-filter-group">
              <label for="ph-start-date" class="ui-filter-label">開始日期 <span class="ph-app__required">*</span></label>
              <input id="ph-start-date" v-model="formStartDate" type="date" class="ph-app__input" data-testid="ph-start-date" />
            </div>
            <div class="ui-filter-group">
              <label for="ph-end-date" class="ui-filter-label">結束日期 <span class="ph-app__required">*</span></label>
              <input id="ph-end-date" v-model="formEndDate" type="date" class="ph-app__input" data-testid="ph-end-date" />
            </div>
          </div>
          <p class="ph-mode-tab__note">
            依所選產品分類與日期區間查詢；識別碼分頁的輸入不會套用。
          </p>
        </div>

        <!-- ── Tab B: 依識別碼查詢 ──────────────────────────────────── -->
        <div
          v-show="queryMode === 'identifier'"
          id="ph-mode-panel-identifier"
          role="tabpanel"
          aria-labelledby="ph-mode-tab-identifier-btn"
          :hidden="queryMode !== 'identifier'"
          data-testid="ph-mode-panel-identifier"
        >
          <!-- 3 wildcard textareas (工單號 / LOT ID / Wafer LOT). No date row,
               no required classification filter. -->
          <div class="ph-first-tier__wildcard-grid">
            <div class="ui-filter-group">
              <label for="ph-mfg-orders" class="ui-filter-label">工單號</label>
              <textarea
                id="ph-mfg-orders"
                v-model="firstTier.wildcardInput.mfg_orders"
                class="ph-app__textarea ph-first-tier__wildcard-input"
                rows="2"
                placeholder="貼上多筆，以換行/逗號分隔。支援 * 萬用字元，例如 MA2025*"
                data-testid="ph-first-tier-mfg-orders"
              ></textarea>
              <div class="ph-first-tier__hint">支援 * 萬用字元；換行/逗號分隔多筆</div>
            </div>
            <div class="ui-filter-group">
              <label for="ph-lot-ids" class="ui-filter-label">LOT ID</label>
              <textarea
                id="ph-lot-ids"
                v-model="firstTier.wildcardInput.lot_ids"
                class="ph-app__textarea ph-first-tier__wildcard-input"
                rows="2"
                placeholder="貼上多筆，以換行/逗號分隔。支援 * 萬用字元，例如 GA250605*"
                data-testid="ph-first-tier-lot-ids"
              ></textarea>
              <div class="ph-first-tier__hint">支援 * 萬用字元；換行/逗號分隔多筆</div>
            </div>
            <div class="ui-filter-group">
              <label for="ph-wafer-lots" class="ui-filter-label">Wafer LOT</label>
              <textarea
                id="ph-wafer-lots"
                v-model="firstTier.wildcardInput.wafer_lots"
                class="ph-app__textarea ph-first-tier__wildcard-input"
                rows="2"
                placeholder="貼上多筆，以換行/逗號分隔。支援 * 萬用字元"
                data-testid="ph-first-tier-wafer-lots"
              ></textarea>
              <div class="ph-first-tier__hint">支援 * 萬用字元；換行/逗號分隔多筆</div>
            </div>
          </div>
          <p class="ph-mode-tab__note">
            輸入任一識別碼即可查詢，免選 Type 與日期；未指定日期時自動查詢近兩年資料。
          </p>
        </div>

        <!-- Supplementary filters (second-tier): only WorkCenter + Equipment.
             MFGORDERNAME / CONTAINERNAME / Package / BOP / Function were
             promoted to first-tier in change `prod-history-first-tier-cache-filters`
             (design D6) — removed here, not hidden, to avoid dual-state bugs. -->
        <p v-if="datasetId" class="ph-second-tier__heading">查詢後細部篩選 (Spool)</p>
        <div v-if="datasetId" class="ph-supplementary-filters">
          <div class="ui-filter-group">
            <label class="ui-filter-label">WorkCenter 群組</label>
            <MultiSelect
              :model-value="stagedFilter.workcenter_groups"
              :options="supplementaryOptions.workcenter_groups"
              :loading="supplementaryOptionsLoading"
              :searchable="true"
              placeholder="全部"
              @update:model-value="onSupplementaryChange('workcenter_groups', $event)"
            />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">Equipment</label>
            <MultiSelect
              :model-value="stagedFilter.equipment_ids"
              :options="supplementaryOptions.equipment_ids"
              :loading="supplementaryOptionsLoading"
              :searchable="true"
              placeholder="全部"
              @update:model-value="onSupplementaryChange('equipment_ids', $event)"
            />
          </div>
        </div>

        <div class="ph-app__filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--secondary"
            :disabled="loading"
            aria-label="清除所有篩選條件與查詢結果"
            data-testid="ph-clear-filters"
            @click="handleClearFilters"
          >
            清除篩選
          </button>
          <div class="flex items-center gap-3">
            <span
              v-if="formError"
              class="ph-app__form-error"
              role="alert"
              aria-live="polite"
              data-testid="ph-form-error"
            >{{ formError }}</span>
            <button
              type="button"
              class="ui-btn ui-btn--primary"
              :disabled="loading"
              data-testid="ph-query-btn"
              @click="handleQuery"
            >
              {{ loading ? '查詢中…' : '查詢' }}
            </button>
          </div>
        </div>
      </div><!-- /ui-card-body -->
    </div><!-- /ui-card -->

    <!-- Error banners -->
    <ErrorBanner :message="error || ''" :dismissible="false" />

    <ErrorBanner
      :message="overloadError ? `系統忙碌中（${overloadError.code}），請 ${overloadError.retryAfterSeconds} 秒後重試。` : ''"
      :dismissible="false"
    >
      <template v-if="overloadError" #action>
        <button type="button" class="ui-btn ui-btn--sm" @click="handleQuery">重試</button>
      </template>
    </ErrorBanner>

    <ErrorBanner
      :message="expiredDataset ? '查詢資料已過期（dataset expired），請重新查詢。' : ''"
      :dismissible="false"
    >
      <template v-if="expiredDataset" #action>
        <button type="button" class="ui-btn ui-btn--sm" @click="handleQuery">重新查詢</button>
      </template>
    </ErrorBanner>

    <!-- Echo dataset meta only for type-check parity (unused in template) -->
    <div v-if="false">{{ datasetMeta }}{{ matrixFilter }}{{ supplementaryFilter }}</div>

    <!-- Results -->
    <template v-if="datasetId">
      <!-- Matrix (top section) -->
      <ProductionMatrix
        :tree="matrixTree"
        :month-columns="matrixMonthColumns"
        :loading="matrixLoading"
        :active-filter="matrixFilter"
        @select-node="handleMatrixSelect"
        @clear-filter="handleClearMatrixFilter"
      />

      <!-- Detail table (bottom section) -->
      <ProductionDetailTable
        :rows="detailRows"
        :pagination="pagination"
        :loading="detailLoading"
        :can-export="!!datasetId"
        @export-csv="exportCsv"
        @page-change="fetchPage"
      />
    </template>

    <!-- Empty state before first query -->
    <div v-else-if="!loading" class="ph-app__empty-state" data-testid="ph-empty-state">
      {{
        queryMode === 'classification'
          ? '請選擇 Type 與日期區間後按「查詢」'
          : '請輸入工單號 / LOT ID / Wafer LOT 後按「查詢」'
      }}
    </div>

    <LoadingOverlay v-if="loading" tier="page" />
  </div>
</template>
