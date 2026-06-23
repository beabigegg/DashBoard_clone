<script setup lang="ts">
import { computed } from 'vue';

import { EffectScatterChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, EffectScatterChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = withDefaults(defineProps<{
  trend?: Record<string, unknown>[];
}>(), {
  trend: () => [],
});

const hasData = computed(() => props.trend.length > 0);

const LINE_SERIES_CONFIG = [
  { name: 'OU%',    field: 'ou_pct',           color: 'rgb(37, 99, 235)',  areaOpacity: 0.2 },
  { name: 'OEE%',   field: 'oee_pct',          color: 'rgb(245, 158, 11)', areaOpacity: 0.1 },
  { name: 'AVAIL%', field: 'availability_pct', color: 'rgb(22, 163, 74)',  areaOpacity: 0.2 },
];

const chartOption = computed(() => {
  const trend = props.trend || [];
  const lastIndex = trend.length - 1;

  const lineSeries = LINE_SERIES_CONFIG.map(({ name, field, color, areaOpacity }) => ({
    name,
    type: 'line',
    smooth: true,
    symbolSize: 6,
    areaStyle: { opacity: areaOpacity },
    lineStyle: { width: 2 },
    itemStyle: { color },
    data: trend.map((item) => Number(item[field] || 0)),
  }));

  const pulseSeries = lastIndex >= 0
    ? LINE_SERIES_CONFIG.map(({ field, color }) => ({
        type: 'effectScatter',
        coordinateSystem: 'cartesian2d',
        showEffectOn: 'render',
        rippleEffect: { brushType: 'stroke', scale: 4, period: 2.5 },
        symbolSize: 8,
        itemStyle: { color },
        data: [[String(trend[lastIndex].date), Number(trend[lastIndex][field] || 0)]],
        silent: true,
        legendHoverLink: false,
        z: 10,
      }))
    : [];

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      formatter(params: unknown) {
        const list = (params as Array<Record<string, unknown>>).filter(
          (p) => p.seriesType !== 'effectScatter',
        );
        if (!list.length) return '';
        const dateLabel = String((list[0] as Record<string, unknown>).axisValueLabel || '');
        return [
          `<b>${dateLabel}</b>`,
          ...list.map((p) => `${p.marker}${p.seriesName}: <b>${Number(p.value || 0).toFixed(1)}%</b>`),
        ].join('<br/>');
      },
    },
    legend: {
      data: ['OU%', 'OEE%', 'AVAIL%'],
      bottom: 0,
    },
    grid: {
      left: 46,
      right: 20,
      top: 24,
      bottom: 50,
    },
    xAxis: {
      type: 'category',
      data: trend.map((item) => item.date),
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' },
    },
    series: [...lineSeries, ...pulseSeries],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">OU% / OEE% / AVAIL% 趨勢</h3>
    <div v-if="hasData" class="chart-body" role="img" aria-label="設備稼動率趨勢圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>
