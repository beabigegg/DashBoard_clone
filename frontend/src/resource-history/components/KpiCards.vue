<script setup lang="ts">
import { computed } from 'vue'
import SummaryCard from '../../shared-ui/components/SummaryCard.vue'
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue'
import { buildResourceKpiFromHours } from '../../core/compute'
import type { ResourceKpi, ResourceHours } from '../../core/compute'
import { OU_BADGE_THRESHOLDS } from '../../resource-shared/constants'

const props = withDefaults(defineProps<{
  kpi?: Record<string, unknown>;
}>(), {
  kpi: () => ({}),
})

function resolveOuAccent(value: unknown): string {
  const pct = Number(value || 0)
  if (pct >= OU_BADGE_THRESHOLDS.high) return 'success'
  if (pct >= OU_BADGE_THRESHOLDS.medium) return 'warning'
  return 'danger'
}

function formatHours(value: unknown): string {
  const hours = Number(value || 0)
  if (hours >= 1000) return `${(hours / 1000).toFixed(1)}K`
  return `${hours.toFixed(1)}`
}

const kpi = computed((): ResourceKpi & ResourceHours & { machine_count?: number | null } => ({
  ...props.kpi,
  ...buildResourceKpiFromHours(props.kpi),
}))
</script>

<template>
  <SummaryCardGroup columns="auto">
    <SummaryCard
      label="OU%"
      :value="kpi.ou_pct"
      format="percent"
      :accent="resolveOuAccent(kpi.ou_pct)"
    >
      <template #sub>稼動率</template>
    </SummaryCard>

    <SummaryCard
      label="OEE%"
      :value="kpi.oee_pct"
      format="percent"
      :accent="resolveOuAccent(kpi.oee_pct)"
    >
      <template #sub>綜合設備效率</template>
    </SummaryCard>

    <SummaryCard
      label="AVAIL%"
      :value="kpi.availability_pct"
      format="percent"
      :accent="resolveOuAccent(kpi.availability_pct)"
    >
      <template #sub>可用率</template>
    </SummaryCard>

    <SummaryCard label="PRD" :value="formatHours(kpi.prd_hours)" accent="prd">
      <template #sub>生產 ({{ Number(kpi.prd_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard label="SBY" :value="formatHours(kpi.sby_hours)" accent="sby">
      <template #sub>待機 ({{ Number(kpi.sby_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard label="UDT" :value="formatHours(kpi.udt_hours)" accent="udt">
      <template #sub>非計畫停機 ({{ Number(kpi.udt_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard label="SDT" :value="formatHours(kpi.sdt_hours)" accent="sdt">
      <template #sub>計畫停機 ({{ Number(kpi.sdt_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard label="EGT" :value="formatHours(kpi.egt_hours)" accent="egt">
      <template #sub>工程 ({{ Number(kpi.egt_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard label="NST" :value="formatHours(kpi.nst_hours)" accent="nst">
      <template #sub>未排程 ({{ Number(kpi.nst_pct || 0).toFixed(1) }}%)</template>
    </SummaryCard>

    <SummaryCard
      label="機台數"
      :value="kpi.machine_count"
      format="number"
      accent="neutral"
    >
      <template #sub>設備總數</template>
    </SummaryCard>
  </SummaryCardGroup>
</template>
