<script setup>
import { computed } from 'vue';

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
    color: 'var(--color-token-h3b82f6)',
  },
  {
    label: 'LOT 數量',
    value: formatNumber(props.kpi.lot_count),
    unit: 'lots',
    color: 'var(--color-brand-500)',
  },
  {
    label: '不良總數',
    value: formatNumber(props.kpi.total_defect_qty),
    unit: 'pcs',
    color: 'var(--color-token-hef4444)',
  },
  {
    label: '不良率',
    value: formatRate(props.kpi.total_defect_rate),
    unit: '%',
    color: 'var(--color-token-hf59e0b)',
  },
  {
    label: '首要不良原因',
    value: props.kpi.top_loss_reason || '-',
    unit: '',
    color: 'var(--color-accent-500)',
    isText: true,
  },
  {
    label: '上游關聯機台',
    value: formatNumber(props.kpi.affected_machine_count),
    unit: '台',
    color: 'var(--color-token-h10b981)',
  },
]);

const forwardCards = computed(() => [
  {
    label: '偵測批次數',
    value: formatNumber(props.kpi.detection_lot_count),
    unit: 'lots',
    color: 'var(--color-token-h3b82f6)',
  },
  {
    label: '偵測不良數',
    value: formatNumber(props.kpi.detection_defect_qty),
    unit: 'pcs',
    color: 'var(--color-token-hef4444)',
  },
  {
    label: '追蹤批次數',
    value: formatNumber(props.kpi.tracked_lot_count),
    unit: 'lots',
    color: 'var(--color-brand-500)',
  },
  {
    label: '下游到達站數',
    value: formatNumber(props.kpi.downstream_stations_reached),
    unit: '站',
    color: 'var(--color-accent-500)',
  },
  {
    label: '下游不良總數',
    value: formatNumber(props.kpi.downstream_total_reject),
    unit: 'pcs',
    color: 'var(--color-token-hf59e0b)',
  },
  {
    label: '下游不良率',
    value: formatRate(props.kpi.downstream_reject_rate),
    unit: '%',
    color: 'var(--color-token-h10b981)',
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
    <div class="kpi-grid">
      <div
        v-for="(card, idx) in cards"
        :key="idx"
        class="kpi-card"
        :style="{ borderTopColor: card.color }"
      >
        <div class="kpi-label">{{ card.label }}</div>
        <div class="kpi-value" :class="{ 'kpi-text': card.isText }">
          <span>{{ card.value }}</span>
          <span v-if="card.unit && !card.isText" class="kpi-unit">{{ card.unit }}</span>
        </div>
      </div>
    </div>
  </section>
</template>
