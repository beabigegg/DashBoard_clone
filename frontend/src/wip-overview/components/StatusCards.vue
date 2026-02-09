<script setup>
const props = defineProps({
  summary: {
    type: Object,
    default: () => ({}),
  },
  activeStatus: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

const cards = [
  { key: 'run', label: 'RUN', className: 'run' },
  { key: 'queue', label: 'QUEUE', className: 'queue' },
  { key: 'quality-hold', label: '品質異常', className: 'quality-hold' },
  { key: 'non-quality-hold', label: '非品質異常', className: 'non-quality-hold' },
];

function resolveData(key) {
  if (key === 'quality-hold') {
    return props.summary?.qualityHold || {};
  }
  if (key === 'non-quality-hold') {
    return props.summary?.nonQualityHold || {};
  }
  return props.summary?.[key] || {};
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '-') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="wip-status-row" :class="{ filtering: activeStatus }">
    <article
      v-for="card in cards"
      :key="card.key"
      class="wip-status-card"
      :class="[card.className, { active: activeStatus === card.key }]"
      @click="emit('toggle', card.key)"
    >
      <div class="status-header">
        <span class="dot"></span>
        {{ card.label }}
      </div>
      <div class="status-values">
        <span>{{ formatNumber(resolveData(card.key).lots) }}</span>
        <span>{{ formatNumber(resolveData(card.key).qtyPcs) }}</span>
      </div>
    </article>
  </section>
</template>
