<script setup>
import { computed } from 'vue';

import {
  MATRIX_STATUS_COLUMNS,
  OU_BADGE_THRESHOLDS,
  STATUS_DISPLAY_MAP,
} from '../../resource-shared/constants.js';

const props = defineProps({
  summary: {
    type: Object,
    default: () => ({
      totalCount: 0,
      byStatus: {},
      ouPct: 0,
      availabilityPct: 0,
    }),
  },
  activeStatus: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle-status']);

const totalForPct = computed(() => {
  return MATRIX_STATUS_COLUMNS.reduce((total, status) => total + Number(props.summary.byStatus?.[status] || 0), 0);
});

function formatPct(count) {
  if (!totalForPct.value) {
    return '--';
  }
  return `${((Number(count || 0) / totalForPct.value) * 100).toFixed(1)}%`;
}

function resolveOuClass(value) {
  const pct = Number(value || 0);
  if (pct >= OU_BADGE_THRESHOLDS.high) {
    return 'high';
  }
  if (pct >= OU_BADGE_THRESHOLDS.medium) {
    return 'medium';
  }
  return 'low';
}

const cards = computed(() => {
  const byStatus = props.summary.byStatus || {};

  return [
    {
      key: 'OU',
      label: 'OU%',
      value: `${Number(props.summary.ouPct || 0).toFixed(1)}%`,
      className: 'ou',
      sub: '稼動率',
      clickable: false,
      badgeClass: resolveOuClass(props.summary.ouPct),
    },
    {
      key: 'AVAIL',
      label: 'AVAIL%',
      value: `${Number(props.summary.availabilityPct || 0).toFixed(1)}%`,
      className: 'availability',
      sub: '可用率',
      clickable: false,
      badgeClass: resolveOuClass(props.summary.availabilityPct),
    },
    ...MATRIX_STATUS_COLUMNS.map((status) => ({
      key: status,
      label: status,
      value: Number(byStatus[status] || 0),
      className: status.toLowerCase(),
      sub: `${STATUS_DISPLAY_MAP[status] || status} (${formatPct(byStatus[status])})`,
      clickable: true,
    })),
    {
      key: 'TOTAL',
      label: 'Total',
      value: Number(props.summary.totalCount || 0),
      className: 'total',
      sub: '設備總數',
      clickable: false,
    },
  ];
});

function handleCardClick(card) {
  if (!card.clickable) {
    return;
  }
  emit('toggle-status', card.key);
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="summary-grid">
        <article
          v-for="card in cards"
          :key="card.key"
          class="summary-card"
          :class="[
            card.className,
            { clickable: card.clickable, active: card.clickable && activeStatus === card.key },
          ]"
          @click="handleCardClick(card)"
        >
          <div class="summary-label">{{ card.label }}</div>
          <div class="summary-value" :class="card.className">
            <span v-if="card.badgeClass" class="ou-badge" :class="card.badgeClass">{{ card.value }}</span>
            <template v-else>{{ card.value }}</template>
          </div>
          <div class="summary-sub">{{ card.sub }}</div>
        </article>
      </div>
    </div>
  </section>
</template>
