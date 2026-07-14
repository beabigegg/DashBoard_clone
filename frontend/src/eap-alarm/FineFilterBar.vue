<script setup lang="ts">
import { nextTick } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface FineFilter {
  alarm_text: string[];
  eqp_id: string[];
  lot_id: string[];
  pj_type: string[];
  product_line: string[];
  pj_bop: string[];
}

interface FilterOptions {
  alarm_text_options: string[];
  equipment_id_options: string[];
  lot_id_options: string[];
  pj_type_options: string[];
  product_line_options: string[];
  pj_bop_options: string[];
}

const props = defineProps<{
  fineFilter: FineFilter;
  filterOptions: FilterOptions;
}>();

const emit = defineEmits<{
  (e: 'change'): void;
}>();

function onFilterChange(key: keyof FineFilter, values: string[]): void {
  props.fineFilter[key] = values;
  emit('change');
}

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
          @update:model-value="(v: string[]) => onFilterChange('alarm_text', v)"
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
          @update:model-value="(v: string[]) => onFilterChange('eqp_id', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">LOT ID</label>
        <MultiSelect
          :model-value="fineFilter.lot_id"
          :options="filterOptions.lot_id_options"
          placeholder="全部 LOT"
          searchable
          data-testid="fine-lot-id-select"
          @update:model-value="(v: string[]) => onFilterChange('lot_id', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">Type</label>
        <MultiSelect
          :model-value="fineFilter.pj_type"
          :options="filterOptions.pj_type_options"
          placeholder="全部 Type"
          searchable
          data-testid="fine-pj-type-select"
          @update:model-value="(v: string[]) => onFilterChange('pj_type', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">Package</label>
        <MultiSelect
          :model-value="fineFilter.product_line"
          :options="filterOptions.product_line_options"
          placeholder="全部 Package"
          searchable
          data-testid="fine-product-line-select"
          @update:model-value="(v: string[]) => onFilterChange('product_line', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">BOP</label>
        <MultiSelect
          :model-value="fineFilter.pj_bop"
          :options="filterOptions.pj_bop_options"
          placeholder="全部 BOP"
          searchable
          data-testid="fine-pj-bop-select"
          @update:model-value="(v: string[]) => onFilterChange('pj_bop', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>
    </div>
  </section>
</template>
