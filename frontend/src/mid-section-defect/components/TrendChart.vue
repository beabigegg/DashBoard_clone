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
  data: {
    type: Array,
    default: () => [],
  },
});

const chartOption = computed(() => {
  if (!props.data || !props.data.length) return null;

  const dates = props.data.map((d) => d.date);
  const inputQty = props.data.map((d) => d.input_qty);
  const defectQty = props.data.map((d) => d.defect_qty);
  const defectRate = props.data.map((d) => d.defect_rate);

  return {
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['投入數', '不良數', '不良率'],
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
      data: dates,
      axisLabel: {
        fontSize: 11,
        rotate: dates.length > 14 ? 30 : 0,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '數量',
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11 },
      },
      {
        type: 'value',
        name: '不良率 %',
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11, formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: '投入數',
        type: 'bar',
        data: inputQty,
        itemStyle: { color: 'rgb(147, 197, 253)', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 30,
      },
      {
        name: '不良數',
        type: 'bar',
        data: defectQty,
        itemStyle: { color: 'rgb(252, 165, 165)', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 30,
      },
      {
        name: '不良率',
        type: 'line',
        yAxisIndex: 1,
        data: defectRate,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: 'rgb(239, 68, 68)', width: 2 },
        itemStyle: { color: 'rgb(239, 68, 68)' },
      },
    ],
  };
});
</script>

<template>
  <div class="chart-card chart-card-full" role="img" aria-label="中段缺陷趨勢圖">
    <h3 class="chart-title">每日不良趨勢</h3>
    <VChart
      v-if="chartOption"
      class="chart-canvas chart-canvas-wide"
      :option="chartOption"
      :autoresize="{ throttle: 100 }"
    />
    <div v-else class="chart-empty">暫無資料</div>
  </div>
</template>
