<script setup lang="ts">
/**
 * TypeBreakdownChart — echarts BarChart (100% stacked by material_part)
 * Change: material-part-consumption
 *
 * AC-4: 100% stacked percentage bar per material_part, X=period
 */
import { computed } from 'vue';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

// Brand-aligned series palette (same as trend chart for consistency)
const SERIES_COLORS = [
  '#0080C8', '#00A3E0', '#006BA8', '#2998d8', '#004A76',
  '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899',
  '#10b981', '#f97316', '#3b82f6', '#6366f1', '#eab308',
  '#14b8a6', '#a855f7', '#06b6d4', '#84cc16', '#f43f5e',
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

// Build label map: part name → "name — description" (fallback: just name)
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

// --- Computed: pivot by material_part, express as 100% stacked percentage ---
const chartOption = computed(() => {
  const items = props.trend ?? [];

  // Collect periods and build partMap
  const periodsSet = new Set<string>();
  const partMap = new Map<string, Map<string, number>>();

  for (const item of items) {
    if (!item.period || !item.material_part) continue;
    periodsSet.add(item.period);
    if (!partMap.has(item.material_part)) partMap.set(item.material_part, new Map());
    partMap.get(item.material_part)!.set(item.period, item.total_consumed);
  }

  const periods = [...periodsSet].sort();
  const parts = [...partMap.keys()];

  // Compute period totals for percentage calculation
  const periodTotals = new Map<string, number>();
  for (const period of periods) {
    let total = 0;
    for (const [, pMap] of partMap) total += pMap.get(period) ?? 0;
    periodTotals.set(period, total);
  }

  const series = parts.map((part, idx) => {
    const color = SERIES_COLORS[idx % SERIES_COLORS.length];
    return {
      name: partLabel(part),
      type: 'bar',
      stack: 'total',
      barMaxWidth: 60,
      itemStyle: {
        color,
        borderRadius: idx === parts.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0],
      },
      emphasis: {
        focus: 'series',
        itemStyle: { shadowBlur: 8, shadowColor: `${color}55` },
      },
      data: periods.map((p) => {
        const total = periodTotals.get(p) ?? 0;
        const val = partMap.get(part)?.get(p) ?? 0;
        return total > 0 ? Math.round((val / total) * 1000) / 10 : 0;
      }),
    };
  });

  const legendLabels = parts.map(partLabel);

  return {
    animation: true,
    animationDuration: 900,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 500,
    color: SERIES_COLORS,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
        shadowStyle: { color: 'rgba(0,128,200,0.04)' },
      },
      backgroundColor: 'rgba(255,255,255,0.97)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: [10, 14],
      extraCssText: 'box-shadow:0 4px 20px rgba(0,0,0,0.1);border-radius:8px;',
      textStyle: { fontSize: 12, color: '#374151' },
      formatter(params: unknown) {
        const items = params as Array<{ seriesName: string; value: number; marker: string }>;
        const period = (params as Array<{ axisValue: string }>)[0]?.axisValue ?? '';
        const lines = items
          .filter(p => p.value > 0)
          .sort((a, b) => b.value - a.value)
          .map(p => `${p.marker}<span style="color:#6b7280">${p.seriesName}</span>: <b>${p.value}%</b>`);
        return `<div style="font-weight:600;color:#1f2937;margin-bottom:6px;font-size:12px">${period}</div>${lines.join('<br>')}`;
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
        rotate: periods.length > 10 ? 30 : 0,
        fontSize: 11,
        color: '#9ca3af',
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { lineStyle: { color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'value',
      max: 100,
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
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
      <VChart
        :option="chartOption"
        :autoresize="true"
      />
    </div>
  </div>
</template>
