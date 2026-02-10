<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent]);

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  data: {
    type: Array,
    default: () => [],
  },
});

const chartOption = computed(() => {
  if (!props.data || !props.data.length) return null;

  const names = props.data.map((d) => d.name);
  const defectQty = props.data.map((d) => d.defect_qty);
  const cumulativePct = props.data.map((d) => d.cumulative_pct);
  const defectRate = props.data.map((d) => d.defect_rate);

  return {
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const idx = params[0]?.dataIndex;
        if (idx == null) return '';
        const item = props.data[idx];
        let html = `<b>${item.name}</b><br/>`;
        html += `不良數: ${(item.defect_qty || 0).toLocaleString()}<br/>`;
        html += `投入數: ${(item.input_qty || 0).toLocaleString()}<br/>`;
        html += `不良率: ${(item.defect_rate || 0).toFixed(2)}%<br/>`;
        html += `累計占比: ${(item.cumulative_pct || 0).toFixed(1)}%`;
        return html;
      },
    },
    legend: {
      data: ['不良數', '不良率', '累計占比'],
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      top: 40,
      right: 60,
      bottom: 50,
      left: 50,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        rotate: names.length > 6 ? 30 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 80,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '不良數',
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11 },
      },
      {
        type: 'value',
        name: '%',
        max: 100,
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11, formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: '不良數',
        type: 'bar',
        data: defectQty,
        itemStyle: { color: '#6366f1', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 40,
      },
      {
        name: '不良率',
        type: 'line',
        yAxisIndex: 1,
        data: defectRate,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#f59e0b', width: 2 },
        itemStyle: { color: '#f59e0b' },
      },
      {
        name: '累計占比',
        type: 'line',
        yAxisIndex: 1,
        data: cumulativePct,
        symbol: 'diamond',
        symbolSize: 6,
        lineStyle: { color: '#ef4444', width: 2, type: 'dashed' },
        itemStyle: { color: '#ef4444' },
      },
    ],
  };
});
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-title">{{ title }}</h3>
    <VChart
      v-if="chartOption"
      class="chart-canvas"
      :option="chartOption"
      autoresize
    />
    <div v-else class="chart-empty">暫無資料</div>
  </div>
</template>
