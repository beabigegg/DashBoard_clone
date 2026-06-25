<script setup lang="ts">
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

interface DraftFilters {
  startDate: string;
  endDate: string;
  includeExcludedScrap: boolean;
  excludeMaterialScrap: boolean;
  excludePbDiode: boolean;
}

interface AvailableFilters {
  workcenterGroups?: string[];
  packages?: string[];
  reasons?: string[];
  types?: string[];
}

interface SupplementaryFilters {
  packages?: string[];
  workcenterGroups?: string[];
  reasons?: string[];
  types?: string[];
}

/** Options available for the primary prefilter MultiSelects (BASE_WHERE layer). */
interface PrimaryPrefilterOptions {
  pj_types?: string[];
  packages?: string[];
  pj_functions?: string[];
}

interface LoadingState {
  querying?: boolean;
  exporting?: boolean;
  [key: string]: unknown;
}

interface ResolutionInfo {
  resolved_count: number;
  expansion_info?: Record<string, unknown>;
  not_found?: string[];
}

interface FilterChip {
  key: string;
  label: string;
  removable: boolean;
  type: string;
  value: string;
  dimension?: string;
}

const props = defineProps<{
  filters: DraftFilters;
  queryMode?: string;
  containerInputType?: string;
  containerInput?: string;
  availableFilters?: AvailableFilters;
  supplementaryFilters?: SupplementaryFilters;
  queryId?: string;
  resolutionInfo?: ResolutionInfo | null;
  loading: LoadingState;
  activeFilterChips?: FilterChip[];
  primaryQueryMaxDays?: number;
  // Primary prefilter selections (BASE_WHERE layer)
  primaryPjTypes?: string[];
  primaryPackages?: string[];
  primaryPjFunctions?: string[];
  // Primary prefilter options (from container_filter_cache cross-filter API)
  primaryPrefilterOptions?: PrimaryPrefilterOptions;
  primaryPrefilterLoading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'apply'): void;
  (e: 'clear'): void;
  (e: 'export-csv'): void;
  (e: 'remove-chip', chip: FilterChip): void;
  (e: 'update:queryMode', value: string): void;
  (e: 'update:containerInputType', value: string): void;
  (e: 'update:containerInput', value: string): void;
  (e: 'supplementary-change', value: { packages: string[]; workcenterGroups: string[]; reasons: string[]; types: string[] }): void;
  (e: 'update:primaryPjTypes', value: string[]): void;
  (e: 'update:primaryPackages', value: string[]): void;
  (e: 'update:primaryPjFunctions', value: string[]): void;
  (e: 'primary-prefilter-close', field: 'pj_types' | 'packages' | 'pj_functions'): void;
}>();

function emitSupplementary(patch: Partial<{ packages: string[]; workcenterGroups: string[]; reasons: string[]; types: string[] }>): void {
  emit('supplementary-change', {
    packages: props.supplementaryFilters?.packages || [],
    workcenterGroups: props.supplementaryFilters?.workcenterGroups || [],
    reasons: props.supplementaryFilters?.reasons || [],
    types: props.supplementaryFilters?.types || [],
    ...patch,
  });
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">查詢條件</div>
    </div>
    <div class="card-body ui-card-body filter-panel">
      <!-- Mode toggle tabs -->
      <div class="filter-group-full mode-tab-row">
        <button
          type="button"
          data-testid="query-mode-date"
          :class="['mode-tab', { active: queryMode === 'date_range' }]"
          @click="$emit('update:queryMode', 'date_range')"
        >
          日期區間
        </button>
        <button
          type="button"
          data-testid="query-mode-container"
          :class="['mode-tab', { active: queryMode === 'container' }]"
          @click="$emit('update:queryMode', 'container')"
        >
          LOT / 工單 / WAFER
        </button>
      </div>

      <!-- Date range mode -->
      <template v-if="queryMode === 'date_range'">
        <div class="filter-group">
          <label class="filter-label" for="start-date">開始日期</label>
          <input
            id="start-date"
            v-model="filters.startDate"
            type="date"
            class="filter-input"
            data-testid="start-date"
          />
        </div>
        <div class="filter-group">
          <label class="filter-label" for="end-date">結束日期</label>
          <input
            id="end-date"
            v-model="filters.endDate"
            type="date"
            class="filter-input"
            data-testid="end-date"
          />
        </div>
        <div class="filter-group-full date-limit-hint">
          日期區間最多 {{ primaryQueryMaxDays }} 天（約一年）。超過請改用較短區間分次查詢。
        </div>
      </template>

      <!-- Container mode -->
      <template v-else>
        <div class="filter-group filter-group-full container-input-group">
          <div class="container-label-row">
            <label class="filter-label" for="container-type">輸入類型</label>
            <select
              id="container-type"
              class="filter-input container-type-select"
              data-testid="container-type-select"
              :value="containerInputType"
              @change="$emit('update:containerInputType', ($event.target as HTMLSelectElement).value)"
            >
              <option value="lot" data-testid="container-type-lot">LOT</option>
              <option value="work_order" data-testid="container-type-workorder">工單</option>
              <option value="wafer_lot">WAFER LOT</option>
            </select>
            <label class="filter-label" for="container-input"
              >輸入值 (每行一個，支援 * 或 % wildcard)</label
            >
          </div>
          <textarea
            id="container-input"
            class="filter-input filter-textarea"
            data-testid="container-input"
            rows="3"
            :value="containerInput"
            @input="$emit('update:containerInput', ($event.target as HTMLTextAreaElement).value)"
            placeholder="GA26020001-A00-001&#10;GA260200%&#10;..."
          ></textarea>
        </div>
      </template>

      <!-- Primary prefilter row (BASE_WHERE layer, optional; narrows Oracle query scope) -->
      <div class="filter-group-full primary-prefilter-row" data-testid="primary-prefilter-row">
        <div class="filter-group" data-testid="primary-pj-type-select">
          <label class="filter-label">PJ Type</label>
          <MultiSelect
            :model-value="primaryPjTypes || []"
            :options="primaryPrefilterOptions?.pj_types || []"
            placeholder="全部 PJ Type"
            aria-label="PJ Type 預篩選"
            searchable
            :loading="primaryPrefilterLoading"
            data-testid="primary-pj-type-multiselect"
            @update:model-value="$emit('update:primaryPjTypes', $event)"
            @dropdown-close="$emit('primary-prefilter-close', 'pj_types')"
          />
        </div>

        <div class="filter-group" data-testid="primary-package-select">
          <label class="filter-label">Package</label>
          <MultiSelect
            :model-value="primaryPackages || []"
            :options="primaryPrefilterOptions?.packages || []"
            placeholder="全部 Package"
            aria-label="Package 預篩選"
            searchable
            :loading="primaryPrefilterLoading"
            data-testid="primary-package-multiselect"
            @update:model-value="$emit('update:primaryPackages', $event)"
            @dropdown-close="$emit('primary-prefilter-close', 'packages')"
          />
        </div>

        <div class="filter-group" data-testid="primary-pj-function-select">
          <label class="filter-label">PJ Function</label>
          <MultiSelect
            :model-value="primaryPjFunctions || []"
            :options="primaryPrefilterOptions?.pj_functions || []"
            placeholder="全部 PJ Function"
            aria-label="PJ Function 預篩選"
            searchable
            :loading="primaryPrefilterLoading"
            data-testid="primary-pj-function-multiselect"
            @update:model-value="$emit('update:primaryPjFunctions', $event)"
            @dropdown-close="$emit('primary-prefilter-close', 'pj_functions')"
          />
        </div>
      </div>

      <div class="filter-toolbar">
        <div class="checkbox-row">
          <label class="checkbox-pill">
            <input v-model="filters.includeExcludedScrap" type="checkbox" data-testid="include-excluded-scrap" />
            納入不計良率報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludeMaterialScrap" type="checkbox" data-testid="exclude-material-scrap" />
            排除原物料報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludePbDiode" type="checkbox" data-testid="exclude-pb-diode" />
            排除 PB_* 系列
          </label>
        </div>
        <div class="filter-actions">
          <button
            class="ui-btn ui-btn--primary"
            data-testid="query-submit-btn"
            :disabled="loading.querying"
            @click="$emit('apply')"
          >
            <template v-if="loading.querying"
              >查詢中...</template
            >
            <template v-else>查詢</template>
          </button>
          <button
            class="ui-btn ui-btn--ghost"
            data-testid="clear-btn"
            :disabled="loading.querying"
            @click="$emit('clear')"
          >
            清除條件
          </button>
          <button
            class="ui-btn ui-btn--ghost"
            :disabled="loading.querying || loading.exporting"
            @click="$emit('export-csv')"
          >
            <template v-if="loading.exporting"
              >匯出中...</template
            >
            <template v-else>匯出 CSV</template>
          </button>
        </div>
      </div>
    </div>

    <!-- Resolution info (container mode) -->
    <div
      v-if="resolutionInfo && queryMode === 'container'"
      class="card-body ui-card-body resolution-info"
    >
      已解析 {{ resolutionInfo.resolved_count }} 筆容器
      <template v-if="resolutionInfo.expansion_info && Object.keys(resolutionInfo.expansion_info).length > 1">
        <span class="resolution-detail">
          ({{ Object.entries(resolutionInfo.expansion_info).map(([k, v]) => `${k}: ${v}`).join(', ') }})
        </span>
      </template>
      <template v-if="(resolutionInfo.not_found?.length ?? 0) > 0">
        <span class="resolution-warn">
          ({{ resolutionInfo.not_found?.length }} 筆未找到:
          {{ resolutionInfo.not_found?.slice(0, 10).join(', ')
          }}{{ (resolutionInfo.not_found?.length ?? 0) > 10 ? '...' : '' }})
        </span>
      </template>
    </div>

    <!-- Supplementary filters (only after primary query) -->
    <div v-if="queryId" class="supplementary-panel">
      <div class="supplementary-header">補充篩選</div>
      <div class="supplementary-toolbar">
        <div class="pareto-fixed-note">
          Pareto 固定累計前 80%，且 TYPE / EQUIPMENT 僅顯示 TOP 20。
          明細與匯出 CSV 仍保留完整篩選結果，不受此顯示限制影響。
        </div>
      </div>
      <div class="supplementary-row">
        <div class="filter-group" data-testid="workcenter-select">
          <label class="filter-label">WORKCENTER GROUP</label>
          <MultiSelect
            :model-value="supplementaryFilters?.workcenterGroups"
            :options="availableFilters?.workcenterGroups || []"
            placeholder="全部工作中心群組"
            searchable
            @update:model-value="emitSupplementary({ workcenterGroups: $event })"
          />
        </div>

        <div class="filter-group" data-testid="package-select">
          <label class="filter-label">Package</label>
          <MultiSelect
            :model-value="supplementaryFilters?.packages"
            :options="availableFilters?.packages || []"
            placeholder="全部 Package"
            searchable
            @update:model-value="emitSupplementary({ packages: $event })"
          />
        </div>

        <div class="filter-group" data-testid="reason-select">
          <label class="filter-label">報廢原因</label>
          <MultiSelect
            :model-value="supplementaryFilters?.reasons"
            :options="availableFilters?.reasons || []"
            placeholder="全部原因"
            searchable
            @update:model-value="emitSupplementary({ reasons: $event })"
          />
        </div>

        <div class="filter-group" data-testid="type-select">
          <label class="filter-label">TYPE</label>
          <MultiSelect
            :model-value="supplementaryFilters?.types"
            :options="availableFilters?.types || []"
            placeholder="全部 TYPE"
            searchable
            @update:model-value="emitSupplementary({ types: $event })"
          />
        </div>
      </div>
    </div>

    <div
      class="card-body ui-card-body active-filter-chip-row"
      v-if="activeFilterChips && activeFilterChips.length > 0"
    >
      <div class="filter-label">套用中篩選</div>
      <div class="chip-list">
        <div
          v-for="chip in activeFilterChips"
          :key="chip.key"
          class="filter-chip"
        >
          <span>{{ chip.label }}</span>
          <button
            v-if="chip.removable"
            type="button"
            class="chip-remove"
            @click="$emit('remove-chip', chip)"
          >
            &times;
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
