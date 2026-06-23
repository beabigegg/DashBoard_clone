<script setup lang="ts">
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

function resolveData(key: string): Record<string, unknown> {
  if (key === 'quality-hold') {
    return (props.summary as Record<string, unknown>)?.qualityHold as Record<string, unknown> || {};
  }
  if (key === 'non-quality-hold') {
    return (props.summary as Record<string, unknown>)?.nonQualityHold as Record<string, unknown> || {};
  }
  return (props.summary as Record<string, unknown>)?.[key] as Record<string, unknown> || {};
}

function formatNumber(value: unknown): string {
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
        <div class="status-val-grp">
          <span class="status-val-num">{{ formatNumber(resolveData(card.key).lots) }}</span>
          <span class="status-val-unit">lots</span>
        </div>
        <div class="status-val-grp">
          <span class="status-val-num">{{ formatNumber(resolveData(card.key).qtyPcs) }}</span>
          <span class="status-val-unit">pcs</span>
        </div>
      </div>
    </article>
  </section>
</template>
