<script setup>
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

const props = defineProps({
  filters: { type: Object, required: true },
  queryMode: { type: String, default: 'date_range' },
  containerInputType: { type: String, default: 'lot' },
  containerInput: { type: String, default: '' },
  availableFilters: { type: Object, default: () => ({}) },
  supplementaryFilters: { type: Object, default: () => ({}) },
  queryId: { type: String, default: '' },
  resolutionInfo: { type: Object, default: null },
  loading: { type: Object, required: true },
  activeFilterChips: { type: Array, default: () => [] },
  primaryQueryMaxDays: { type: Number, default: 190 },
});

const emit = defineEmits([
  'apply',
  'clear',
  'export-csv',
  'remove-chip',
  'update:queryMode',
  'update:containerInputType',
  'update:containerInput',
  'supplementary-change',
]);

function emitSupplementary(patch) {
  emit('supplementary-change', {
    packages: props.supplementaryFilters.packages || [],
    workcenterGroups: props.supplementaryFilters.workcenterGroups || [],
    reasons: props.supplementaryFilters.reasons || [],
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
          :class="['mode-tab', { active: queryMode === 'date_range' }]"
          @click="$emit('update:queryMode', 'date_range')"
        >
          日期區間
        </button>
        <button
          type="button"
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
          />
        </div>
        <div class="filter-group">
          <label class="filter-label" for="end-date">結束日期</label>
          <input
            id="end-date"
            v-model="filters.endDate"
            type="date"
            class="filter-input"
          />
        </div>
        <div class="filter-group-full date-limit-hint">
          日期區間最多 {{ primaryQueryMaxDays }} 天（約半年）。超過請改用較短區間分次查詢。
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
              :value="containerInputType"
              @change="$emit('update:containerInputType', $event.target.value)"
            >
              <option value="lot">LOT</option>
              <option value="work_order">工單</option>
              <option value="wafer_lot">WAFER LOT</option>
            </select>
            <label class="filter-label" for="container-input"
              >輸入值 (每行一個，支援 * 或 % wildcard)</label
            >
          </div>
          <textarea
            id="container-input"
            class="filter-input filter-textarea"
            rows="3"
            :value="containerInput"
            @input="$emit('update:containerInput', $event.target.value)"
            placeholder="GA26020001-A00-001&#10;GA260200%&#10;..."
          ></textarea>
        </div>
      </template>

      <div class="filter-toolbar">
        <div class="checkbox-row">
          <label class="checkbox-pill">
            <input v-model="filters.includeExcludedScrap" type="checkbox" />
            納入不計良率報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludeMaterialScrap" type="checkbox" />
            排除原物料報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludePbDiode" type="checkbox" />
            排除 PB_* 系列
          </label>
        </div>
        <div class="filter-actions">
          <button
            class="ui-btn ui-btn--primary"
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
      <template v-if="resolutionInfo.not_found?.length > 0">
        <span class="resolution-warn">
          ({{ resolutionInfo.not_found.length }} 筆未找到:
          {{ resolutionInfo.not_found.slice(0, 10).join(', ')
          }}{{ resolutionInfo.not_found.length > 10 ? '...' : '' }})
        </span>
      </template>
    </div>

    <!-- Supplementary filters (only after primary query) -->
    <div v-if="queryId" class="supplementary-panel">
      <div class="supplementary-header">補充篩選 (快取內篩選)</div>
      <div class="supplementary-toolbar">
        <div class="pareto-fixed-note">
          Pareto 固定累計前 80%，且 TYPE / EQUIPMENT 僅顯示 TOP 20。
          明細與匯出 CSV 仍保留完整篩選結果，不受此顯示限制影響。
        </div>
      </div>
      <div class="supplementary-row">
        <div class="filter-group">
          <label class="filter-label">WORKCENTER GROUP</label>
          <MultiSelect
            :model-value="supplementaryFilters.workcenterGroups"
            :options="availableFilters.workcenterGroups || []"
            placeholder="全部工作中心群組"
            searchable
            @update:model-value="emitSupplementary({ workcenterGroups: $event })"
          />
        </div>

        <div class="filter-group">
          <label class="filter-label">Package</label>
          <MultiSelect
            :model-value="supplementaryFilters.packages"
            :options="availableFilters.packages || []"
            placeholder="全部 Package"
            searchable
            @update:model-value="emitSupplementary({ packages: $event })"
          />
        </div>

        <div class="filter-group">
          <label class="filter-label">報廢原因</label>
          <MultiSelect
            :model-value="supplementaryFilters.reasons"
            :options="availableFilters.reasons || []"
            placeholder="全部原因"
            searchable
            @update:model-value="emitSupplementary({ reasons: $event })"
          />
        </div>
      </div>
    </div>

    <div
      class="card-body ui-card-body active-filter-chip-row"
      v-if="activeFilterChips.length > 0"
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
