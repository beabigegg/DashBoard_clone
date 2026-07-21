<script setup lang="ts">
import { useRouter } from 'vue-router';

import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import WorkcenterOuRings from '../../resource-status/components/WorkcenterOuRings.vue';
import { MATRIX_STATUS_COLUMNS, OU_BADGE_THRESHOLDS } from '../../resource-shared/constants';

interface EquipmentSummary {
  total_count?: number;
  by_status?: Record<string, number>;
  ou_pct?: number;
  availability_pct?: number;
}

interface EquipmentItem {
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  EQUIPMENTASSETSSTATUS: string;
}

const props = defineProps<{
  summary: EquipmentSummary | null;
  equipment: EquipmentItem[];
}>();

const STATUS_ACCENT_MAP: Record<string, string> = {
  PRD: 'prd',
  SBY: 'sby',
  UDT: 'udt',
  SDT: 'sdt',
  EGT: 'egt',
  NST: 'nst',
  OTHER: 'neutral',
};

function resolveOuAccent(value: number | undefined): string {
  const pct = Number(value || 0);
  if (pct >= OU_BADGE_THRESHOLDS.high) return 'success';
  if (pct >= OU_BADGE_THRESHOLDS.medium) return 'warning';
  return 'danger';
}

function statusValue(status: string): number {
  return Number(props.summary?.by_status?.[status] ?? 0);
}

const router = useRouter();

function goToResourceStatus(): void {
  router.push('/resource');
}
</script>

<template>
  <section class="card ui-card" data-testid="dashboard-equipment-section">
    <div
      class="card-header ui-card-header dh-card-header--nav"
      role="button"
      tabindex="0"
      title="前往設備即時概況"
      @click="goToResourceStatus"
      @keydown.enter="goToResourceStatus"
      @keydown.space.prevent="goToResourceStatus"
    >
      <div class="card-title ui-card-title">設備即時概況（重點機台）</div>
      <span class="dh-nav-arrow" aria-hidden="true">›</span>
    </div>
    <div class="card-body ui-card-body">
      <SummaryCardGroup columns="auto">
        <SummaryCard
          label="OU%"
          :value="summary?.ou_pct ?? 0"
          format="percent"
          :accent="resolveOuAccent(summary?.ou_pct)"
        >
          <template #sub>稼動率</template>
        </SummaryCard>
        <SummaryCard
          label="AVAIL%"
          :value="summary?.availability_pct ?? 0"
          format="percent"
          :accent="resolveOuAccent(summary?.availability_pct)"
        >
          <template #sub>可用率</template>
        </SummaryCard>
        <SummaryCard
          v-for="status in MATRIX_STATUS_COLUMNS"
          :key="status"
          :label="status"
          :value="statusValue(status)"
          format="number"
          :accent="STATUS_ACCENT_MAP[status] || 'neutral'"
        />
        <SummaryCard label="Total" :value="summary?.total_count ?? 0" format="number" accent="brand">
          <template #sub>重點設備總數</template>
        </SummaryCard>
      </SummaryCardGroup>

      <WorkcenterOuRings :equipment="equipment" />
    </div>
  </section>
</template>
