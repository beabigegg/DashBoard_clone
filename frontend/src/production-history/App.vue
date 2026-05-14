<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useProductionHistory, type SupplementaryFilterField, type MatrixFilter } from './composables/useProductionHistory';
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
} = useProductionHistory();

// ── First-tier cached cross-filter + wildcard composable ───────────────────
const firstTier = useFirstTierFilters();

const { nextRequestId, isStaleRequest } = useRequestGuard();

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

function validate(): boolean {
  formError.value = '';
  if (!firstTier.selection.pj_types.length) {
    formError.value = '請選擇至少一個 Type';
    return false;
  }
  if (!formStartDate.value || !formEndDate.value) {
    formError.value = '請填寫查詢起訖日期';
    return false;
  }
  if (formStartDate.value > formEndDate.value) {
    formError.value = '開始日期不可晚於結束日期';
    return false;
  }
  return true;
}

async function handleQuery(): Promise<void> {
  if (loading.value) return;
  if (!validate()) return;
  const requestId = nextRequestId();
  await runQuery({
    ...firstTier.buildQueryFragment(),
    start_date: formStartDate.value,
    end_date: formEndDate.value,
  });
  if (isStaleRequest(requestId)) return;
}

// ── Supplementary filter change handler (stage only, apply on 查詢) ────────
function onSupplementaryChange(field: SupplementaryFilterField, values: string[]): void {
  stageSupplementaryFilter(field, values);
}

// ── Matrix interaction ─────────────────────────────────────────────────────
async function handleMatrixSelect({ filter }: { filter: Partial<MatrixFilter> }): Promise<void> {
  await applyMatrixFilter(filter);
}

async function handleClearFilter(): Promise<void> {
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
const today = new Date();
formEndDate.value = today.toISOString().slice(0, 10);
const monthAgo = new Date(today);
monthAgo.setDate(monthAgo.getDate() - 30);
formStartDate.value = monthAgo.toISOString().slice(0, 10);
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
        <!-- First-tier filter-options API error (UI-UX REC-01) -->
        <div
          v-if="firstTier.error.value"
          class="ph-first-tier__error"
          role="alert"
          aria-live="polite"
          data-testid="ph-first-tier-error"
        >
          {{ firstTier.error.value }}：請稍後重試,或直接以下方萬用字元欄位輸入查詢條件。
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

        <!-- Row 2: 3 wildcard textareas (工單號 / LOT ID / Wafer LOT) -->
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

        <!-- Row 3: date range -->
        <div class="ph-app__filter-row">
          <div class="ui-filter-group">
            <label class="ui-filter-label">開始日期 <span class="ph-app__required">*</span></label>
            <input v-model="formStartDate" type="date" class="ph-app__input" />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">結束日期 <span class="ph-app__required">*</span></label>
            <input v-model="formEndDate" type="date" class="ph-app__input" />
          </div>
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
          <span
            v-if="formError"
            class="ph-app__form-error"
            role="alert"
            aria-live="polite"
          >{{ formError }}</span>
          <button
            class="ui-btn ui-btn--primary"
            :disabled="loading"
            @click="handleQuery"
          >
            {{ loading ? '查詢中…' : '查詢' }}
          </button>
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
        <button class="ui-btn ui-btn--sm" @click="handleQuery">重試</button>
      </template>
    </ErrorBanner>

    <ErrorBanner
      :message="expiredDataset ? '查詢資料已過期（dataset expired），請重新查詢。' : ''"
      :dismissible="false"
    >
      <template v-if="expiredDataset" #action>
        <button class="ui-btn ui-btn--sm" @click="handleQuery">重新查詢</button>
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
        @clear-filter="handleClearFilter"
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
    <div v-else-if="!loading" class="ph-app__empty-state">
      請選擇 Type 與日期區間後按「查詢」
    </div>

    <LoadingOverlay v-if="loading" tier="page" />
  </div>
</template>
