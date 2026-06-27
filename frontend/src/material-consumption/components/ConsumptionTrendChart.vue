<script setup lang="ts">
/**
 * ConsumptionTrendChart — echarts LineChart
 * Change: material-part-consumption
 *
 * AC-2: one line series per material_part; hard cap 20 series
 * Design: no area fills (avoids overlap clutter); diverse color palette.
 */
import { computed } from 'vue';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent]);

// --- Constants ---
const MAX_SERIES = 20;

// Visually distinct palette — no consecutive same-family colors
const SERIES_COLORS = [
  '#0080C8', // brand blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // purple
  '#06b6d4', // cyan
  '#f97316', // orange
  '#ec4899', // pink
  '#84cc16', // lime
  '#6366f1', // indigo
  '#10b981', // emerald
  '#dc2626', // crimson
  '#7c3aed', // violet
  '#0891b2', // sky
  '#ca8a04', // dark amber
  '#059669', // dark green
  '#db2777', // deep pink
  '#2563eb', // royal blue
  '#65a30d', // olive
  '#9333ea', // grape
];

// --- Types ---
export interface TrendItem {
  period: string;
  material_part: string;
  total_consumed: number;
}

export interface PartOption {
  name: string;
  description?: string | null;
}

// --- Props ---
const props = withDefaults(
  defineProps<{
    trend?: TrendItem[];
    loading?: boolean;
    partOptions?: PartOption[];
  }>(),
  {
    trend: () => [],
    loading: false,
    partOptions: () => [],
  }
);

const partLabelMap = computed(() => {
  const map = new Map<string, string>();
  for (const p of props.partOptions) {
    map.set(p.name, p.description ? `${p.name} — ${p.description}` : p.name);
  }
  return map;
});

function partLabel(name: string): string {
  return partLabelMap.value.get(name) ?? name;
}

// --- Computed: pivot trend data into echarts series ---
const chartOption = computed(() => {
  const items = props.trend ?? [];

  const periodsSet = new Set<string>();
  const partMap = new Map<string, Map<string, number>>();

  for (const item of items) {
    if (!item.period || !item.material_part) continue;
    periodsSet.add(item.period);
    if (!partMap.has(item.material_part)) {
      partMap.set(item.material_part, new Map());
    }
    partMap.get(item.material_part)!.set(item.period, item.total_consumed);
  }

  const periods = [...periodsSet].sort();
  const allParts = [...partMap.keys()];

  // Sort parts by total consumption descending (most consumed first)
  allParts.sort((a, b) => {
    const sumA = [...(partMap.get(a)?.values() ?? [])].reduce((s, v) => s + v, 0);
    const sumB = [...(partMap.get(b)?.values() ?? [])].reduce((s, v) => s + v, 0);
    return sumB - sumA;
  });

  const cappedParts = allParts.slice(0, MAX_SERIES);
  const dense = periods.length > 24;

  const series = cappedParts.map((part, idx) => {
    const color = SERIES_COLORS[idx % SERIES_COLORS.length];
    return {
      name: partLabel(part),
      type: 'line',
      smooth: 0.3,
      symbol: 'circle',
      symbolSize: dense ? 4 : 8,
      showSymbol: !dense,
      lineStyle: { width: 2.5, color },
      itemStyle: { color, borderColor: '#fff', borderWidth: 2.5 },
      emphasis: {
        focus: 'series',
        scale: true,
        lineStyle: { width: 3.5 },
        itemStyle: { symbolSize: 11, shadowBlur: 8, shadowColor: `${color}66` },
      },
      // No areaStyle — avoids color bleeding between many series
      data: periods.map((p) => partMap.get(part)?.get(p) ?? 0),
    };
  });

  const legendLabels = cappedParts.map(partLabel);

  return {
    animation: true,
    animationDuration: 800,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 400,
    color: SERIES_COLORS,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'line',
        lineStyle: { color: 'rgba(100,116,139,0.3)', width: 1.5, type: 'dashed' },
      },
      backgroundColor: 'rgba(255,255,255,0.98)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: [10, 14],
      extraCssText: 'box-shadow:0 4px 20px rgba(0,0,0,0.1);border-radius:8px;min-width:160px;',
      textStyle: { fontSize: 12, color: '#374151' },
      formatter(params: unknown) {
        const pts = params as Array<{ seriesName: string; value: number; marker: string }>;
        const period = (params as Array<{ axisValue: string }>)[0]?.axisValue ?? '';
        const lines = pts
          .filter(p => p.value > 0)
          .sort((a, b) => b.value - a.value)
          .map(p => `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:2px">${p.marker}<span style="color:#6b7280">${p.seriesName}</span><b>${Number(p.value).toLocaleString('zh-TW')}</b></div>`);
        return `<div style="font-weight:600;color:#1f2937;margin-bottom:6px;font-size:12px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">${period}</div>${lines.join('')}`;
      },
    },
    legend: {
      data: legendLabels,
      bottom: 0,
      type: 'scroll',
      textStyle: { fontSize: 11, color: '#6b7280' },
      itemWidth: 14,
      itemHeight: 3,
      pageTextStyle: { color: '#6b7280', fontSize: 11 },
    },
    grid: { left: 60, right: 24, top: 24, bottom: 72, containLabel: false },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: {
        rotate: periods.length > 10 ? 35 : 0,
        fontSize: 11,
        color: '#9ca3af',
        margin: 10,
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
      axisLabel: {
        fontSize: 11,
        color: '#9ca3af',
        formatter(value: unknown) {
          const n = Number(value || 0);
          if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
          if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
          return n.toLocaleString('zh-TW');
        },
      },
    },
    series,
  };
});

const hasData = computed(() => (props.trend ?? []).length > 0);
</script>

<template>
  <div class="trend-chart-container">
    <div class="chart-toolbar">
      <span class="chart-title">消耗趨勢</span>
    </div>
    <BlockLoadingState v-if="loading" />
    <div v-else-if="!hasData" class="chart-empty">
      <span>無資料</span>
    </div>
    <div v-else class="vchart-trend">
      <VChart :option="chartOption" :autoresize="true" />
    </div>
  </div>
</template>
