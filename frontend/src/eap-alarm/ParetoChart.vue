<script setup lang="ts">
import { computed } from 'vue';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import { BarChart, LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
]);

const MAX_VISIBLE_CATEGORIES = 15;

interface ParetoItem {
  // `name` is the generic dim value; `alarm_text` is the legacy alias kept in
  // the API for backward compatibility — read name first, fall back to alias.
  name?: string;
  alarm_text?: string;
  count: number;
  cumulative_pct: number;
}

// Selectable pareto dimensions (must match backend GROUP_DIMENSIONS keys)
const DIM_OPTIONS = Object.freeze([
  { value: 'alarm_text', label: 'ALARM 訊息' },
  { value: 'eqp_id', label: '機台' },
  { value: 'lot_id', label: 'LOT' },
  { value: 'pj_type', label: 'PJ 類型' },
  { value: 'product_line', label: 'Package' },
  { value: 'pj_bop', label: 'BOP' },
]);

const props = defineProps<{
  items?: ParetoItem[];
  total?: number;
  dim?: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'bar-click', name: string): void;
  (e: 'dim-change', dim: string): void;
}>();

const hasData = computed(() => Array.isArray(props.items) && (props.items?.length ?? 0) > 0);

function itemName(i: ParetoItem): string {
  return i.name ?? i.alarm_text ?? '(未知)';
}

const chartOption = computed(() => {
  const items = props.items ?? [];
  const labels = items.map((i) => itemName(i));
  const counts = items.map((i) => Number(i.count || 0));
  const cumPcts = items.map((i) => Number((i.cumulative_pct ?? 0).toFixed(1)));
  const needsHorizontalZoom = items.length > MAX_VISIBLE_CATEGORIES;
  const initialZoomEnd = needsHorizontalZoom
    ? Math.max(1, (MAX_VISIBLE_CATEGORIES / items.length) * 100)
    : 100;

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
      top: 0,
      left: 'center',
    },
    grid: {
      left: 64,
      right: 64,
      top: 52,
      bottom: needsHorizontalZoom ? 112 : 82,
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisTick: { alignWithLabel: true },
      axisLabel: {
        rotate: needsHorizontalZoom ? 35 : 25,
        interval: 0,
        width: 96,
        overflow: 'truncate',
        formatter(value: string) {
          return value.length > 14 ? `${value.slice(0, 14)}...` : value;
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
    dataZoom: needsHorizontalZoom
      ? [
          {
            type: 'inside',
            xAxisIndex: 0,
            start: 0,
            end: initialZoomEnd,
            zoomOnMouseWheel: true,
            moveOnMouseMove: true,
            moveOnMouseWheel: true,
          },
          {
            type: 'slider',
            xAxisIndex: 0,
            start: 0,
            end: initialZoomEnd,
            bottom: 10,
            height: 20,
            brushSelect: false,
            showDetail: false,
            borderColor: 'rgb(203, 213, 225)',
            fillerColor: 'rgba(37, 99, 235, 0.16)',
            handleStyle: {
              color: 'rgb(37, 99, 235)',
              borderColor: 'rgb(37, 99, 235)',
            },
          },
        ]
      : [],
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
  const name = item ? (item.name ?? item.alarm_text) : undefined;
  if (name) {
    emit('bar-click', name);
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
      <div class="trend-granularity-toggle" data-testid="pareto-dim-toggle">
        <button
          v-for="opt in DIM_OPTIONS"
          :key="opt.value"
          type="button"
          :class="['ui-btn ui-btn--sm', (dim ?? 'alarm_text') === opt.value ? 'ui-btn--primary' : 'ui-btn--ghost']"
          @click="emit('dim-change', opt.value)"
        >
          {{ opt.label }}
        </button>
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
