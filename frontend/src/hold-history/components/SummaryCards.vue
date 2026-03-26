<script setup>
import SummaryCard from '../../shared-ui/components/SummaryCard.vue'
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue'

const props = defineProps({
  summary: {
    type: Object,
    default: () => ({
      releaseQty: 0,
      newHoldQty: 0,
      futureHoldQty: 0,
      stillOnHoldCount: 0,
      newHoldSnapshotCount: 0,
      netChange: 0,
      avgHoldHours: 0,
    }),
  },
})
</script>

<template>
  <SummaryCardGroup :columns="7">
    <SummaryCard label="On Hold 數量"     :value="summary.stillOnHoldCount"    format="number"   accent="danger" />
    <SummaryCard label="最末日新增 Hold"  :value="summary.newHoldSnapshotCount" format="number"   accent="warning" />
    <SummaryCard label="累計新增 Hold"    :value="summary.newHoldQty"           format="number"   accent="danger" />
    <SummaryCard label="累計 Release"     :value="summary.releaseQty"           format="number"   accent="success" />
    <SummaryCard label="累計 Future Hold" :value="summary.futureHoldQty"        format="number"   accent="warning" />
    <SummaryCard label="累計淨變動"       :value="summary.netChange"            format="number"   :accent="summary.netChange >= 0 ? 'success' : 'danger'" />
    <SummaryCard label="平均 Hold 時長"   :value="summary.avgHoldHours"         format="duration" accent="neutral">
      <template #sub>hr</template>
    </SummaryCard>
  </SummaryCardGroup>
</template>
