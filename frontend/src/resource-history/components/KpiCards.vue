<script setup>
import { computed } from 'vue';

import { buildResourceKpiFromHours } from '../../core/compute.js';
import { OU_BADGE_THRESHOLDS } from '../../resource-shared/constants.js';

function resolveOuClass(value) {
  const pct = Number(value || 0);
  if (pct >= OU_BADGE_THRESHOLDS.high) return 'high';
  if (pct >= OU_BADGE_THRESHOLDS.medium) return 'medium';
  return 'low';
}

const props = defineProps({
  kpi: {
    type: Object,
    default: () => ({}),
  },
});

function formatHours(value) {
  const hours = Number(value || 0);
  if (hours >= 1000) {
    return `${(hours / 1000).toFixed(1)}K`;
  }
  return `${hours.toFixed(1)}h`;
}

const normalizedKpi = computed(() => {
  return {
    ...props.kpi,
    ...buildResourceKpiFromHours(props.kpi),
  };
});

const cards = computed(() => {
  const kpi = normalizedKpi.value;

  return [
    {
      key: 'ou',
      label: 'OU%',
      value: `${Number(kpi.ou_pct || 0).toFixed(1)}%`,
      className: 'ou',
      sub: '稼動率',
      badgeClass: resolveOuClass(kpi.ou_pct),
    },
    {
      key: 'availability',
      label: 'AVAIL%',
      value: `${Number(kpi.availability_pct || 0).toFixed(1)}%`,
      className: 'availability',
      sub: '可用率',
      badgeClass: resolveOuClass(kpi.availability_pct),
    },
    {
      key: 'prd',
      label: 'PRD',
      value: formatHours(kpi.prd_hours),
      className: 'prd',
      sub: `生產 (${Number(kpi.prd_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'sby',
      label: 'SBY',
      value: formatHours(kpi.sby_hours),
      className: 'sby',
      sub: `待機 (${Number(kpi.sby_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'udt',
      label: 'UDT',
      value: formatHours(kpi.udt_hours),
      className: 'udt',
      sub: `非計畫停機 (${Number(kpi.udt_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'sdt',
      label: 'SDT',
      value: formatHours(kpi.sdt_hours),
      className: 'sdt',
      sub: `計畫停機 (${Number(kpi.sdt_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'egt',
      label: 'EGT',
      value: formatHours(kpi.egt_hours),
      className: 'egt',
      sub: `工程 (${Number(kpi.egt_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'nst',
      label: 'NST',
      value: formatHours(kpi.nst_hours),
      className: 'nst',
      sub: `未排程 (${Number(kpi.nst_pct || 0).toFixed(1)}%)`,
    },
    {
      key: 'machine',
      label: '機台數',
      value: Number(kpi.machine_count || 0).toLocaleString('zh-TW'),
      className: 'total',
      sub: '設備總數',
    },
  ];
});
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="summary-grid">
        <article v-for="card in cards" :key="card.key" class="summary-card" :class="card.className">
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
