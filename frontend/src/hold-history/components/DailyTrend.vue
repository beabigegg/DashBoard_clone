<script setup>
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent]);

const props = defineProps({
  days: {
    type: Array,
    default: () => [],
  },
});

const hasData = computed(() => (props.days || []).length > 0);

const chartOption = computed(() => {
  const days = props.days || [];
  const dates = days.map((item) => item.date);
  const release = days.map((item) => Number(item.releaseQty || 0));
  const newHold = days.map((item) => -Math.abs(Number(item.newHoldQty || 0)));
  const futureHold = days.map((item) => -Math.abs(Number(item.futureHoldQty || 0)));
  const stock = days.map((item) => Number(item.holdQty || 0));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const index = Number(params?.[0]?.dataIndex || 0);
        const row = days[index] || {};
        const parts = [
          `<b>${row.date || '--'}</b>`,
          `Release: ${Number(row.releaseQty || 0).toLocaleString('zh-TW')}`,
          `New Hold: ${Number(row.newHoldQty || 0).toLocaleString('zh-TW')}`,
          `Future Hold: ${Number(row.futureHoldQty || 0).toLocaleString('zh-TW')}`,
          `On Hold: ${Number(row.holdQty || 0).toLocaleString('zh-TW')}`,
        ];
        return parts.join('<br/>');
      },
    },
    legend: {
      data: ['Release', 'New Hold', 'Future Hold', 'On Hold'],
      bottom: 0,
    },
    grid: {
      left: 48,
      right: 58,
      top: 30,
      bottom: 52,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        interval: Math.max(Math.floor(dates.length / 12), 0),
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '增減量',
        axisLabel: {
          formatter: (value) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
      {
        type: 'value',
        name: 'On Hold',
        axisLabel: {
          formatter: (value) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
    ],
    series: [
      {
        name: 'Release',
        type: 'bar',
        data: release,
        itemStyle: { color: 'rgb(22, 163, 74)' },
        barMaxWidth: 18,
      },
      {
        name: 'New Hold',
        type: 'bar',
        stack: 'negative',
        data: newHold,
        itemStyle: { color: 'rgb(220, 38, 38)' },
        barMaxWidth: 18,
      },
      {
        name: 'Future Hold',
        type: 'bar',
        stack: 'negative',
        data: futureHold,
        itemStyle: { color: 'rgb(249, 115, 22)' },
        barMaxWidth: 18,
      },
      {
        name: 'On Hold',
        type: 'line',
        yAxisIndex: 1,
        data: stock,
        smooth: true,
        lineStyle: { width: 2, color: 'rgb(37, 99, 235)' },
        itemStyle: { color: 'rgb(37, 99, 235)' },
        symbolSize: 5,
      },
    ],
  };
});
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">Daily Trend</div>
    </div>
    <div class="card-body ui-card-body">
      <div v-if="hasData" class="trend-chart-wrap">
        <VChart :option="chartOption" autoresize />
      </div>
      <div v-else class="placeholder">No data</div>
    </div>
  </section>
</template>
