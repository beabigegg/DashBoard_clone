<script setup lang="ts">
import { computed } from 'vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import type { DowntimeKpiShape } from '../types';

const props = defineProps<{
  summary: DowntimeKpiShape;
  selectedStatusTypes?: string[] | null;
}>();

const emit = defineEmits<{
  (e: 'click-status', statusTypes: string[] | null): void;
}>();

function formatHours(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return `${value.toFixed(1)}`;
}

const kpi = computed(() => props.summary);

const hasStatusFilter = computed(
  () => !!(props.selectedStatusTypes?.length)
);

function isActive(status: string): boolean {
  return props.selectedStatusTypes?.length === 1 && props.selectedStatusTypes[0] === status;
}

function handleStatusCardClick(status: string): void {
  if (isActive(status)) {
    emit('click-status', null);
  } else {
    emit('click-status', [status]);
  }
}
</script>

<template>
  <SummaryCardGroup columns="auto">
    <SummaryCard
      label="總停機時數"
      :value="formatHours(kpi.total_hours)"
      accent="danger"
      :clickable="hasStatusFilter"
      :active="false"
      tooltip="點擊清除篩選"
      @click="hasStatusFilter && emit('click-status', null)"
    >
      <template #sub>UDT + SDT + EGT (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="UDT"
      :value="formatHours(kpi.udt_hours)"
      accent="udt"
      :clickable="true"
      :active="isActive('UDT')"
      tooltip="點擊篩選 UDT 非計畫停機"
      @click="handleStatusCardClick('UDT')"
    >
      <template #sub>非計畫停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="SDT"
      :value="formatHours(kpi.sdt_hours)"
      accent="sdt"
      :clickable="true"
      :active="isActive('SDT')"
      tooltip="點擊篩選 SDT 計畫停機"
      @click="handleStatusCardClick('SDT')"
    >
      <template #sub>計畫停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="EGT"
      :value="formatHours(kpi.egt_hours)"
      accent="egt"
      :clickable="true"
      :active="isActive('EGT')"
      tooltip="點擊篩選 EGT 工程停機"
      @click="handleStatusCardClick('EGT')"
    >
      <template #sub>工程停機 (小時)</template>
    </SummaryCard>

    <SummaryCard
      label="事件數"
      :value="kpi.event_count"
      format="number"
      accent="neutral"
    >
      <template #sub>次</template>
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
