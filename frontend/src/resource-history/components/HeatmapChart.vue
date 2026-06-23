<script setup lang="ts">
import { computed, ref } from 'vue';

import { HeatmapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent]);

interface MetricOption {
  value: string;
  label: string;
}

const props = withDefaults(defineProps<{
  heatmap?: Record<string, unknown>[];
}>(), {
  heatmap: () => [],
});

const metricOptions: MetricOption[] = [
  { value: 'ou_pct', label: 'OU%' },
  { value: 'oee_pct', label: 'OEE%' },
  { value: 'availability_pct', label: 'AVAIL%' },
];
const selectedMetric = ref<string>('ou_pct');

const metricLabel = computed(() => {
  const opt = metricOptions.find((o) => o.value === selectedMetric.value);
  return opt ? opt.label : 'OU%';
});

const hasData = computed(() => props.heatmap.length > 0);

const parsedHeatmap = computed(() => {
  const rows = props.heatmap || [];
  const metric = selectedMetric.value;

  const seqByWorkcenter: Record<string, number> = {};
  rows.forEach((row) => {
    seqByWorkcenter[String(row.workcenter)] = Number(row.workcenter_seq ?? 999);
  });

  const workcenters = [...new Set(rows.map((row) => String(row.workcenter)))].sort(
    (left, right) => Number(seqByWorkcenter[left] ?? 999) - Number(seqByWorkcenter[right] ?? 999)
  );
  const dates = [...new Set(rows.map((row) => String(row.date)))].sort();

  const matrixData = rows.map((row) => [
    dates.indexOf(String(row.date)),
    workcenters.indexOf(String(row.workcenter)),
    Number(row[metric] || 0),
  ]);

  return {
    dates,
    workcenters,
    matrixData,
  };
});

const ROW_HEIGHT = 36;
const GRID_OVERHEAD = 120; // top:20 + bottom:100 (visualMap legend)

const chartBodyHeight = computed(() => {
  const rows = parsedHeatmap.value.workcenters.length;
  return Math.min(Math.max(280, rows * ROW_HEIGHT + GRID_OVERHEAD), 900);
});

const chartOption = computed(() => {
  const payload = parsedHeatmap.value;
  const showCellLabel = payload.dates.length <= 30;

  return {
    tooltip: {
      position: 'top',
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as { value?: unknown[] };
        const xIndex = Number(p.value?.[0] || 0);
        const yIndex = Number(p.value?.[1] || 0);
        const value = Number(p.value?.[2] || 0);

        return `${payload.workcenters[yIndex] || '--'}<br/>${payload.dates[xIndex] || '--'}<br/>${metricLabel.value}: <b>${value.toFixed(1)}%</b>`;
      },
    },
    grid: {
      left: 130,
      right: 20,
      top: 20,
      bottom: 100,
    },
    xAxis: {
      type: 'category',
      data: payload.dates,
      splitArea: { show: true },
      axisLabel: {
        fontSize: 11,
        rotate: 40,
      },
    },
    yAxis: {
      type: 'category',
      data: payload.workcenters,
      inverse: true,
      splitArea: { show: true },
      axisLabel: {
        fontSize: 13,
        fontWeight: 500,
      },
    },
    visualMap: {
      min: 0,
      max: 100,
      orient: 'horizontal',
      left: 'center',
      bottom: 8,
      text: ['100%', '0%'],
      textStyle: { fontSize: 11, color: '#64748b' },
      itemWidth: 14,
      itemHeight: 120,
      calculable: true,
      inRange: {
        color: ['#ef4444', '#f97316', '#eab308', '#22c55e'],
      },
    },
    series: [
      {
        type: 'heatmap',
        data: payload.matrixData,
        itemStyle: {
          borderColor: 'rgba(255,255,255,0.55)',
          borderWidth: 1,
        },
        label: {
          show: showCellLabel,
          fontSize: 11,
          fontWeight: 600,
          color: '#fff',
          textShadowBlur: 3,
          textShadowColor: 'rgba(0,0,0,0.55)',
          formatter: (params: unknown) => {
            const v = Number((params as { value?: unknown[] }).value?.[2] || 0);
            return v > 0 ? v.toFixed(1) : '';
          },
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 22,
            shadowColor: 'rgba(0,0,0,0.45)',
            borderColor: 'rgba(255,255,255,0.95)',
            borderWidth: 2,
          },
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <div class="chart-header">
      <h3 class="chart-title">Workcenter x Date {{ metricLabel }} 熱圖</h3>
      <select v-model="selectedMetric" class="heatmap-metric-select">
        <option v-for="opt in metricOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
    </div>
    <div v-if="hasData" class="chart-body" :style="{ height: chartBodyHeight + 'px' }" role="img" aria-label="設備稼動率熱力圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data" :style="{ height: chartBodyHeight + 'px' }">No data</div>
  </article>
</template>

<style scoped>
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 10px 12px;
  border-bottom: 1px solid #eef2f7;
}
.chart-header .chart-title {
  border-bottom: none;
  padding: 0;
  margin: 0;
}
.heatmap-metric-select {
  padding: 4px 10px;
  border: 1.5px solid #cbd5e1;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  background: #f8fafc;
  color: #334155;
  cursor: pointer;
  transition: border-color 0.15s;
}
.heatmap-metric-select:hover {
  border-color: #93c5fd;
}
.heatmap-metric-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.18);
}
</style>
