<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, TitleComponent]);

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  mode: {
    type: String,
    default: 'pareto',
  },
  data: {
    type: Array,
    default: () => [],
  },
  field: {
    type: String,
    default: '',
  },
  selectedValue: {
    type: String,
    default: '',
  },
  lineLabel: {
    type: String,
    default: '',
  },
  lineColor: {
    type: String,
    default: '#6366f1',
  },
});

const emit = defineEmits(['select']);

function emptyOption() {
  return {
    title: {
      text: '無資料',
      left: 'center',
      top: 'center',
      textStyle: { color: '#94a3b8', fontSize: 14 },
    },
    xAxis: { show: false },
    yAxis: { show: false },
    series: [],
  };
}

const chartOption = computed(() => {
  const data = props.data || [];
  if (!data.length) {
    return emptyOption();
  }

  if (props.mode === 'pareto') {
    const names = data.map((item) => item.name);
    const printRates = data.map((item) => Number(item.print_defect_rate || 0));
    const leadRates = data.map((item) => Number(item.lead_defect_rate || 0));
    const cumPct = data.map((item) => Number(item.cumulative_pct || 0));

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
      },
      legend: { data: ['印字不良率', '腳型不良率', '累積%'], bottom: 0 },
      grid: { left: 56, right: 56, top: 24, bottom: names.length > 8 ? 90 : 56 },
      xAxis: {
        type: 'category',
        data: names,
        axisLabel: {
          rotate: names.length > 8 ? 35 : 0,
          interval: 0,
          formatter: (value) => (value.length > 16 ? `${value.slice(0, 16)}...` : value),
        },
      },
      yAxis: [
        { type: 'value', name: '不良率(%)', splitLine: { lineStyle: { type: 'dashed' } } },
        { type: 'value', name: '累積%', max: 100 },
      ],
      series: [
        {
          name: '印字不良率',
          type: 'bar',
          stack: 'defect',
          data: printRates,
          itemStyle: { color: '#ef4444' },
          barMaxWidth: 40,
        },
        {
          name: '腳型不良率',
          type: 'bar',
          stack: 'defect',
          data: leadRates,
          itemStyle: { color: '#f59e0b' },
          barMaxWidth: 40,
        },
        {
          name: '累積%',
          type: 'line',
          yAxisIndex: 1,
          data: cumPct,
          itemStyle: { color: '#6366f1' },
          lineStyle: { width: 2 },
          symbol: 'circle',
          symbolSize: 6,
        },
      ],
    };
  }

  const dates = data.map((item) => item.date);
  const lineValues = data.map((item) => Number(item[props.mode === 'print-trend' ? 'print_defect_rate' : 'lead_defect_rate'] || 0));
  const inputValues = data.map((item) => Number(item.input_qty || 0));

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: [props.lineLabel || '趨勢', '投入數'], bottom: 0 },
    grid: { left: 56, right: 56, top: 24, bottom: 56 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: dates.length > 14 ? 35 : 0 },
    },
    yAxis: [
      { type: 'value', name: '不良率(%)', splitLine: { lineStyle: { type: 'dashed' } } },
      { type: 'value', name: '投入數' },
    ],
    series: [
      {
        name: props.lineLabel || '趨勢',
        type: 'line',
        data: lineValues,
        itemStyle: { color: props.lineColor },
        lineStyle: { width: 2 },
        symbol: 'circle',
        symbolSize: 4,
      },
      {
        name: '投入數',
        type: 'bar',
        yAxisIndex: 1,
        data: inputValues,
        itemStyle: { color: '#c7d2fe' },
        barMaxWidth: 20,
      },
    ],
  };
});

function handleClick(params) {
  if (props.mode !== 'pareto' || params?.componentType !== 'series' || !params?.name || !props.field) {
    return;
  }
  emit('select', {
    field: props.field,
    value: params.name,
    label: `${props.field}: ${params.name}`,
  });
}
</script>

<template>
  <article class="tmtt-chart-card">
    <h3>{{ title }}</h3>
    <VChart class="tmtt-chart-canvas" :option="chartOption" autoresize @click="handleClick" />
  </article>
</template>
