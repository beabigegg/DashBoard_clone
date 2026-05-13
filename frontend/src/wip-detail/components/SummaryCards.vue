<script setup lang="ts">
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';

defineProps({
  summary: {
    type: Object,
    default: null,
  },
  activeStatus: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

const cards = [
  { key: 'run', label: 'RUN', accent: 'success', valueKey: 'runLots' },
  { key: 'queue', label: 'QUEUE', accent: 'warning', valueKey: 'queueLots' },
  { key: 'quality-hold', label: '品質異常', accent: 'danger', valueKey: 'qualityHoldLots' },
  { key: 'non-quality-hold', label: '非品質異常', accent: 'warning', valueKey: 'nonQualityHoldLots' },
];
</script>

<template>
  <SummaryCardGroup :columns="5">
    <SummaryCard
      label="Total Lots"
      :value="summary?.totalLots"
      format="number"
      accent="brand"
    />
    <SummaryCard
      v-for="card in cards"
      :key="card.key"
      :label="card.label"
      :value="summary?.[card.valueKey]"
      format="number"
      :accent="card.accent"
      :clickable="true"
      :active="activeStatus === card.key"
      @click="emit('toggle', card.key)"
    />
  </SummaryCardGroup>
</template>
