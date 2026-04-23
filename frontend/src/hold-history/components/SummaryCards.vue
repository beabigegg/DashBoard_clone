<script setup>
import SummaryCard from '../../shared-ui/components/SummaryCard.vue'
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue'

const FUTURE_HOLD_TOOLTIP =
  '當下仍標記為 Future Hold 的總量。此指標依 PJMES043 原廠邏輯（同工單同原因的重複 Hold 且有 Future Hold 備註）計算。lot release 後 MES 可能清除備註，導致歷史日期的數值隨時間衰減。若需穩定指標請參考「品質重複觸發」。'

const REPEAT_QUALITY_TOOLTIP =
  '同工單同原因的 quality Hold 再次發生總量（基於歷史重複推斷，不依賴 FutureHold 備註，值不會衰減）'

const props = defineProps({
  summary: {
    type: Object,
    default: () => ({
      releaseQty: 0,
      newHoldQty: 0,
      futureHoldQty: 0,
      repeatQualityHoldQty: 0,
      stillOnHoldCount: 0,
      newHoldSnapshotCount: 0,
      netChange: 0,
      avgReleasedHours: 0,
      avgOnHoldHours: 0,
      maxReleasedHours: 0,
      maxOnHoldHours: 0,
    }),
  },
})
</script>

<template>
  <SummaryCardGroup :columns="11">
    <SummaryCard label="On Hold 數量"        :value="summary.stillOnHoldCount"       format="number"   accent="danger" />
    <SummaryCard label="最末日新增 Hold"     :value="summary.newHoldSnapshotCount"    format="number"   accent="warning" />
    <SummaryCard label="累計新增 Hold"       :value="summary.newHoldQty"              format="number"   accent="danger" />
    <SummaryCard label="累計 Release"        :value="summary.releaseQty"              format="number"   accent="success" />
    <SummaryCard label="累計 Future Hold"    :value="summary.futureHoldQty"           format="number"   accent="warning" :tooltip="FUTURE_HOLD_TOOLTIP" />
    <SummaryCard label="品質重複觸發"        :value="summary.repeatQualityHoldQty"    format="number"   accent="danger"  :tooltip="REPEAT_QUALITY_TOOLTIP" />
    <SummaryCard label="累計淨變動"          :value="summary.netChange"               format="number"   :accent="summary.netChange >= 0 ? 'success' : 'danger'" />
    <SummaryCard label="已解除平均時長"      :value="summary.avgReleasedHours"        format="duration" accent="neutral">
      <template #sub>hr</template>
    </SummaryCard>
    <SummaryCard label="持續 Hold 平均時長"  :value="summary.avgOnHoldHours"          format="duration" accent="neutral">
      <template #sub>hr</template>
    </SummaryCard>
    <SummaryCard label="已解除最長時長"      :value="summary.maxReleasedHours"        format="duration" accent="neutral">
      <template #sub>hr</template>
    </SummaryCard>
    <SummaryCard label="持續 Hold 最長時長" :value="summary.maxOnHoldHours"          format="duration" accent="neutral">
      <template #sub>hr</template>
    </SummaryCard>
  </SummaryCardGroup>
</template>
