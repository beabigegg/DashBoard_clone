<script setup lang="ts">
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';

defineProps({
  summary: {
    type: Object,
    default: null,
  },
});
</script>

<template>
  <SummaryCardGroup :columns="5">
    <SummaryCard label="Total Lots" :value="summary?.totalLots" format="number" accent="brand" />
    <SummaryCard label="Total QTY" :value="summary?.totalQty" format="number" accent="brand" />
    <SummaryCard label="平均當站滯留" :value="summary?.avgAge" format="duration" accent="warning">
      <template #sub>天</template>
    </SummaryCard>
    <SummaryCard label="最久當站滯留" :value="summary?.maxAge" format="duration" accent="danger">
      <template #sub>天</template>
    </SummaryCard>
    <SummaryCard label="影響站群" :value="summary?.workcenterCount" format="number" accent="info" />
  </SummaryCardGroup>
</template>
