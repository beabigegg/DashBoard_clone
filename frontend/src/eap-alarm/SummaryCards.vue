<script setup lang="ts">
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';

interface SummaryData {
  total_alarm_count: number;
  affected_equipment_count: number;
  unresolved_count: number;
  avg_duration_minutes: number | null;
}

defineProps<{
  summary: SummaryData;
  loading?: boolean;
}>();
</script>

<template>
  <SummaryCardGroup :columns="4">
    <SummaryCard
      label="ALARM 發生次數"
      :value="summary.total_alarm_count"
      format="number"
      accent="danger"
    />
    <SummaryCard
      label="受影響機台數"
      :value="summary.affected_equipment_count"
      format="number"
      accent="info"
    />
    <SummaryCard
      label="尚未解除"
      :value="summary.unresolved_count"
      format="number"
      accent="warning"
    />
    <SummaryCard
      label="平均排除時間（分鐘）"
      :value="summary.avg_duration_minutes ?? '—'"
      accent="neutral"
    />
  </SummaryCardGroup>
</template>
