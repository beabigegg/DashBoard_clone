<script setup lang="ts">
import { useRouter } from 'vue-router';

import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import StatusMixDonut from '../../wip-overview/components/StatusMixDonut.vue';

interface WipStatusEntry {
  lots?: number;
  qtyPcs?: number;
}

interface WipSummary {
  totalLots?: number;
  totalQtyPcs?: number;
  byWipStatus?: Record<string, WipStatusEntry>;
}

const props = defineProps<{
  summary: WipSummary | null;
}>();

const router = useRouter();

function goToWipOverview(): void {
  router.push('/wip-overview');
}

function statusLots(key: string): number {
  return Number(props.summary?.byWipStatus?.[key]?.lots ?? 0);
}

function statusQty(key: string): number {
  return Number(props.summary?.byWipStatus?.[key]?.qtyPcs ?? 0);
}
</script>

<template>
  <section class="card ui-card" data-testid="dashboard-wip-section">
    <div
      class="card-header ui-card-header dh-card-header--nav"
      role="button"
      tabindex="0"
      title="前往 WIP 即時概況"
      @click="goToWipOverview"
      @keydown.enter="goToWipOverview"
      @keydown.space.prevent="goToWipOverview"
    >
      <div class="card-title ui-card-title">WIP 概況</div>
      <span class="dh-nav-arrow" aria-hidden="true">›</span>
    </div>
    <div class="card-body ui-card-body">
      <div class="dh-wip-top-row">
        <SummaryCard label="TOTAL LOTS" :value="summary?.totalLots ?? 0" format="number" accent="brand" />
        <SummaryCard label="TOTAL QTY · PCS" :value="summary?.totalQtyPcs ?? 0" format="number" accent="brand" />
        <StatusMixDonut :data="summary?.byWipStatus || {}" mode="lots" />
        <StatusMixDonut :data="summary?.byWipStatus || {}" mode="pcs" />
      </div>

      <SummaryCardGroup columns="auto">
        <SummaryCard
          label="RUN"
          :value="statusLots('run')"
          format="number"
          :sub-value="statusQty('run')"
          sub-unit=" PCS"
          accent="success"
        />
        <SummaryCard
          label="QUEUE"
          :value="statusLots('queue')"
          format="number"
          :sub-value="statusQty('queue')"
          sub-unit=" PCS"
          accent="warning"
        />
        <SummaryCard
          label="品質異常"
          :value="statusLots('qualityHold')"
          format="number"
          :sub-value="statusQty('qualityHold')"
          sub-unit=" PCS"
          accent="danger"
        />
        <SummaryCard
          label="非品質異常"
          :value="statusLots('nonQualityHold')"
          format="number"
          :sub-value="statusQty('nonQualityHold')"
          sub-unit=" PCS"
          accent="warning"
        />
      </SummaryCardGroup>
    </div>
  </section>
</template>
