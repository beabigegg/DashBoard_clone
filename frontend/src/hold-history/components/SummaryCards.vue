<script setup lang="ts">
import SummaryCard from '../../shared-ui/components/SummaryCard.vue'
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue'

function rawFor(v: number | undefined | null): number | undefined {
  if (v == null) return undefined;
  return Math.abs(v) >= 1000 ? v : undefined;
}

// ── Range mode tooltips ──────────────────────────────────────────────────────
const RANGE_FUTURE_HOLD_TOOLTIP =
  '有標註 FUTURE HOLD 備註的 Hold 總量（PJMES043 原廠邏輯）。lot release 後 MES 可能清除備註，導致歷史數值衰減。'

const RANGE_REPEAT_QUALITY_TOOLTIP =
  '同一 Lot 因相同品質原因被重複 Hold 的數量，不因 lot release 衰減'

// ── Today mode tooltips ──────────────────────────────────────────────────────
const TODAY_ON_HOLD_LOTS_TOOLTIP =
  '當日-1 07:30 → 當日 07:30 視為當日，班次結束時仍在 Hold 的 LOT 件數'

const TODAY_ON_HOLD_QTY_TOOLTIP =
  '班次結束時仍在 Hold 的總 QTY'

const TODAY_REPEAT_QUALITY_TOOLTIP =
  '同一 Lot 因相同品質原因被重複 Hold 的數量，不因 lot release 衰減'

const TODAY_AVG_HOURS_TOOLTIP =
  '班次結束時仍在 Hold 的 lot 之平均時長，時長計算至 07:30 當日（班次結束點）'

// ── Current mode tooltips ────────────────────────────────────────────────────
const CURRENT_ON_HOLD_LOTS_TOOLTIP =
  '目前真實未釋放的所有 LOT 件數（RELEASETXNDATE IS NULL）'

const CURRENT_ON_HOLD_QTY_TOOLTIP =
  '目前真實未釋放的所有 QTY 加總'

const CURRENT_REPEAT_QUALITY_TOOLTIP =
  '同一 Lot 因相同品質原因被重複 Hold 的數量，不因 lot release 衰減'

const CURRENT_AVG_HOURS_TOOLTIP =
  '目前仍在 Hold 的 lot 之平均時長，以 SYSDATE 即時計算'

// TODO: type — summary shape varies by mode (range/today/current); use numeric-value Record for now
interface SummaryData {
  [key: string]: number | undefined;
}

interface Props {
  summary?: SummaryData;
  mode?: string;
}

const props = withDefaults(defineProps<Props>(), {
  summary: () => ({}),
  mode: 'range',
})
</script>

<template>
  <!-- Range mode: 9-card layout -->
  <template v-if="mode === 'range'">
    <SummaryCardGroup :columns="9">
      <SummaryCard
        label="累計新增"
        :value="summary.newHoldQty ?? 0"
        format="number"
        accent="danger"
        :sub-value="rawFor(summary.newHoldQty)"
      />
      <SummaryCard
        label="累計 Release"
        :value="summary.releaseQty ?? 0"
        format="number"
        accent="success"
        :sub-value="rawFor(summary.releaseQty)"
      />
      <SummaryCard
        label="累計 FH"
        :value="summary.futureHoldQty ?? 0"
        format="number"
        accent="warning"
        :sub-value="rawFor(summary.futureHoldQty)"
      />
      <SummaryCard
        label="品質重複 HOLD"
        :value="summary.repeatQualityHoldQty ?? 0"
        format="number"
        accent="danger"
        :tooltip="RANGE_REPEAT_QUALITY_TOOLTIP"
        :sub-value="rawFor(summary.repeatQualityHoldQty)"
      />
      <SummaryCard
        label="累計淨變動"
        :value="summary.netChange ?? 0"
        format="number"
        :accent="(summary.netChange ?? 0) >= 0 ? 'success' : 'danger'"
        :sub-value="rawFor(summary.netChange)"
      />
      <SummaryCard
        label="RELEASE 平均時長"
        :value="summary.avgReleasedHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
      <SummaryCard
        label="ON HOLD 平均時長"
        :value="summary.avgOnHoldHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
      <SummaryCard
        label="RELEASE 最長時長"
        :value="summary.maxReleasedHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
      <SummaryCard
        label="ON HOLD 最長時長"
        :value="summary.maxOnHoldHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
    </SummaryCardGroup>
  </template>

  <!-- Today mode: 8-card layout -->
  <template v-else-if="mode === 'today'">
    <SummaryCardGroup :columns="8">
      <SummaryCard
        label="ON HOLD (LOTs)"
        :value="summary.onHoldLots ?? 0"
        format="number"
        accent="danger"
        :tooltip="TODAY_ON_HOLD_LOTS_TOOLTIP"
        :sub-value="rawFor(summary.onHoldLots)"
      />
      <SummaryCard
        label="ON HOLD (QTY)"
        :value="summary.onHoldQty ?? 0"
        format="number"
        accent="danger"
        :tooltip="TODAY_ON_HOLD_QTY_TOOLTIP"
        :sub-value="rawFor(summary.onHoldQty)"
      />
      <SummaryCard
        label="當日新增"
        :value="summary.todayNewQty ?? 0"
        format="number"
        accent="warning"
        :sub-value="rawFor(summary.todayNewQty)"
      />
      <SummaryCard
        label="當日 Release"
        :value="summary.todayReleaseQty ?? 0"
        format="number"
        accent="success"
        :sub-value="rawFor(summary.todayReleaseQty)"
      />
      <SummaryCard
        label="當日 Future Hold"
        :value="summary.todayFutureHoldQty ?? 0"
        format="number"
        accent="warning"
        :sub-value="rawFor(summary.todayFutureHoldQty)"
      />
      <SummaryCard
        label="品質重複 HOLD"
        :value="summary.repeatQualityHoldQty ?? 0"
        format="number"
        accent="danger"
        :tooltip="TODAY_REPEAT_QUALITY_TOOLTIP"
        :sub-value="rawFor(summary.repeatQualityHoldQty)"
      />
      <SummaryCard
        label="ON HOLD 平均時長"
        :value="summary.onHoldAvgHours ?? 0"
        format="duration"
        accent="neutral"
        :tooltip="TODAY_AVG_HOURS_TOOLTIP"
      >
        <template #sub>hr</template>
      </SummaryCard>
      <SummaryCard
        label="ON HOLD 最長時長"
        :value="summary.onHoldMaxHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
    </SummaryCardGroup>
  </template>

  <!-- Current mode: 8-card layout -->
  <template v-else-if="mode === 'current'">
    <SummaryCardGroup :columns="8">
      <SummaryCard
        label="ON HOLD (LOTs)"
        :value="summary.onHoldLots ?? 0"
        format="number"
        accent="danger"
        :tooltip="CURRENT_ON_HOLD_LOTS_TOOLTIP"
        :sub-value="rawFor(summary.onHoldLots)"
      />
      <SummaryCard
        label="ON HOLD (QTY)"
        :value="summary.onHoldQty ?? 0"
        format="number"
        accent="danger"
        :tooltip="CURRENT_ON_HOLD_QTY_TOOLTIP"
        :sub-value="rawFor(summary.onHoldQty)"
      />
      <SummaryCard
        label="現況新增"
        :value="summary.currentNewQty ?? 0"
        format="number"
        accent="warning"
        :sub-value="rawFor(summary.currentNewQty)"
      />
      <SummaryCard
        label="現況 Release"
        :value="summary.currentReleaseQty ?? 0"
        format="number"
        accent="success"
        :sub-value="rawFor(summary.currentReleaseQty)"
      />
      <SummaryCard
        label="現況 Future Hold"
        :value="summary.currentFutureHoldQty ?? 0"
        format="number"
        accent="warning"
        :sub-value="rawFor(summary.currentFutureHoldQty)"
      />
      <SummaryCard
        label="品質重複 HOLD"
        :value="summary.repeatQualityHoldQty ?? 0"
        format="number"
        accent="danger"
        :tooltip="CURRENT_REPEAT_QUALITY_TOOLTIP"
        :sub-value="rawFor(summary.repeatQualityHoldQty)"
      />
      <SummaryCard
        label="ON HOLD 平均時長"
        :value="summary.onHoldAvgHours ?? 0"
        format="duration"
        accent="neutral"
        :tooltip="CURRENT_AVG_HOURS_TOOLTIP"
      >
        <template #sub>hr</template>
      </SummaryCard>
      <SummaryCard
        label="ON HOLD 最長時長"
        :value="summary.onHoldMaxHours ?? 0"
        format="duration"
        accent="neutral"
      >
        <template #sub>hr</template>
      </SummaryCard>
    </SummaryCardGroup>
  </template>
</template>
