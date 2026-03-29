<script setup>
import { computed, ref } from 'vue';

import { HeatmapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  heatmap: {
    type: Array,
    default: () => [],
  },
});

const metricOptions = [
  { value: 'ou_pct', label: 'OU%' },
  { value: 'oee_pct', label: 'OEE%' },
  { value: 'availability_pct', label: 'AVAIL%' },
];
const selectedMetric = ref('ou_pct');

const metricLabel = computed(() => {
  const opt = metricOptions.find((o) => o.value === selectedMetric.value);
  return opt ? opt.label : 'OU%';
});

const hasData = computed(() => props.heatmap.length > 0);

const parsedHeatmap = computed(() => {
  const rows = props.heatmap || [];
  const metric = selectedMetric.value;

  const seqByWorkcenter = {};
  rows.forEach((row) => {
    seqByWorkcenter[row.workcenter] = Number(row.workcenter_seq ?? 999);
  });

  const workcenters = [...new Set(rows.map((row) => row.workcenter))].sort(
    (left, right) => Number(seqByWorkcenter[left] ?? 999) - Number(seqByWorkcenter[right] ?? 999)
  );
  const dates = [...new Set(rows.map((row) => row.date))].sort();

  const matrixData = rows.map((row) => [
    dates.indexOf(row.date),
    workcenters.indexOf(row.workcenter),
    Number(row[metric] || 0),
  ]);

  return {
    dates,
    workcenters,
    matrixData,
  };
});

const chartOption = computed(() => {
  const payload = parsedHeatmap.value;

  return {
    tooltip: {
      position: 'top',
      formatter(params) {
        const xIndex = Number(params.value?.[0] || 0);
        const yIndex = Number(params.value?.[1] || 0);
        const value = Number(params.value?.[2] || 0);

        return `${payload.workcenters[yIndex] || '--'}<br/>${payload.dates[xIndex] || '--'}<br/>${metricLabel.value}: <b>${value.toFixed(
          1
        )}%</b>`;
      },
    },
    grid: {
      left: 110,
      right: 20,
      top: 20,
      bottom: 100,
    },
    xAxis: {
      type: 'category',
      data: payload.dates,
      splitArea: { show: true },
      axisLabel: {
        fontSize: 10,
        rotate: 40,
      },
    },
    yAxis: {
      type: 'category',
      data: payload.workcenters,
      splitArea: { show: true },
      axisLabel: {
        fontSize: 10,
      },
    },
    visualMap: {
      min: 0,
      max: 100,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      inRange: {
        color: ['rgb(239, 68, 68)', 'rgb(245, 158, 11)', 'rgb(34, 197, 94)'],
      },
    },
    series: [
      {
        type: 'heatmap',
        data: payload.matrixData,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
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
    <div v-if="hasData" class="chart-body" role="img" aria-label="設備稼動率熱力圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>

<style scoped>
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.heatmap-metric-select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.25rem;
  font-size: 0.8125rem;
  background: var(--color-surface, #fff);
  color: var(--color-text, #1f2937);
}
</style>
