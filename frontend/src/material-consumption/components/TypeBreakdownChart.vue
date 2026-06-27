<script setup lang="ts">
/**
 * TypeBreakdownChart — echarts BarChart (100% stacked by material_part)
 * Change: material-part-consumption
 *
 * AC-4: 100% stacked percentage bar per material_part, X=period
 * Design: parts sorted by total desc (largest at bottom); parts that
 * average < MIN_PCT_THRESHOLD across all periods are merged into "其他"
 * to avoid invisible slivers.
 */
import { computed } from 'vue';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

// Same distinct palette as trend chart for visual consistency
const SERIES_COLORS = [
  '#0080C8', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#ec4899', '#84cc16', '#6366f1',
  '#10b981', '#dc2626', '#7c3aed', '#0891b2', '#ca8a04',
  '#059669', '#db2777', '#2563eb', '#65a30d', '#9333ea',
];
const OTHER_COLOR = '#94a3b8'; // slate for "其他"

// Parts whose average share across periods is below this threshold
// are merged into "其他" to avoid invisible sliver bars
const MIN_PCT_THRESHOLD = 2; // percent

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

const chartOption = computed(() => {
  const items = props.trend ?? [];

  const periodsSet = new Set<string>();
  const partMap = new Map<string, Map<string, number>>();

  for (const item of items) {
    if (!item.period || !item.material_part) continue;
    periodsSet.add(item.period);
    if (!partMap.has(item.material_part)) partMap.set(item.material_part, new Map());
    partMap.get(item.material_part)!.set(item.period, item.total_consumed);
  }

  const periods = [...periodsSet].sort();

  // Period totals for percentage calculation
  const periodTotals = new Map<string, number>();
  for (const period of periods) {
    let total = 0;
    for (const [, pMap] of partMap) total += pMap.get(period) ?? 0;
    periodTotals.set(period, total);
  }

  // Sort all parts by grand total (descending) — biggest parts at the bottom
  const allParts = [...partMap.keys()].sort((a, b) => {
    const sumA = [...(partMap.get(a)?.values() ?? [])].reduce((s, v) => s + v, 0);
    const sumB = [...(partMap.get(b)?.values() ?? [])].reduce((s, v) => s + v, 0);
    return sumB - sumA;
  });

  // Compute average % per part across all periods
  const avgPct = new Map<string, number>();
  for (const part of allParts) {
    const pcts = periods.map(p => {
      const total = periodTotals.get(p) ?? 0;
      const val = partMap.get(part)?.get(p) ?? 0;
      return total > 0 ? (val / total) * 100 : 0;
    });
    avgPct.set(part, pcts.reduce((s, v) => s + v, 0) / (pcts.length || 1));
  }

  // Separate "visible" parts (avg >= threshold) from "other"
  const visibleParts = allParts.filter(p => (avgPct.get(p) ?? 0) >= MIN_PCT_THRESHOLD);
  const otherParts   = allParts.filter(p => (avgPct.get(p) ?? 0) <  MIN_PCT_THRESHOLD);

  // Build series — visible parts first (bottom to top in stack), then "其他" on top
  const series = visibleParts.map((part, idx) => {
    const color = SERIES_COLORS[idx % SERIES_COLORS.length];
    return {
      name: partLabel(part),
      type: 'bar',
      stack: 'total',
      barMaxWidth: 64,
      itemStyle: { color, borderRadius: [0, 0, 0, 0] },
      emphasis: {
        focus: 'series',
        itemStyle: { shadowBlur: 6, shadowColor: `${color}55` },
      },
      data: periods.map(p => {
        const total = periodTotals.get(p) ?? 0;
        const val = partMap.get(part)?.get(p) ?? 0;
        return total > 0 ? Math.round((val / total) * 1000) / 10 : 0;
      }),
    };
  });

  // Merge all "other" parts into a single "其他" series
  if (otherParts.length > 0) {
    const otherData = periods.map(p => {
      const total = periodTotals.get(p) ?? 0;
      const val = otherParts.reduce((s, part) => s + (partMap.get(part)?.get(p) ?? 0), 0);
      return total > 0 ? Math.round((val / total) * 1000) / 10 : 0;
    });
    series.push({
      name: `其他 (${otherParts.length}項)`,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 64,
      itemStyle: { color: OTHER_COLOR, borderRadius: [3, 3, 0, 0] },
      emphasis: {
        focus: 'series',
        itemStyle: { shadowBlur: 6, shadowColor: `${OTHER_COLOR}55` },
      },
      data: otherData,
    });
  } else if (series.length > 0) {
    // Round top corners on the last visible series
    const last = series[series.length - 1];
    last.itemStyle = { ...last.itemStyle, borderRadius: [3, 3, 0, 0] };
  }

  const legendLabels = [
    ...visibleParts.map(partLabel),
    ...(otherParts.length > 0 ? [`其他 (${otherParts.length}項)`] : []),
  ];

  return {
    animation: true,
    animationDuration: 800,
    animationEasing: 'cubicOut',
    color: SERIES_COLORS,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
        shadowStyle: { color: 'rgba(0,128,200,0.04)' },
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
          .map(p => `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:2px">${p.marker}<span style="color:#6b7280">${p.seriesName}</span><b>${p.value}%</b></div>`);
        return `<div style="font-weight:600;color:#1f2937;margin-bottom:6px;font-size:12px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">${period}</div>${lines.join('')}`;
      },
    },
    legend: {
      data: legendLabels,
      bottom: 0,
      type: 'scroll',
      textStyle: { fontSize: 11, color: '#6b7280' },
      itemWidth: 12,
      itemHeight: 12,
      pageTextStyle: { color: '#6b7280', fontSize: 11 },
    },
    grid: { left: 48, right: 24, top: 24, bottom: 72, containLabel: false },
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
      max: 100,
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
      axisLabel: {
        fontSize: 11,
        color: '#9ca3af',
        formatter: (v: unknown) => `${v}%`,
      },
    },
    series,
  };
});

const hasData = computed(() => (props.trend ?? []).length > 0);
</script>

<template>
  <div class="type-breakdown-chart-container">
    <div class="chart-toolbar">
      <span class="chart-title">料號消耗佔比</span>
    </div>
    <BlockLoadingState v-if="loading" />
    <div v-else-if="!hasData" class="chart-empty">
      <span>無資料</span>
    </div>
    <div v-else class="vchart-breakdown">
      <VChart :option="chartOption" :autoresize="true" />
    </div>
  </div>
</template>
