<script setup>
const props = defineProps({
  summary: {
    type: Object,
    default: null,
  },
});

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function formatAge(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  const num = Number(value);
  return `${Number.isFinite(num) ? num.toFixed(1) : value}天`;
}
</script>

<template>
  <section class="summary-row hold-summary-row">
    <article class="summary-card">
      <div class="summary-label">Total Lots</div>
      <div class="summary-value">{{ formatNumber(summary?.totalLots) }}</div>
    </article>
    <article class="summary-card">
      <div class="summary-label">Total QTY</div>
      <div class="summary-value">{{ formatNumber(summary?.totalQty) }}</div>
    </article>
    <article class="summary-card">
      <div class="summary-label">平均當站滯留</div>
      <div class="summary-value small">{{ formatAge(summary?.avgAge) }}</div>
    </article>
    <article class="summary-card">
      <div class="summary-label">最久當站滯留</div>
      <div class="summary-value small">{{ formatAge(summary?.maxAge) }}</div>
    </article>
    <article class="summary-card">
      <div class="summary-label">影響站群</div>
      <div class="summary-value">{{ formatNumber(summary?.workcenterCount) }}</div>
    </article>
  </section>
</template>
