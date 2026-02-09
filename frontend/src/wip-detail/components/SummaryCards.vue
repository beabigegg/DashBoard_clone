<script setup>
const props = defineProps({
  summary: {
    type: Object,
    default: null,
  },
  activeStatus: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

const cards = [
  { key: 'run', label: 'RUN', className: 'status-run', valueKey: 'runLots' },
  { key: 'queue', label: 'QUEUE', className: 'status-queue', valueKey: 'queueLots' },
  { key: 'quality-hold', label: '品質異常', className: 'status-quality-hold', valueKey: 'qualityHoldLots' },
  { key: 'non-quality-hold', label: '非品質異常', className: 'status-non-quality-hold', valueKey: 'nonQualityHoldLots' },
];

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="summary-row detail-summary-row" :class="{ filtering: activeStatus }">
    <article class="summary-card">
      <div class="summary-label">Total Lots</div>
      <div class="summary-value">{{ formatNumber(summary?.totalLots) }}</div>
    </article>

    <article
      v-for="card in cards"
      :key="card.key"
      class="summary-card"
      :class="[card.className, { active: activeStatus === card.key }]"
      @click="emit('toggle', card.key)"
    >
      <div class="summary-label">{{ card.label }}</div>
      <div class="summary-value">{{ formatNumber(summary?.[card.valueKey]) }}</div>
    </article>
  </section>
</template>
