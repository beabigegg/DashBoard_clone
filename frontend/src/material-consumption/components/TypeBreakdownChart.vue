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

// --- Types ---
export interface TrendItem {
  period: string;
  material_part: string;
  total_consumed: number;
}

// --- Props ---
const props = withDefaults(
  defineProps<{
    trend?: TrendItem[];
    loading?: boolean;
  }>(),
  {
    trend: () => [],
    loading: false,
  }
);

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

  const series = parts.map((part) => ({
    name: part,
    type: 'bar',
    stack: 'total',
    data: periods.map((p) => {
      const total = periodTotals.get(p) ?? 0;
      const val = partMap.get(part)?.get(p) ?? 0;
      return total > 0 ? Math.round((val / total) * 1000) / 10 : 0; // 1 decimal %
    }),
    emphasis: { focus: 'series' },
  }));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        // TODO: type echarts callback
        const items = params as Array<{ seriesName: string; value: number; marker: string }>;
        const period = (params as Array<{ axisValue: string }>)[0]?.axisValue ?? '';
        const lines = items.map((p) => `${p.marker}${p.seriesName}: ${p.value}%`);
        return `<strong>${period}</strong><br>${lines.join('<br>')}`;
      },
    },
    legend: { data: parts, bottom: 0, type: 'scroll' },
    grid: { left: 48, right: 24, top: 22, bottom: 72, containLabel: false },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: { rotate: periods.length > 10 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      max: 100,
      // TODO: type echarts callback
      axisLabel: { formatter: (v: unknown) => `${v}%` },
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
    <!-- BLOCKING-3 fix: use contracted BlockLoadingState; handles prefers-reduced-motion -->
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
