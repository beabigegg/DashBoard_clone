<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

import { STATUS_COLORS } from '../../resource-shared/constants.js';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  trend: {
    type: Array,
    default: () => [],
  },
});

const hasData = computed(() => props.trend.length > 0);

const statuses = ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST'];

const chartOption = computed(() => {
  const trend = props.trend || [];

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        if (!Array.isArray(params) || !params.length) {
          return '';
        }

        const index = Number(params[0].dataIndex || 0);
        const current = trend[index] || {};
        const total = statuses.reduce(
          (sum, status) => sum + Number(current[`${status.toLowerCase()}_hours`] || 0),
          0
        );

        const lines = params.map((item) => {
          const value = Number(item.value || 0);
          const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
          return `${item.marker}${item.seriesName}: ${value.toFixed(1)}h (${pct}%)`;
        });

        return [`<b>${current.date || '--'}</b>`, ...lines, `<b>Total: ${total.toFixed(1)}h</b>`].join('<br/>');
      },
    },
    legend: {
      data: statuses,
      bottom: 0,
    },
    grid: {
      left: 46,
      right: 20,
      top: 24,
      bottom: 60,
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
      axisLabel: {
        formatter: '{value}h',
      },
    },
    series: statuses.map((status) => ({
      name: status,
      type: 'bar',
      stack: 'hours',
      itemStyle: {
        color: STATUS_COLORS[status],
      },
      data: trend.map((item) => Number(item[`${status.toLowerCase()}_hours`] || 0)),
    })),
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">E10 狀態時數分布</h3>
    <div v-if="hasData" class="chart-body">
      <VChart :option="chartOption" autoresize />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>
