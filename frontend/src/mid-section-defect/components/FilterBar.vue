<script setup>
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  availableLossReasons: {
    type: Array,
    default: () => [],
  },
  stationOptions: {
    type: Array,
    default: () => [],
  },
  queryMode: {
    type: String,
    default: 'date_range',
  },
  containerInputType: {
    type: String,
    default: 'lot',
  },
  containerInput: {
    type: String,
    default: '',
  },
  resolutionInfo: {
    type: Object,
    default: null,
  },
  pjTypeOptions: {
    type: Array,
    default: () => [],
  },
  packageOptions: {
    type: Array,
    default: () => [],
  },
  filterOptionsLoading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  'update-filters',
  'query',
  'update:queryMode',
  'update:containerInputType',
  'update:containerInput',
  'commit-container-filter',
]);

function updateFilters(patch) {
  emit('update-filters', {
    ...props.filters,
    ...patch,
  });
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <!-- Mode toggle tabs -->
      <div class="mode-tab-row">
        <button
          type="button"
          :class="['mode-tab', { active: queryMode === 'date_range' }]"
          data-testid="mode-date-range"
          @click="$emit('update:queryMode', 'date_range')"
        >
          日期區間
        </button>
        <button
          type="button"
          :class="['mode-tab', { active: queryMode === 'container' }]"
          data-testid="mode-container"
          @click="$emit('update:queryMode', 'container')"
        >
          LOT / 工單 / WAFER
        </button>
      </div>

      <div class="filter-row">
        <!-- Shared: detection station (multi-select) -->
        <div class="filter-field">
          <label>偵測站</label>
          <MultiSelect
            :model-value="filters.station"
            :options="stationOptions"
            :disabled="loading"
            placeholder="選擇偵測站"
            data-testid="station-select"
            @update:model-value="updateFilters({ station: $event })"
          />
        </div>

        <!-- Container mode: input type -->
        <div v-if="queryMode === 'container'" class="filter-field">
          <label for="msd-container-type">輸入類型</label>
          <select
            id="msd-container-type"
            class="filter-select"
            :value="containerInputType"
            :disabled="loading"
            @change="$emit('update:containerInputType', $event.target.value)"
          >
            <option value="lot" data-testid="container-type-lot">LOT</option>
            <option value="work_order" data-testid="container-type-workorder">工單</option>
            <option value="wafer_lot" data-testid="container-type-wafer">WAFER LOT</option>
            <option value="serial_number">成品流水號</option>
            <option value="gd_work_order">GD 工單</option>
            <option value="gd_lot_id">GD LOT ID</option>
          </select>
        </div>

        <!-- Shared: direction -->
        <div class="filter-field">
          <label>方向</label>
          <div class="direction-toggle">
            <button
              type="button"
              class="direction-btn"
              :class="{ active: filters.direction === 'backward' }"
              :disabled="loading"
              @click="updateFilters({ direction: 'backward' })"
            >
              反向追溯
            </button>
            <button
              type="button"
              class="direction-btn"
              :class="{ active: filters.direction === 'forward' }"
              :disabled="loading"
              @click="updateFilters({ direction: 'forward' })"
            >
              正向追溯
            </button>
          </div>
        </div>

        <!-- Date range mode: dates -->
        <template v-if="queryMode === 'date_range'">
          <div class="filter-field">
            <label for="msd-start-date">開始</label>
            <input
              id="msd-start-date"
              type="date"
              :value="filters.startDate"
              :disabled="loading"
              data-testid="start-date"
              @input="updateFilters({ startDate: $event.target.value })"
            />
          </div>

          <div class="filter-field">
            <label for="msd-end-date">結束</label>
            <input
              id="msd-end-date"
              type="date"
              :value="filters.endDate"
              :disabled="loading"
              data-testid="end-date"
              @input="updateFilters({ endDate: $event.target.value })"
            />
          </div>
        </template>

        <!-- Shared: Type (PJ_TYPE) cross-filter -->
        <div class="filter-field">
          <label>型號</label>
          <MultiSelect
            :model-value="filters.pjTypes"
            :options="pjTypeOptions"
            :disabled="loading"
            :loading="filterOptionsLoading"
            placeholder="全部型號"
            data-testid="pj-type-select"
            @update:model-value="updateFilters({ pjTypes: $event })"
            @dropdown-close="emit('commit-container-filter')"
          />
        </div>

        <!-- Shared: Package (PRODUCTLINENAME) cross-filter -->
        <div class="filter-field">
          <label>封裝</label>
          <MultiSelect
            :model-value="filters.packages"
            :options="packageOptions"
            :disabled="loading"
            :loading="filterOptionsLoading"
            placeholder="全部封裝"
            data-testid="package-select"
            @update:model-value="updateFilters({ packages: $event })"
            @dropdown-close="emit('commit-container-filter')"
          />
        </div>

        <!-- Shared: loss reasons -->
        <div class="filter-field">
          <label>不良原因</label>
          <MultiSelect
            :model-value="filters.lossReasons"
            :options="availableLossReasons"
            :disabled="loading"
            placeholder="全部原因"
            data-testid="loss-reason-select"
            @update:model-value="updateFilters({ lossReasons: $event })"
          />
        </div>

        <button
          type="button"
          class="ui-btn ui-btn--primary"
          :disabled="loading"
          data-testid="query-submit-btn"
          @click="$emit('query')"
        >
          查詢
        </button>
      </div>

      <!-- Container mode: textarea input -->
      <div v-if="queryMode === 'container'" class="container-input-row">
        <textarea
          class="filter-textarea"
          rows="3"
          :value="containerInput"
          :disabled="loading"
          placeholder="每行一個，支援 * 或 % wildcard&#10;GA26020001-A00-001&#10;GA260200%&#10;..."
          data-testid="container-input"
          @input="$emit('update:containerInput', $event.target.value)"
        ></textarea>
      </div>

      <!-- Resolution info (container mode) -->
      <div
        v-if="resolutionInfo && queryMode === 'container'"
        class="resolution-info"
      >
        已解析 {{ resolutionInfo.resolved_count }} 筆容器
        <template v-if="resolutionInfo.not_found?.length > 0">
          <span class="resolution-warn">
            ({{ resolutionInfo.not_found.length }} 筆未找到:
            {{ resolutionInfo.not_found.slice(0, 10).join(', ')
            }}{{ resolutionInfo.not_found.length > 10 ? '...' : '' }})
          </span>
        </template>
      </div>
    </div>
  </section>
</template>
