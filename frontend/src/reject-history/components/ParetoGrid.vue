<script setup lang="ts">
import ParetoSection from './ParetoSection.vue';

interface ParetoItem {
  reason: string;
  metric_value: number;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  count: number;
  pct: number;
  cumPct: number;
}

interface ParetoDimensionData {
  items?: ParetoItem[];
  dimension?: string;
  metric_mode?: string;
}

const DIMENSIONS: { key: string; label: string }[] = [
  { key: 'reason', label: '不良原因' },
  { key: 'package', label: 'PACKAGE' },
  { key: 'type', label: 'TYPE' },
];

const props = defineProps<{
  paretoData?: Record<string, ParetoDimensionData>;
  paretoSelections?: Record<string, string[]>;
  loading?: boolean;
  metricLabel?: string;
  selectedDates?: string[];
  displayScope?: string;
}>();

const emit = defineEmits<{
  (e: 'item-toggle', dimension: string, value: string): void;
}>();

function onItemToggle(dimension: string, value: string): void {
  emit('item-toggle', dimension, value);
}
</script>

<template>
  <div class="pareto-grid">
    <ParetoSection
      v-for="dim in DIMENSIONS"
      :key="dim.key"
      :dimension="dim.key"
      :dimension-label="dim.label"
      :items="paretoData[dim.key]?.items || []"
      :selected-values="paretoSelections[dim.key] || []"
      :selected-dates="selectedDates"
      :metric-label="metricLabel"
      :display-scope="displayScope"
      :loading="loading"
      @item-toggle="onItemToggle(dim.key, $event)"
    />
  </div>
</template>
