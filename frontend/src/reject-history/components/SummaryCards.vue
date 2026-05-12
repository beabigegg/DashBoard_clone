<script setup lang="ts">
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';

interface KpiCard {
  key: string;
  label: string;
  value: number;
  lane: string;
  isPct: boolean;
}

defineProps<{
  cards?: KpiCard[];
}>();

const LANE_ACCENT_MAP: Record<string, string> = {
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
