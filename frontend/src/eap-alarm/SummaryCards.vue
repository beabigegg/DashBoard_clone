<script setup lang="ts">
import SummaryCard from '../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../shared-ui/components/SummaryCardGroup.vue';

interface TopEquipment {
  eqp_id: string;
  alarm_count: number;
}

interface SummaryData {
  total_alarm_count: number;
  affected_equipment_count: number;
  affected_lot_count: number;
  top_equipment: TopEquipment | null;
}

defineProps<{
  summary: SummaryData;
  loading?: boolean;
}>();
</script>

<template>
  <SummaryCardGroup :columns="4">
    <SummaryCard
      label="總 ALARM 數"
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
      label="受影響 LOT 數"
      :value="summary.affected_lot_count"
      format="number"
      accent="neutral"
    />
    <SummaryCard
      :label="summary.top_equipment ? `最多 ALARM 機台：${summary.top_equipment.eqp_id}` : '最多 ALARM 機台'"
      :value="summary.top_equipment ? summary.top_equipment.alarm_count : 0"
      format="number"
      accent="warning"
    />
  </SummaryCardGroup>
</template>
