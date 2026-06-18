<script setup lang="ts">
import { computed } from 'vue';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent]);

interface ParetoItem {
  alarm_text: string;
  count: number;
  cumulative_pct: number;
}

const props = defineProps<{
  items?: ParetoItem[];
  total?: number;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'bar-click', alarmText: string): void;
}>();

const hasData = computed(() => Array.isArray(props.items) && (props.items?.length ?? 0) > 0);

const chartOption = computed(() => {
  const items = props.items ?? [];
  const labels = items.map((i) => i.alarm_text || '(未知)');
  const counts = items.map((i) => Number(i.count || 0));
  const cumPcts = items.map((i) => Number((i.cumulative_pct ?? 0).toFixed(1)));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params: unknown[]) {
        const p = params as Array<{ seriesName: string; value: number; name: string }>;
        const bar = p.find((x) => x.seriesName === 'ALARM 次數');
        const line = p.find((x) => x.seriesName === '累積百分比');
        const name = p[0]?.name ?? '';
        const shortName = name.length > 40 ? `${name.slice(0, 40)}...` : name;
        return `${shortName}<br/>${bar ? `次數: ${bar.value}` : ''}<br/>${line ? `累積: ${line.value}%` : ''}`;
      },
    },
    legend: {
      data: ['ALARM 次數', '累積百分比'],
      bottom: 0,
    },
    grid: { left: 60, right: 60, top: 20, bottom: 60, containLabel: false },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: 30,
        interval: 0,
        formatter(value: string) {
          return value.length > 12 ? `${value.slice(0, 12)}...` : value;
        },
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '次數',
        position: 'left',
        axisLabel: {
          formatter(v: unknown) {
            return Number(v || 0).toLocaleString('zh-TW');
          },
        },
      },
      {
        type: 'value',
        name: '累積%',
        position: 'right',
        min: 0,
        max: 100,
        axisLabel: { formatter: (v: unknown) => `${v}%` },
      },
    ],
    series: [
      {
        name: 'ALARM 次數',
        type: 'bar',
        data: counts,
        itemStyle: { color: 'rgb(220, 38, 38)' },
        barMaxWidth: 40,
      },
      {
        name: '累積百分比',
        type: 'line',
        yAxisIndex: 1,
        data: cumPcts,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: 'rgb(234, 179, 8)' },
        itemStyle: { color: 'rgb(234, 179, 8)' },
        smooth: false,
      },
    ],
  };
});

// vue-echarts: bind @click on <VChart> (frontend-patterns.md)
function handleChartClick(params: { componentType?: string; dataIndex: number }): void {
  if (params?.componentType !== 'series') return;
  const item = props.items?.[params.dataIndex];
  if (item?.alarm_text) {
    emit('bar-click', item.alarm_text);
  }
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">
        ALARM Pareto 分析
        <span v-if="total" class="pareto-total-badge">共 {{ total }} 次</span>
      </div>
    </div>
    <div class="card-body ui-card-body pareto-chart-body">
      <LoadingSpinner v-if="loading" size="md" />
      <EmptyState v-else-if="!hasData" type="no-data" message="暫無 ALARM 資料" />
      <VChart
        v-else
        class="pareto-chart"
        :option="chartOption"
        autoresize
        @click="handleChartClick"
      />
    </div>
  </section>
</template>
