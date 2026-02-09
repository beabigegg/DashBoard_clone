<script setup>
import { computed } from 'vue';

import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  trend: {
    type: Array,
    default: () => [],
  },
});

const hasData = computed(() => props.trend.length > 0);

const chartOption = computed(() => {
  const trend = props.trend || [];

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
    },
    legend: {
      data: ['OU%', 'AVAIL%'],
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
      axisLabel: {
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: {
        formatter: '{value}%',
      },
    },
    series: [
      {
        name: 'OU%',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        areaStyle: { opacity: 0.2 },
        lineStyle: { width: 2 },
        itemStyle: { color: '#2563eb' },
        data: trend.map((item) => Number(item.ou_pct || 0)),
      },
      {
        name: 'AVAIL%',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        areaStyle: { opacity: 0.2 },
        lineStyle: { width: 2 },
        itemStyle: { color: '#16a34a' },
        data: trend.map((item) => Number(item.availability_pct || 0)),
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">OU% / AVAIL% 趨勢</h3>
    <div v-if="hasData" class="chart-body">
      <VChart :option="chartOption" autoresize />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>
