<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { apiGet } from '../core/api';
import { useProductionHistory, type SupplementaryFilterField, type MatrixFilter } from './composables/useProductionHistory';
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

const { nextRequestId, isStaleRequest } = useRequestGuard();

// ── Type MultiSelect state ───────────────────────────────────────────────
const typeOptions = ref<string[]>([]);
const typeOptionsLoading = ref(false);
const selectedTypes = ref<string[]>([]);

onMounted(async () => {
  typeOptionsLoading.value = true;
  try {
    const resp = (await apiGet('/api/production-history/type-options')) as {
      data?: { items?: string[] };
    };
    typeOptions.value = resp.data?.items || [];
  } catch (_) {
    // non-critical
  } finally {
    typeOptionsLoading.value = false;
  }
});

// ── Primary query state ────────────────────────────────────────────────────
const formStartDate = ref('');
const formEndDate = ref('');
const formError = ref('');

function validate(): boolean {
  formError.value = '';
  if (!selectedTypes.value.length) {
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
    pj_types: selectedTypes.value,
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
        <!-- Row 1: Type (MultiSelect), date range -->
        <div class="ph-app__filter-row">
          <div class="ui-filter-group ph-app__filter-field--type">
            <label class="ui-filter-label">Type <span class="ph-app__required">*</span></label>
            <MultiSelect
              :model-value="selectedTypes"
              :options="typeOptions"
              :loading="typeOptionsLoading"
              :searchable="true"
              placeholder="選擇 Type"
              @update:model-value="selectedTypes = $event"
            />
          </div>

          <div class="ui-filter-group">
            <label class="ui-filter-label">開始日期 <span class="ph-app__required">*</span></label>
            <input v-model="formStartDate" type="date" class="ph-app__input" />
          </div>
          <div class="ui-filter-group">
            <label class="ui-filter-label">結束日期 <span class="ph-app__required">*</span></label>
            <input v-model="formEndDate" type="date" class="ph-app__input" />
          </div>
        </div>

        <!-- Supplementary filters — only after query returns data -->
        <div v-if="datasetId" class="ph-supplementary-filters">
        <div class="ui-filter-group">
          <label class="ui-filter-label">工單號</label>
          <MultiSelect
            :model-value="stagedFilter.work_orders"
            :options="supplementaryOptions.work_orders"
            :loading="supplementaryOptionsLoading"
            :searchable="true"
            placeholder="全部"
            @update:model-value="onSupplementaryChange('work_orders', $event)"
          />
        </div>
        <div class="ui-filter-group">
          <label class="ui-filter-label">LOT ID</label>
          <MultiSelect
            :model-value="stagedFilter.lot_ids"
            :options="supplementaryOptions.lot_ids"
            :loading="supplementaryOptionsLoading"
            :searchable="true"
            placeholder="全部"
            @update:model-value="onSupplementaryChange('lot_ids', $event)"
          />
        </div>
        <div class="ui-filter-group">
          <label class="ui-filter-label">Package</label>
          <MultiSelect
            :model-value="stagedFilter.packages"
            :options="supplementaryOptions.packages"
            :loading="supplementaryOptionsLoading"
            :searchable="true"
            placeholder="全部"
            @update:model-value="onSupplementaryChange('packages', $event)"
          />
        </div>
        <div class="ui-filter-group">
          <label class="ui-filter-label">BOP</label>
          <MultiSelect
            :model-value="stagedFilter.bop_codes"
            :options="supplementaryOptions.bop_codes"
            :loading="supplementaryOptionsLoading"
            :searchable="true"
            placeholder="全部"
            @update:model-value="onSupplementaryChange('bop_codes', $event)"
          />
        </div>
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
          <span v-if="formError" class="ph-app__form-error">{{ formError }}</span>
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
