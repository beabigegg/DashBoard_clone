<script setup>
import MultiSelect from '../../resource-shared/components/MultiSelect.vue';

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
  paretoDisplayScope: { type: String, default: 'all' },
});

const emit = defineEmits([
  'apply',
  'clear',
  'export-csv',
  'remove-chip',
  'pareto-scope-toggle',
  'pareto-display-scope-change',
  'update:queryMode',
  'update:containerInputType',
  'update:containerInput',
  'supplementary-change',
]);

function emitSupplementary(patch) {
  emit('supplementary-change', {
    packages: props.supplementaryFilters.packages || [],
    workcenterGroups: props.supplementaryFilters.workcenterGroups || [],
    reason: props.supplementaryFilters.reason || '',
    ...patch,
  });
}
</script>

<template>
  <section class="card">
    <div class="card-header">
      <div class="card-title">查詢條件</div>
    </div>
    <div class="card-body filter-panel">
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
      </template>

      <!-- Container mode -->
      <template v-else>
        <div class="filter-group">
          <label class="filter-label" for="container-type">輸入類型</label>
          <select
            id="container-type"
            class="filter-input"
            :value="containerInputType"
            @change="$emit('update:containerInputType', $event.target.value)"
          >
            <option value="lot">LOT</option>
            <option value="work_order">工單</option>
            <option value="wafer_lot">WAFER LOT</option>
          </select>
        </div>
        <div class="filter-group filter-group-wide">
          <label class="filter-label" for="container-input"
            >輸入值 (每行一個，支援 * 或 % wildcard)</label
          >
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
            class="btn btn-primary"
            :disabled="loading.querying"
            @click="$emit('apply')"
          >
            <template v-if="loading.querying"
              ><span class="btn-spinner"></span>查詢中...</template
            >
            <template v-else>查詢</template>
          </button>
          <button
            class="btn btn-secondary"
            :disabled="loading.querying"
            @click="$emit('clear')"
          >
            清除條件
          </button>
          <button
            class="btn btn-light btn-export"
            :disabled="loading.querying || loading.exporting"
            @click="$emit('export-csv')"
          >
            <template v-if="loading.exporting"
              ><span class="btn-spinner"></span>匯出中...</template
            >
            <template v-else>匯出 CSV</template>
          </button>
        </div>
      </div>
    </div>

    <!-- Resolution info (container mode) -->
    <div
      v-if="resolutionInfo && queryMode === 'container'"
      class="card-body resolution-info"
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
        <label class="checkbox-pill">
          <input
            :checked="filters.paretoTop80"
            type="checkbox"
            @change="$emit('pareto-scope-toggle', $event.target.checked)"
          />
          Pareto 僅顯示累計前 80%
        </label>
        <label class="filter-label">顯示範圍</label>
        <select
          class="dimension-select pareto-scope-select"
          :value="paretoDisplayScope"
          @change="$emit('pareto-display-scope-change', $event.target.value)"
        >
          <option value="all">全部顯示</option>
          <option value="top20">只顯示 TOP 20</option>
        </select>
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
          <label class="filter-label" for="supp-reason">報廢原因</label>
          <select
            id="supp-reason"
            class="filter-input"
            :value="supplementaryFilters.reason"
            @change="emitSupplementary({ reason: $event.target.value })"
          >
            <option value="">全部原因</option>
            <option
              v-for="r in availableFilters.reasons || []"
              :key="r"
              :value="r"
            >
              {{ r }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <div
      class="card-body active-filter-chip-row"
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
