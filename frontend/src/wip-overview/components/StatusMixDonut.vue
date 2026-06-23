<script setup lang="ts">
import { computed } from 'vue';
import { PieChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, PieChart, TooltipComponent]);

const STATUS_CONFIG = [
  { key: 'run',            label: 'RUN',            color: '#22c55e' },
  { key: 'queue',          label: 'QUEUE',           color: '#3b82f6' },
  { key: 'qualityHold',    label: '品質異常 HOLD',   color: '#ef4444' },
  { key: 'nonQualityHold', label: '非品質異常 HOLD', color: '#f97316' },
] as const;

interface StatusEntry {
  lots?: number;
  qtyPcs?: number;
}

const props = defineProps<{
  data: Record<string, unknown>;
  mode: 'lots' | 'pcs';
}>();

const title = computed(() =>
  props.mode === 'lots' ? 'STATUS MIX · BY LOTS' : 'STATUS MIX · BY PCS',
);

const seriesData = computed(() =>
  STATUS_CONFIG.map((s) => {
    const entry = (props.data[s.key] as StatusEntry) || {};
    const value = Number(props.mode === 'lots' ? (entry.lots ?? 0) : (entry.qtyPcs ?? 0));
    return { name: s.label, value, itemStyle: { color: s.color } };
  }),
);

const total = computed(() =>
  seriesData.value.reduce((acc, item) => acc + item.value, 0),
);

const totalFormatted = computed(() => {
  const n = total.value;
  if (!n) return '—';
  if (props.mode === 'pcs') {
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}KK`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  }
  return n.toLocaleString('zh-TW');
});

const legendItems = computed(() =>
  STATUS_CONFIG.map((s) => {
    const entry = (props.data[s.key] as StatusEntry) || {};
    const value = Number(props.mode === 'lots' ? (entry.lots ?? 0) : (entry.qtyPcs ?? 0));
    const pct = total.value > 0 ? Math.round((value / total.value) * 100) : 0;
    return { key: s.key, label: s.label, color: s.color, pct };
  }),
);

const chartOption = computed(() => ({
  series: [
    {
      type: 'pie' as const,
      radius: ['50%', '78%'],
      center: ['50%', '50%'],
      data: seriesData.value,
      emphasis: {
        itemStyle: {
          shadowBlur: 14,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.25)',
        },
        scale: true,
        scaleSize: 3,
      },
      label: { show: false },
      labelLine: { show: false },
      animationType: 'expansion' as const,
      animationDuration: 700,
      animationEasing: 'cubicOut' as const,
    },
  ],
}));
</script>

<template>
  <div class="status-mix-donut">
    <div class="status-mix-donut__label">{{ title }}</div>
    <div class="status-mix-donut__body">
      <div class="status-mix-donut__chart-wrap">
        <v-chart class="status-mix-donut__vchart" :option="chartOption" autoresize />
        <div class="status-mix-donut__center" aria-hidden="true">
          <span class="status-mix-donut__center-num">{{ totalFormatted }}</span>
          <span class="status-mix-donut__center-unit">{{ mode === 'lots' ? 'LOTS' : 'PCS' }}</span>
        </div>
      </div>
      <ul class="status-mix-donut__legend" role="list">
        <li
          v-for="item in legendItems"
          :key="item.key"
          class="status-mix-donut__legend-item"
        >
          <span class="status-mix-donut__dot" :style="{ background: item.color }" />
          <span class="status-mix-donut__legend-name">{{ item.label }}</span>
          <span class="status-mix-donut__legend-pct">{{ item.pct }}%</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.status-mix-donut {
  position: relative;
  background: var(--card-bg);
  border-radius: 10px;
  box-shadow: var(--shadow);
  border: 1px solid var(--border);
  padding: 14px 16px 12px;
  overflow: hidden;
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

/* top accent bar */
.status-mix-donut::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: theme('colors.brand.500');
}

/* card-level glow on hover */
.status-mix-donut:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 1px rgba(0, 128, 200, 0.2),
    0 0 24px rgba(0, 128, 200, 0.25),
    0 8px 24px rgba(0, 0, 0, 0.1);
}

/* radial ambient glow behind chart */
.status-mix-donut::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: radial-gradient(
    circle at 30% 60%,
    rgba(0, 128, 200, 0.06) 0%,
    transparent 65%
  );
  opacity: 0;
  transition: opacity 0.25s ease;
}

.status-mix-donut:hover::after {
  opacity: 1;
}

.status-mix-donut__label {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-mix-donut__body {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── donut chart ───────────────────────────────────────────────────────── */

.status-mix-donut__chart-wrap {
  position: relative;
  flex: 0 0 120px;
  height: 120px;
}

.status-mix-donut__vchart {
  width: 100%;
  height: 100%;
}

.status-mix-donut__center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  gap: 2px;
}

.status-mix-donut__center-num {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.status-mix-donut__center-unit {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.05em;
}

/* ── legend ────────────────────────────────────────────────────────────── */

.status-mix-donut__legend {
  flex: 1 1 0;
  min-width: 0;
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-mix-donut__legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  overflow: hidden;
}

.status-mix-donut__dot {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-mix-donut__legend-name {
  flex: 1 1 0;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
}

.status-mix-donut__legend-pct {
  flex: 0 0 auto;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

/* ── reduced motion ────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .status-mix-donut,
  .status-mix-donut::after {
    transition: none;
  }

  .status-mix-donut:hover {
    transform: none;
  }
}
</style>
