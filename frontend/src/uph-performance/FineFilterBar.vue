<script setup lang="ts">
import { nextTick } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface FineFilter {
  equipment_id: string[];
  package: string[];
  pj_type: string[];
  die_count: string[];
  wire_count: string[];
}

interface FilterOptions {
  equipment_id_options: string[];
  package_options: string[];
  pj_type_options: string[];
  die_count_options: string[];
  wire_count_options: string[];
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
  <section class="card ui-card filter-query-card fine-filter-panel" data-testid="ctrl-fine-filter">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">細部篩選 <span class="fine-filter-badge">快取內篩選，不重新查詢</span></div>
    </div>
    <div class="card-body ui-card-body fine-filter-body">
      <div class="filter-group">
        <label class="filter-label">機台 ID</label>
        <MultiSelect
          :model-value="fineFilter.equipment_id"
          :options="filterOptions.equipment_id_options"
          placeholder="全部機台"
          searchable
          data-testid="fine-equipment-id-select"
          @update:model-value="(v: string[]) => onFilterChange('equipment_id', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">Package / 封裝</label>
        <MultiSelect
          :model-value="fineFilter.package"
          :options="filterOptions.package_options"
          placeholder="全部 Package"
          searchable
          data-testid="fine-package-select"
          @update:model-value="(v: string[]) => onFilterChange('package', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">Type / 類型</label>
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
        <label class="filter-label">晶粒數</label>
        <MultiSelect
          :model-value="fineFilter.die_count"
          :options="filterOptions.die_count_options"
          placeholder="全部晶粒數"
          searchable
          data-testid="fine-die-count-select"
          @update:model-value="(v: string[]) => onFilterChange('die_count', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label">打線數</label>
        <MultiSelect
          :model-value="fineFilter.wire_count"
          :options="filterOptions.wire_count_options"
          placeholder="全部打線數"
          searchable
          data-testid="fine-wire-count-select"
          @update:model-value="(v: string[]) => onFilterChange('wire_count', v)"
          @dropdown-close="handleMultiSelectClose"
        />
      </div>
    </div>
  </section>
</template>
