<script setup>
const props = defineProps({
  summary: {
    type: Object,
    default: () => ({
      releaseQty: 0,
      newHoldQty: 0,
      futureHoldQty: 0,
      stillOnHoldCount: 0,
      newHoldSnapshotCount: 0,
      netChange: 0,
      avgHoldHours: 0,
    }),
  },
});

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}

function formatHours(value) {
  return `${Number(value || 0).toFixed(1)} hr`;
}
</script>

<template>
  <section class="summary-row hold-history-summary-row">
    <article class="summary-card stat-negative-red">
      <div class="summary-label">On Hold 數量</div>
      <div class="summary-value">{{ formatNumber(summary.stillOnHoldCount) }}</div>
    </article>

    <article class="summary-card stat-negative-orange">
      <div class="summary-label">最末日新增 Hold</div>
      <div class="summary-value">{{ formatNumber(summary.newHoldSnapshotCount) }}</div>
    </article>

    <article class="summary-card stat-negative-red">
      <div class="summary-label">累計新增 Hold</div>
      <div class="summary-value">{{ formatNumber(summary.newHoldQty) }}</div>
    </article>

    <article class="summary-card stat-positive">
      <div class="summary-label">累計 Release</div>
      <div class="summary-value">{{ formatNumber(summary.releaseQty) }}</div>
    </article>

    <article class="summary-card stat-negative-orange">
      <div class="summary-label">累計 Future Hold</div>
      <div class="summary-value">{{ formatNumber(summary.futureHoldQty) }}</div>
    </article>

    <article class="summary-card">
      <div class="summary-label">累計淨變動 (Release - New - Future)</div>
      <div class="summary-value" :class="{ positive: summary.netChange >= 0, negative: summary.netChange < 0 }">
        {{ formatNumber(summary.netChange) }}
      </div>
    </article>

    <article class="summary-card">
      <div class="summary-label">平均 Hold 時長</div>
      <div class="summary-value">{{ formatHours(summary.avgHoldHours) }}</div>
    </article>
  </section>
</template>
