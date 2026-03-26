<script setup>
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';

defineProps({
  cards: { type: Array, default: () => [] },
});

const LANE_ACCENT_MAP = {
  reject: 'danger',
  defect: 'info',
  neutral: 'neutral',
};
</script>

<template>
  <SummaryCardGroup :columns="6">
    <SummaryCard
      v-for="card in cards"
      :key="card.key"
      :label="card.label"
      :value="card.value"
      :format="card.isPct ? 'percent' : 'number'"
      :accent="LANE_ACCENT_MAP[card.lane] || 'neutral'"
    />
  </SummaryCardGroup>
</template>
