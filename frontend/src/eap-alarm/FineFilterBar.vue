<script setup lang="ts">
import { nextTick } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface AlarmCategoryOption {
  code: number;
  label: string;
}

interface FineFilter {
  alarm_text: string[];
  alarm_category: string[];
  eqp_id: string[];
}

interface FilterOptions {
  alarm_text_options: string[];
  alarm_category_options: AlarmCategoryOption[];
  equipment_id_options: string[];
}

const props = defineProps<{
  fineFilter: FineFilter;
  filterOptions: FilterOptions;
}>();

const emit = defineEmits<{
  (e: 'change'): void;
}>();

function onAlarmTextChange(values: string[]): void {
  props.fineFilter.alarm_text = values;
  emit('change');
}

function onAlarmCategoryChange(values: string[]): void {
  props.fineFilter.alarm_category = values;
  emit('change');
}

function onEqpIdChange(values: string[]): void {
  props.fineFilter.eqp_id = values;
  emit('change');
}

// WAI-ARIA combobox close: return focus via nextTick (frontend-patterns.md)
function handleMultiSelectClose(event: Event): void {
  const trigger = event.target as HTMLElement | null;
  if (trigger) {
    nextTick(() => trigger.focus());
  }
}
</script>

<template>
  <section class="card ui-card filter-query-card fine-filter-panel">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">細部篩選 <span class="fine-filter-badge">快取內篩選</span></div>
    </div>
    <div class="card-body ui-card-body fine-filter-body">
      <div class="filter-group">
        <label class="filter-label">ALARM 訊息</label>
        <MultiSelect
          :model-value="fineFilter.alarm_text"
          :options="filterOptions.alarm_text_options"
          placeholder="全部 ALARM 訊息"
          searchable
          @update:model-value="onAlarmTextChange"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">ALARM 類別</label>
        <MultiSelect
          :model-value="fineFilter.alarm_category"
          :options="filterOptions.alarm_category_options.map((o) => o.label)"
          placeholder="全部類別"
          searchable
          @update:model-value="onAlarmCategoryChange"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">機台 ID</label>
        <MultiSelect
          :model-value="fineFilter.eqp_id"
          :options="filterOptions.equipment_id_options"
          placeholder="全部機台"
          searchable
          @update:model-value="onEqpIdChange"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>
    </div>
  </section>
</template>
