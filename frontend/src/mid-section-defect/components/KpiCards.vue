<script setup>
import { computed } from 'vue';

import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';

const props = defineProps({
  kpi: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  direction: {
    type: String,
    default: 'backward',
  },
  stationLabel: {
    type: String,
    default: '測試',
  },
});

const backwardCards = computed(() => [
  {
    label: `${props.stationLabel} 投入數`,
    value: formatNumber(props.kpi.total_input),
    unit: 'pcs',
    accent: 'info',
  },
  {
    label: 'LOT 數量',
    value: formatNumber(props.kpi.lot_count),
    unit: 'lots',
    accent: 'brand',
  },
  {
    label: '不良總數',
    value: formatNumber(props.kpi.total_defect_qty),
    unit: 'pcs',
    accent: 'danger',
  },
  {
    label: '不良率',
    value: formatRate(props.kpi.total_defect_rate),
    unit: '%',
    accent: 'warning',
  },
  {
    label: '首要不良原因',
    value: props.kpi.top_loss_reason || '-',
    unit: '',
    accent: 'neutral',
  },
  {
    label: '上游關聯機台',
    value: formatNumber(props.kpi.affected_machine_count),
    unit: '台',
    accent: 'success',
  },
]);

const forwardCards = computed(() => [
  {
    label: '偵測批次數',
    value: formatNumber(props.kpi.detection_lot_count),
    unit: 'lots',
    accent: 'info',
  },
  {
    label: '偵測不良數',
    value: formatNumber(props.kpi.detection_defect_qty),
    unit: 'pcs',
    accent: 'danger',
  },
  {
    label: '追蹤批次數',
    value: formatNumber(props.kpi.tracked_lot_count),
    unit: 'lots',
    accent: 'brand',
  },
  {
    label: '下游到達站數',
    value: formatNumber(props.kpi.downstream_stations_reached),
    unit: '站',
    accent: 'neutral',
  },
  {
    label: '下游不良總數',
    value: formatNumber(props.kpi.downstream_total_reject),
    unit: 'pcs',
    accent: 'warning',
  },
  {
    label: '下游不良率',
    value: formatRate(props.kpi.downstream_reject_rate),
    unit: '%',
    accent: 'success',
  },
]);

const cards = computed(() => (
  props.direction === 'forward' ? forwardCards.value : backwardCards.value
));

function formatNumber(v) {
  if (v == null || v === 0) return '0';
  return Number(v).toLocaleString();
}

function formatRate(v) {
  if (v == null) return '0.00';
  return Number(v).toFixed(2);
}
</script>

<template>
  <section class="kpi-section">
    <SummaryCardGroup :columns="cards.length">
      <SummaryCard
        v-for="(card, idx) in cards"
        :key="idx"
        :label="card.label"
        :value="card.value"
        :accent="card.accent"
      >
        <template v-if="card.unit" #sub>{{ card.unit }}</template>
      </SummaryCard>
    </SummaryCardGroup>
  </section>
</template>
