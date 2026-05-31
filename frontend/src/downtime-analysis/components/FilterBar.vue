<script setup lang="ts">
import { ref, computed } from 'vue';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import type { FilterState, FilterOptions } from '../types';

const props = defineProps<{
  state: FilterState;
  options: FilterOptions;
  loading?: boolean;
}>();

const emit = defineEmits<{
  /** Emitted only when the user clicks the "查詢" submit button. */
  (e: 'filter-change', state: FilterState): void;
  /** Emitted for any intermediate state change (date, dropdown, granularity) — does NOT trigger a query. */
  (e: 'update-state', patch: Partial<FilterState>): void;
  (e: 'clear'): void;
}>();

const MAX_QUERY_DAYS = 730;

const dateError = ref('');

const STATUS_TYPE_OPTIONS: string[] = ['UDT', 'SDT', 'EGT'];

function validateDates(): string {
  if (!props.state.start_date || !props.state.end_date) {
    return '請先設定開始與結束日期';
  }
  const start = new Date(props.state.start_date);
  const end = new Date(props.state.end_date);
  const diffDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
  if (diffDays < 0) return '結束日期必須大於起始日期';
  if (diffDays > MAX_QUERY_DAYS) return '查詢範圍不可超過兩年';
  return '';
}

function handleSubmit(): void {
  const err = validateDates();
  if (err) {
    dateError.value = err;
    return;
  }
  dateError.value = '';
  emit('filter-change', { ...props.state });
}

function handleClear(): void {
  dateError.value = '';
  emit('clear');
}

/** Fix 2: date inputs only update draft state — no query fired. */
function handleStartDate(e: Event): void {
  const val = (e.target as HTMLInputElement).value;
  emit('update-state', { start_date: val });
}

/** Fix 2: date inputs only update draft state — no query fired. */
function handleEndDate(e: Event): void {
  const val = (e.target as HTMLInputElement).value;
  emit('update-state', { end_date: val });
}

/** Granularity change updates draft state only; query fires on submit. */
function handleGranularity(g: string): void {
  emit('update-state', { granularity: g });
}

const granularityOptions = [
  { value: 'day', label: '日' },
  { value: 'week', label: '週' },
  { value: 'month', label: '月' },
];

const isDisabled = computed(() => props.loading);
</script>

<template>
  <div class="downtime-filter-bar">
    <div class="filter-row">
      <!-- Date range -->
      <div class="filter-field">
        <label for="downtime-start-date">開始日期</label>
        <input
          id="downtime-start-date"
          type="date"
          :value="state.start_date"
          :disabled="isDisabled"
          aria-label="開始日期"
          @change="handleStartDate"
        />
      </div>
      <div class="filter-field">
        <label for="downtime-end-date">結束日期</label>
        <input
          id="downtime-end-date"
          type="date"
          :value="state.end_date"
          :disabled="isDisabled"
          aria-label="結束日期"
          @change="handleEndDate"
        />
      </div>

      <!-- Granularity -->
      <div class="filter-field">
        <label>時間粒度</label>
        <div class="granularity-btns" role="group" aria-label="時間粒度">
          <button
            v-for="g in granularityOptions"
            :key="g.value"
            type="button"
            class="granularity-btn"
            :class="{ active: state.granularity === g.value }"
            :aria-pressed="state.granularity === g.value"
            :disabled="isDisabled"
            @click="handleGranularity(g.value)"
          >
            {{ g.label }}
          </button>
        </div>
      </div>

      <!-- Fix 1: Workcenter Groups MultiSelect -->
      <div class="filter-field">
        <label>工站群組</label>
        <MultiSelect
          :model-value="state.workcenter_groups"
          :options="options.workcenter_groups"
          :disabled="isDisabled"
          placeholder="全部站點"
          @update:model-value="emit('update-state', { workcenter_groups: $event })"
        />
      </div>

      <!-- Fix 1: Equipment Family MultiSelect -->
      <div class="filter-field">
        <label>設備型號</label>
        <MultiSelect
          :model-value="state.families"
          :options="options.families"
          :disabled="isDisabled"
          placeholder="全部型號"
          @update:model-value="emit('update-state', { families: $event })"
        />
      </div>

      <!-- Fix 1: Equipment (Resource) MultiSelect -->
      <div class="filter-field">
        <label>設備</label>
        <MultiSelect
          :model-value="state.resource_ids"
          :options="options.resources"
          :disabled="isDisabled"
          placeholder="全部設備"
          searchable
          @update:model-value="emit('update-state', { resource_ids: $event })"
        />
      </div>

      <!-- Fix 1: Status Type MultiSelect (UDT / SDT / EGT) -->
      <div class="filter-field">
        <label>停機類型</label>
        <MultiSelect
          :model-value="state.status_types"
          :options="STATUS_TYPE_OPTIONS"
          :disabled="isDisabled"
          placeholder="全部類型"
          @update:model-value="emit('update-state', { status_types: $event })"
        />
      </div>

      <!-- Equipment type checkboxes -->
      <div class="checkbox-row">
        <label class="checkbox-pill">
          <input
            type="checkbox"
            :checked="state.is_production"
            :disabled="isDisabled"
            @change="emit('update-state', { is_production: ($event.target as HTMLInputElement).checked })"
          />
          生產設備
        </label>
        <label class="checkbox-pill">
          <input
            type="checkbox"
            :checked="state.is_key"
            :disabled="isDisabled"
            @change="emit('update-state', { is_key: ($event.target as HTMLInputElement).checked })"
          />
          重點設備
        </label>
        <label class="checkbox-pill">
          <input
            type="checkbox"
            :checked="state.is_monitor"
            :disabled="isDisabled"
            @change="emit('update-state', { is_monitor: ($event.target as HTMLInputElement).checked })"
          />
          監控設備
        </label>
      </div>

      <!-- Actions -->
      <div class="filter-actions">
        <button
          type="button"
          class="btn-query"
          :disabled="isDisabled"
          aria-label="查詢"
          @click="handleSubmit"
        >
          {{ loading ? '查詢中...' : '查詢' }}
        </button>
        <button
          type="button"
          class="btn-clear"
          :disabled="isDisabled"
          aria-label="清除篩選"
          @click="handleClear"
        >
          清除
        </button>
      </div>
    </div>

    <!-- Validation error -->
    <p v-if="dateError" class="date-error" role="alert" aria-live="polite">
      {{ dateError }}
    </p>
  </div>
</template>
