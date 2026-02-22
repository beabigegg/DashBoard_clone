<script setup>
defineProps({
  cards: { type: Array, default: () => [] },
});

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}
</script>

<template>
  <section class="summary-row reject-summary-row">
    <article
      v-for="card in cards"
      :key="card.key"
      class="summary-card"
      :class="`lane-${card.lane}`"
    >
      <div class="summary-label">{{ card.label }}</div>
      <div class="summary-value small">{{ card.isPct ? formatPct(card.value) : formatNumber(card.value) }}</div>
    </article>
  </section>
</template>
