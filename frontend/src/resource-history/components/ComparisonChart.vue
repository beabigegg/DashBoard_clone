<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const props = withDefaults(defineProps<{
  comparison?: Record<string, unknown>[];
}>(), {
  comparison: () => [],
});

const rankedData = computed(() => {
  return [...(props.comparison || [])]
    .filter((item) => item.ou_pct != null && item.ou_pct !== '')
    .sort((left, right) => Number(right.ou_pct || 0) - Number(left.ou_pct || 0));
});

const hasData = computed(() => rankedData.value.length > 0);

const ROW_HEIGHT = 36;
const GRID_OVERHEAD = 44; // top:20 + bottom:24

const chartBodyHeight = computed(() => {
  const rows = rankedData.value.length;
  return Math.min(Math.max(280, rows * ROW_HEIGHT + GRID_OVERHEAD), 900);
});

const chartOption = computed(() => {
  const rows = rankedData.value;

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const paramsList = params as Record<string, unknown>[];
        if (!Array.isArray(paramsList) || !paramsList.length) {
          return '';
        }
        const idx = Number((paramsList[0] as Record<string, unknown>).dataIndex || 0);
        const row = rows[idx] || {};
        return `${row.workcenter || '--'}<br/>OU%: <b>${Number(row.ou_pct || 0).toFixed(1)}%</b><br/>機台數: ${
          Number(row.machine_count || 0)
        }`;
      },
    },
    grid: {
      left: 120,
      right: 58,
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
        fontSize: 13,
        fontWeight: 500,
      },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 22,
        label: {
          show: true,
          position: 'right',
          fontSize: 11,
          color: '#475569',
          formatter: (params: unknown) =>
            `${Number((params as Record<string, unknown>).value || 0).toFixed(1)}%`,
        },
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 22,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(255,255,255,0.45)',
            borderColor: 'rgba(255,255,255,0.9)',
            borderWidth: 1.5,
          },
        },
        data: rows.map((item) => {
          const pct = Number(item.ou_pct || 0);
          const color = pct >= 80 ? 'rgb(34, 197, 94)' : pct >= 50 ? 'rgb(245, 158, 11)' : 'rgb(239, 68, 68)';
          return { value: pct, itemStyle: { color } };
        }),
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">Workcenter OU%</h3>
    <div v-if="hasData" class="chart-body" :style="{ height: chartBodyHeight + 'px' }" role="img" aria-label="設備稼動率比較圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data" :style="{ height: chartBodyHeight + 'px' }">No data</div>
  </article>
</template>
