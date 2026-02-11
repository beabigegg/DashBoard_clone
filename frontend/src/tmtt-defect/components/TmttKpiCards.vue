<script setup>
import { computed } from 'vue';

const props = defineProps({
  kpi: {
    type: Object,
    default: null,
  },
});

function fmtNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toLocaleString('zh-TW');
}

function fmtRate(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(4);
}

const cards = computed(() => {
  const value = props.kpi || {};
  return [
    { key: 'total_input', label: '投入數', display: fmtNumber(value.total_input), tone: 'neutral' },
    { key: 'lot_count', label: 'LOT 數', display: fmtNumber(value.lot_count), tone: 'neutral' },
    { key: 'print_defect_qty', label: '印字不良數', display: fmtNumber(value.print_defect_qty), tone: 'danger' },
    { key: 'print_defect_rate', label: '印字不良率', display: fmtRate(value.print_defect_rate), unit: '%', tone: 'danger' },
    { key: 'lead_defect_qty', label: '腳型不良數', display: fmtNumber(value.lead_defect_qty), tone: 'warning' },
    { key: 'lead_defect_rate', label: '腳型不良率', display: fmtRate(value.lead_defect_rate), unit: '%', tone: 'warning' },
  ];
});
</script>

<template>
  <div class="tmtt-kpi-grid">
    <article
      v-for="card in cards"
      :key="card.key"
      class="tmtt-kpi-card"
      :class="`tone-${card.tone}`"
    >
      <p class="tmtt-kpi-label">{{ card.label }}</p>
      <p class="tmtt-kpi-value">
        {{ card.display }}
        <span v-if="card.unit" class="tmtt-kpi-unit">{{ card.unit }}</span>
      </p>
    </article>
  </div>
</template>
