<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

import { STATUS_COLORS } from '../../resource-shared/constants';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent]);

function resolveCssVar(varExpr: unknown): string {
  const match = String(varExpr).match(/var\((--[\w-]+)\)/);
  if (!match) return String(varExpr);
  return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim();
}

function toRgba(color: string, alpha: number): string {
  const m = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
  return m ? `rgba(${m[1]},${m[2]},${m[3]},${alpha})` : color;
}

const props = withDefaults(defineProps<{
  trend?: Record<string, unknown>[];
}>(), {
  trend: () => [],
});

const hasData = computed(() => props.trend.length > 0);

const statuses = ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST'];

const chartOption = computed(() => {
  const trend = props.trend || [];

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

        const index = Number((paramsList[0] as Record<string, unknown>).dataIndex || 0);
        const current = trend[index] || {};
        const total = statuses.reduce(
          (sum, status) => sum + Number(current[`${status.toLowerCase()}_hours`] || 0),
          0
        );

        const lines = paramsList.map((item) => {
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
    series: statuses.map((status) => {
      const color = resolveCssVar(STATUS_COLORS[status]);
      return {
        name: status,
        type: 'bar',
        stack: 'hours',
        itemStyle: { color },
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 22,
            shadowColor: toRgba(color, 0.75),
            borderColor: 'rgba(255,255,255,0.85)',
            borderWidth: 1.5,
          },
        },
        data: trend.map((item) => Number(item[`${status.toLowerCase()}_hours`] || 0)),
      };
    }),
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">E10 狀態時數分布</h3>
    <div v-if="hasData" class="chart-body" role="img" aria-label="設備稼動率堆疊圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">No data</div>
  </article>
</template>
