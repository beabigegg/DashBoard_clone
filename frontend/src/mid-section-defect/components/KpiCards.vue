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
});

const cards = computed(() => [
  {
    label: 'TMTT 投入數',
    value: formatNumber(props.kpi.total_input),
    unit: 'pcs',
    color: '#3b82f6',
  },
  {
    label: 'LOT 數量',
    value: formatNumber(props.kpi.lot_count),
    unit: 'lots',
    color: '#6366f1',
  },
  {
    label: '不良總數',
    value: formatNumber(props.kpi.total_defect_qty),
    unit: 'pcs',
    color: '#ef4444',
  },
  {
    label: '不良率',
    value: formatRate(props.kpi.total_defect_rate),
    unit: '%',
    color: '#f59e0b',
  },
  {
    label: '首要不良原因',
    value: props.kpi.top_loss_reason || '-',
    unit: '',
    color: '#8b5cf6',
    isText: true,
  },
  {
    label: '上游關聯機台',
    value: formatNumber(props.kpi.affected_machine_count),
    unit: '台',
    color: '#10b981',
  },
]);

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
