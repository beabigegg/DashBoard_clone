<script setup>
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  activeReason: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['toggle']);

const hasData = computed(() => (props.items || []).length > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const reasons = items.map((item) => item.reason || '(未填寫)');
  const qtys = items.map((item) => Number(item.qty || 0));
  const cumPct = items.map((item) => Number(item.cumPct || 0));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const index = Number(params?.[0]?.dataIndex || 0);
        const item = items[index] || {};
        const reason = item.reason || '(未填寫)';
        return [
          `<b>${reason}</b>`,
          `數量: ${Number(item.qty || 0).toLocaleString('zh-TW')}`,
          `Lot 數: ${Number(item.count || 0).toLocaleString('zh-TW')}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
          `累積占比: ${Number(item.cumPct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    legend: {
      data: ['數量', '累積%'],
      bottom: 0,
    },
    grid: {
      left: 8,
      right: 8,
      top: 30,
      bottom: 100,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: reasons,
      axisLabel: {
        interval: 0,
        rotate: reasons.length > 5 ? 35 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 92,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '數量',
        axisLabel: {
          formatter: (value) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: {
          formatter: '{value}%',
        },
      },
    ],
    series: [
      {
        name: '數量',
        type: 'bar',
        data: qtys,
        itemStyle: {
          color(params) {
            const reason = reasons[params.dataIndex] || '';
            return reason === props.activeReason ? 'rgb(220, 38, 38)' : 'rgb(29, 78, 216)';
          },
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 36,
      },
      {
        name: '累積%',
        type: 'line',
        yAxisIndex: 1,
        data: cumPct,
        lineStyle: { color: 'rgb(245, 158, 11)', width: 2 },
        itemStyle: { color: 'rgb(245, 158, 11)' },
        symbolSize: 6,
      },
    ],
  };
});

function handleChartClick(params) {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const selected = props.items?.[params.dataIndex]?.reason;
  if (!selected) {
    return;
  }
  emit('toggle', selected);
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">Reason Pareto</div>
    </div>
    <div class="card-body ui-card-body">
      <div v-if="hasData" class="pareto-chart-wrap" role="img" aria-label="Hold 原因柏拉圖">
        <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
      </div>
      <div v-else class="placeholder">No data</div>
    </div>
  </section>
</template>
