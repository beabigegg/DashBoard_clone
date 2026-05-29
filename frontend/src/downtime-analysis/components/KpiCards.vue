<script setup lang="ts">
import { computed } from 'vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import type { DowntimeKpiShape } from '../types';

const props = defineProps<{
  summary: DowntimeKpiShape;
}>();

function formatHours(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return `${value.toFixed(1)}`;
}

const kpi = computed(() => props.summary);
</script>

<template>
  <SummaryCardGroup columns="auto">
    <SummaryCard
      label="總停機時數"
      :value="formatHours(kpi.total_hours)"
      accent="danger"
    >
      <template #sub>UDT + SDT + EGT (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="UDT"
      :value="formatHours(kpi.udt_hours)"
      accent="udt"
    >
      <template #sub>非計畫停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="SDT"
      :value="formatHours(kpi.sdt_hours)"
      accent="sdt"
    >
      <template #sub>計畫停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="EGT"
      :value="formatHours(kpi.egt_hours)"
      accent="egt"
    >
      <template #sub>工程停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="事件數"
      :value="kpi.event_count"
      format="number"
      accent="neutral"
    >
      <template #sub>邏輯事件 (次)</template>
    </SummaryCard>

    <SummaryCard
      label="平均時長"
      :value="kpi.avg_event_min.toFixed(1)"
      accent="neutral"
    >
      <template #sub>每事件平均 (分鐘)</template>
    </SummaryCard>
  </SummaryCardGroup>
</template>
