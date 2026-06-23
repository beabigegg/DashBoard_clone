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
  (e: 'filter-change', state: FilterState): void;
  (e: 'update-state', patch: Partial<FilterState>): void;
  (e: 'dimension-closed', dimension: string): void;
  (e: 'clear'): void;
}>();

const MAX_QUERY_DAYS = 730;
const dateError = ref('');

function validateDates(): string {
  if (!props.state.start_date || !props.state.end_date) return '請先設定開始與結束日期';
  const start = new Date(props.state.start_date);
  const end = new Date(props.state.end_date);
  const diffDays = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
  if (diffDays < 0) return '結束日期必須大於起始日期';
  if (diffDays > MAX_QUERY_DAYS) return '查詢範圍不可超過兩年';
  return '';
}

function handleSubmit(): void {
  const err = validateDates();
  if (err) { dateError.value = err; return; }
  dateError.value = '';
  emit('filter-change', { ...props.state });
}

function handleClear(): void {
  dateError.value = '';
  emit('clear');
}

function handleStartDate(e: Event): void {
  emit('update-state', { start_date: (e.target as HTMLInputElement).value });
}

function handleEndDate(e: Event): void {
  emit('update-state', { end_date: (e.target as HTMLInputElement).value });
}

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
  <section class="section-card">
    <div class="section-inner filter-rows">
      <!-- Row 1: 日期區間 & 粒度 -->
      <div class="filter-row">
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
      </div>

      <!-- Row 2: 工站群組 & 型號 & 機台 & 封裝群組 -->
      <div class="filter-row">
        <div class="filter-field">
          <label>工站群組</label>
          <MultiSelect
            :model-value="state.workcenter_groups"
            :options="options.workcenter_groups"
            :disabled="isDisabled"
            placeholder="全部站點"
            @update:model-value="emit('update-state', { workcenter_groups: $event })"
            @dropdown-close="emit('dimension-closed', 'workcenter_groups')"
          />
        </div>
        <div class="filter-field">
          <label>設備區域</label>
          <MultiSelect
            :model-value="state.locations"
            :options="options.locations"
            :disabled="isDisabled"
            placeholder="全部區域"
            @update:model-value="emit('update-state', { locations: $event })"
            @dropdown-close="emit('dimension-closed', 'locations')"
          />
        </div>
        <div class="filter-field">
          <label>設備型號</label>
          <MultiSelect
            :model-value="state.families"
            :options="options.families"
            :disabled="isDisabled"
            placeholder="全部型號"
            @update:model-value="emit('update-state', { families: $event })"
            @dropdown-close="emit('dimension-closed', 'families')"
          />
        </div>
        <div class="filter-field">
          <label>設備</label>
          <MultiSelect
            :model-value="state.resource_ids"
            :options="options.resources"
            :disabled="isDisabled"
            placeholder="全部設備"
            searchable
            @update:model-value="emit('update-state', { resource_ids: $event })"
            @dropdown-close="emit('dimension-closed', 'resource_ids')"
          />
        </div>
        <div class="filter-field">
          <label>封裝群組</label>
          <MultiSelect
            :model-value="state.package_groups"
            :options="options.package_groups"
            :disabled="isDisabled"
            placeholder="全部封裝群組"
            @update:model-value="emit('update-state', { package_groups: $event })"
            @dropdown-close="emit('dimension-closed', 'package_groups')"
          />
        </div>
      </div>

      <!-- Row 3: 設備類型 checkboxes + 查詢/清除 -->
      <div class="filter-row">
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
        <div class="filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            :disabled="isDisabled"
            aria-label="查詢"
            @click="handleSubmit"
          >
            {{ loading ? '查詢中...' : '查詢' }}
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--ghost"
            :disabled="isDisabled"
            aria-label="清除篩選"
            @click="handleClear"
          >
            清除條件
          </button>
        </div>
      </div>

      <p v-if="dateError" class="date-error" role="alert" aria-live="polite">
        {{ dateError }}
      </p>
    </div>
  </section>
</template>
