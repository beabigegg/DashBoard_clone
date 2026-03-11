<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const props = defineProps({
  comparison: {
    type: Array,
    default: () => [],
  },
});

const rankedData = computed(() => {
  return [...(props.comparison || [])]
    .sort((left, right) => Number(right.ou_pct || 0) - Number(left.ou_pct || 0))
    .slice(0, 15);
});

const hasData = computed(() => rankedData.value.length > 0);

const chartOption = computed(() => {
  const rows = rankedData.value;

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        if (!Array.isArray(params) || !params.length) {
          return '';
        }
        const idx = Number(params[0].dataIndex || 0);
        const row = rows[idx] || {};
        return `${row.workcenter || '--'}<br/>OU%: <b>${Number(row.ou_pct || 0).toFixed(1)}%</b><br/>機台數: ${
          Number(row.machine_count || 0)
        }`;
      },
    },
    grid: {
      left: 110,
      right: 24,
      top: 20,
      bottom: 24,
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: {
        formatter: '{value}%',
      },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((item) => item.workcenter),
      axisLabel: {
        fontSize: 11,
      },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 20,
        data: rows.map((item) => ({
          value: Number(item.ou_pct || 0),
          itemStyle: {
            color:
              Number(item.ou_pct || 0) >= 80
                ? 'rgb(34, 197, 94)'
                : Number(item.ou_pct || 0) >= 50
                  ? 'rgb(245, 158, 11)'
                  : 'rgb(239, 68, 68)',
          },
        })),
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">Top 15 Workcenter OU%</h3>
    <div v-if="hasData" class="chart-body">
      <VChart :option="chartOption" autoresize />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>
