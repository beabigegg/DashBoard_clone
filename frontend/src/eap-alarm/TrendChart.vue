<script setup lang="ts">
import { computed } from 'vue';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent]);

// ECharts color palette for series (css-contract §6: chart color exception)
const SERIES_COLORS = Object.freeze([
  'rgb(220, 38, 38)',
  'rgb(2, 132, 199)',
  'rgb(22, 163, 74)',
  'rgb(234, 179, 8)',
  'rgb(168, 85, 247)',
  'rgb(249, 115, 22)',
  'rgb(236, 72, 153)',
  'rgb(14, 165, 233)',
  'rgb(132, 204, 22)',
  'rgb(251, 191, 36)',
]);

interface TrendSeries {
  eqp_type: string;
  data: number[];
}

const props = defineProps<{
  labels?: string[];
  series?: TrendSeries[];
  granularity?: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'granularity-change', value: string): void;
}>();

const hasData = computed(() => Array.isArray(props.series) && (props.series?.length ?? 0) > 0);

const chartOption = computed(() => {
  const labels = props.labels ?? [];
  const seriesData = props.series ?? [];

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: seriesData.map((s) => s.eqp_type),
      bottom: 0,
      type: 'scroll',
    },
    grid: { left: 60, right: 24, top: 20, bottom: 80, containLabel: false },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: props.granularity === 'hour' ? 45 : 0,
        formatter(value: string) {
          return value.length > 10 ? `${value.slice(0, 10)}` : value;
        },
      },
    },
    yAxis: {
      type: 'value',
      name: 'ALARM 次數',
      axisLabel: {
        formatter(v: unknown) {
          return Number(v || 0).toLocaleString('zh-TW');
        },
      },
    },
    series: seriesData.map((s, i) => ({
      name: s.eqp_type,
      type: 'line',
      data: s.data,
      smooth: false,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
      itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
      stack: 'total',
      areaStyle: { opacity: 0.15 },
    })),
  };
});
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">ALARM 趨勢</div>
      <div class="trend-granularity-toggle">
        <button
          type="button"
          :class="['ui-btn ui-btn--sm', granularity === 'day' ? 'ui-btn--primary' : 'ui-btn--ghost']"
          @click="emit('granularity-change', 'day')"
        >
          日
        </button>
        <button
          type="button"
          :class="['ui-btn ui-btn--sm', granularity === 'hour' ? 'ui-btn--primary' : 'ui-btn--ghost']"
          @click="emit('granularity-change', 'hour')"
        >
          時
        </button>
      </div>
    </div>
    <div class="card-body ui-card-body trend-chart-body">
      <LoadingSpinner v-if="loading" size="md" />
      <EmptyState v-else-if="!hasData" type="no-data" message="暫無趨勢資料" />
      <VChart
        v-else
        class="trend-chart"
        :option="chartOption"
        autoresize
      />
    </div>
  </section>
</template>
