<script setup lang="ts">
import { computed } from 'vue';

import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

interface SeriesDef {
  name: string;
  key: string;
  color: string;
  yAxisIndex?: number;
}

interface SnapshotRow {
  ts?: string;
  [key: string]: unknown;
}

const props = defineProps<{
  title?: string;
  snapshots?: SnapshotRow[];
  series?: SeriesDef[];
  height?: string;
  yAxisLabel?: string;
  yMax?: number;
}>();

const hasData = computed(() => (props.snapshots?.length ?? 0) > 1);

function extractValue(row: SnapshotRow, key: string): unknown {
  return row[key] ?? null;
}

function formatTime(ts: string | undefined): string {
  if (!ts) return '';
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

const chartOption = computed(() => {
  const data = props.snapshots ?? [];
  const seriesDefs = props.series ?? [];

  const xLabels = data.map((row) => formatTime(row.ts));

  const echartsSeries = seriesDefs.map((s) => ({
    name: s.name,
    type: 'line',
    smooth: true,
    symbol: 'none',
    areaStyle: { opacity: 0.12 },
    lineStyle: { width: 2 },
    itemStyle: { color: s.color },
    yAxisIndex: s.yAxisIndex ?? 0,
    data: data.map((row) => extractValue(row, s.key)),
  }));

  const yAxisConfig: Record<string, unknown> = { type: 'value', min: 0 };
  if (props.yMax != null) yAxisConfig.max = props.yMax;
  if (props.yAxisLabel) {
    yAxisConfig.axisLabel = { formatter: `{value}${props.yAxisLabel}` };
  }

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: seriesDefs.map((s) => s.name),
      bottom: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 16,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisLabel: { fontSize: 10 },
    },
    yAxis: yAxisConfig,
    series: echartsSeries,
  };
});
</script>

<template>
  <div class="trend-chart-card">
    <h4 v-if="title" class="trend-chart-title">{{ title }}</h4>
    <div v-if="hasData" class="trend-chart-canvas" :style="{ height: height || '200px' }" role="img" :aria-label="title ? `${title} 趨勢圖` : '效能趨勢圖'">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="trend-chart-empty">
      <div class="trend-chart-empty__primary">趨勢資料不足（需至少 2 筆快照）</div>
      <div class="trend-chart-empty__hint">（每 30 秒自動收集一次）</div>
    </div>
  </div>
</template>
