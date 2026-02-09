<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  summary: {
    type: Object,
    default: null,
  },
});

const lotsUpdated = ref(false);
const qtyUpdated = ref(false);

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

watch(
  () => props.summary?.totalLots,
  () => {
    lotsUpdated.value = true;
    setTimeout(() => {
      lotsUpdated.value = false;
    }, 500);
  }
);

watch(
  () => props.summary?.totalQtyPcs,
  () => {
    qtyUpdated.value = true;
    setTimeout(() => {
      qtyUpdated.value = false;
    }, 500);
  }
);
</script>

<template>
  <section class="summary-row overview-summary-row">
    <article class="summary-card">
      <div class="summary-label">Total Lots</div>
      <div class="summary-value" :class="{ updated: lotsUpdated }">
        {{ formatNumber(summary?.totalLots) }}
      </div>
    </article>
    <article class="summary-card">
      <div class="summary-label">Total QTY</div>
      <div class="summary-value" :class="{ updated: qtyUpdated }">
        {{ formatNumber(summary?.totalQtyPcs) }}
      </div>
    </article>
  </section>
</template>
