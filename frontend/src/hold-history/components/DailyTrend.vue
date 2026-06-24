<script setup lang="ts">
import { computed } from 'vue';

import { BarChart, EffectScatterChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

use([CanvasRenderer, BarChart, LineChart, EffectScatterChart, GridComponent, LegendComponent, TooltipComponent]);

interface TrendDayRow {
  date?: string;
  releaseQty?: number;
  newHoldQty?: number;
  futureHoldQty?: number;
  holdQty?: number;
}

interface Props {
  days?: TrendDayRow[];
}

const props = withDefaults(defineProps<Props>(), {
  days: () => [],
});

const hasData = computed(() => (props.days || []).length > 0);

const chartOption = computed(() => {
  const days = props.days || [];
  const dates = days.map((item) => item.date ?? '');
  const release = days.map((item) => Number(item.releaseQty || 0));
  const newHold = days.map((item) => -Math.abs(Number(item.newHoldQty || 0)));
  const futureHold = days.map((item) => -Math.abs(Number(item.futureHoldQty || 0)));
  const stock = days.map((item) => Number(item.holdQty || 0));

  // Last day with any activity (release / new / future hold), not just carry-forward stock
  const lastStockIdx = days.reduce((acc, item, i) => {
    const active =
      Number(item.releaseQty || 0) > 0 ||
      Number(item.newHoldQty || 0) > 0 ||
      Number(item.futureHoldQty || 0) > 0;
    return active ? i : acc;
  }, -1);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ dataIndex?: number }>;
        const index = Number(p?.[0]?.dataIndex || 0);
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
      left: 8,
      right: 8,
      top: 30,
      bottom: 52,
      containLabel: true,
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
          // TODO: type echarts callback
          formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
      {
        type: 'value',
        name: 'On Hold',
        axisLabel: {
          // TODO: type echarts callback
          formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
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
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(22, 163, 74, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'New Hold',
        type: 'bar',
        stack: 'negative',
        data: newHold,
        itemStyle: { color: 'rgb(220, 38, 38)' },
        barMaxWidth: 18,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(220, 38, 38, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'Future Hold',
        type: 'bar',
        stack: 'negative',
        data: futureHold,
        itemStyle: { color: 'rgb(249, 115, 22)' },
        barMaxWidth: 18,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(249, 115, 22, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
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
      ...(lastStockIdx >= 0
        ? [
            {
              name: '_pulse',
              type: 'effectScatter',
              yAxisIndex: 1,
              symbolSize: 9,
              showEffectOn: 'render',
              rippleEffect: { brushType: 'stroke', scale: 3.5, period: 2 },
              data: [[dates[lastStockIdx], stock[lastStockIdx]]],
              itemStyle: { color: 'rgb(37, 99, 235)' },
              silent: true,
              legendHoverLink: false,
              tooltip: { show: false },
            },
          ]
        : []),
    ],
  };
});
</script>

<template>
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="hh-card-title">Daily Trend</h3>
    </template>
    <div v-if="hasData" class="trend-chart-wrap" role="img" aria-label="Hold 每日趨勢圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="hh-chart-empty">No data</div>
  </SectionCard>
</template>
