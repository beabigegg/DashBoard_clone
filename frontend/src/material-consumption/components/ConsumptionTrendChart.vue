<script setup lang="ts">
/**
 * ConsumptionTrendChart — echarts LineChart
 * Change: material-part-consumption
 *
 * AC-2: one line series per material_part; hard cap 20 series
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

// --- Computed: pivot trend data into echarts series ---
const chartOption = computed(() => {
  const items = props.trend ?? [];

  // Collect unique periods (x-axis)
  const periodsSet = new Set<string>();
  const partMap = new Map<string, Map<string, number>>();

  for (const item of items) {
    if (!item.period || !item.material_part) continue; // guard: echarts crashes on null axis/series name
    periodsSet.add(item.period);
    if (!partMap.has(item.material_part)) {
      partMap.set(item.material_part, new Map());
    }
    partMap.get(item.material_part)!.set(item.period, item.total_consumed);
  }

  const periods = [...periodsSet].sort();

  // Collect all parts, cap at MAX_SERIES (AC-2)
  const allParts = [...partMap.keys()];
  const cappedParts = allParts.slice(0, MAX_SERIES);

  const series = cappedParts.map((part) => ({
    name: partLabel(part),
    type: 'line',
    smooth: true,
    data: periods.map((p) => partMap.get(part)?.get(p) ?? 0),
  }));

  const legendLabels = cappedParts.map(partLabel);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        // TODO: type echarts callback
        const items = params as Array<{ seriesName: string; value: number; marker: string }>;
        const period = (params as Array<{ axisValue: string }>)[0]?.axisValue ?? '';
        const lines = items.map(
          (p) => `${p.marker}${p.seriesName}: ${Number(p.value).toLocaleString('zh-TW')}`
        );
        return `<strong>${period}</strong><br>${lines.join('<br>')}`;
      },
    },
    legend: {
      data: legendLabels,
      bottom: 0,
      type: 'scroll',
    },
    grid: { left: 56, right: 24, top: 22, bottom: 72, containLabel: false },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: { rotate: periods.length > 10 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        // TODO: type echarts callback
        formatter(value: unknown) {
          return Number(value || 0).toLocaleString('zh-TW');
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
      <span class="chart-title">消耗趨勢圖</span>
    </div>

    <!-- BLOCKING-3 fix: use contracted BlockLoadingState; handles prefers-reduced-motion -->
    <BlockLoadingState v-if="loading" />
    <div v-else-if="!hasData" class="chart-empty">
      <span>無資料</span>
    </div>
    <div v-else class="vchart-trend">
      <VChart
        :option="chartOption"
        :autoresize="true"
      />
    </div>
  </div>
</template>
