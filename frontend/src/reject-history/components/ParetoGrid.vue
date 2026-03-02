<script setup>
import ParetoSection from './ParetoSection.vue';

const DIMENSIONS = [
  { key: 'reason', label: '不良原因' },
  { key: 'package', label: 'PACKAGE' },
  { key: 'type', label: 'TYPE' },
  { key: 'workflow', label: 'WORKFLOW' },
  { key: 'workcenter', label: '站點' },
  { key: 'equipment', label: '機台' },
];

const props = defineProps({
  paretoData: { type: Object, default: () => ({}) },
  paretoSelections: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  metricLabel: { type: String, default: '報廢量' },
  selectedDates: { type: Array, default: () => [] },
  displayScope: { type: String, default: 'all' },
});

const emit = defineEmits(['item-toggle']);

function onItemToggle(dimension, value) {
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
