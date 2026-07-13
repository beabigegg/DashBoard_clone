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
  'rgb(2, 132, 199)',
  'rgb(220, 38, 38)',
  'rgb(22, 163, 74)',
  'rgb(234, 179, 8)',
  'rgb(168, 85, 247)',
  'rgb(249, 115, 22)',
]);

// Native M[60] hourly granularity only — no day/hour switch (unlike eap-alarm's
// trend), per interaction-design.md §Deleted Controls.
const GROUP_BY_OPTIONS = Object.freeze([
  { value: 'family', label: '機型' },
  { value: 'equipment_id', label: '機台' },
  { value: 'package', label: 'Package' },
]);

interface TrendSeries {
  name: string;
  data: (number | null)[];
}

const props = defineProps<{
  labels?: string[];
  series?: TrendSeries[];
  groupBy?: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'group-by-change', value: string): void;
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
    // Legend clicks toggle series visibility — standard ECharts behavior,
    // confirmed #5. No extra handler needed to enable this.
    legend: {
      data: seriesData.map((s) => s.name),
      bottom: 0,
      type: 'scroll',
    },
    grid: { left: 60, right: 24, top: 20, bottom: 60, containLabel: false },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: 45,
        formatter(value: string) {
          return value.length > 13 ? `${value.slice(0, 13)}` : value;
        },
      },
    },
    yAxis: {
      type: 'value',
      name: 'UPH',
      axisLabel: {
        formatter(v: unknown) {
          return Number(v || 0).toLocaleString('zh-TW');
        },
      },
    },
    series: seriesData.map((s, i) => ({
      name: s.name,
      type: 'line',
      // `connectNulls` intentionally left at its default (false): a missing
      // hour bucket arrives as `null` and must render as a visual gap, never
      // as an implicit zero (interaction-design.md — "a trend gap is not a
      // zero").
      data: s.data,
      smooth: false,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
      itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
    })),
  };
});
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">UPH 趨勢</div>
      <div class="trend-groupby-toggle" data-testid="ctrl-trend-groupby">
        <button
          v-for="opt in GROUP_BY_OPTIONS"
          :key="opt.value"
          type="button"
          :class="['ui-btn ui-btn--sm', (groupBy ?? 'family') === opt.value ? 'ui-btn--primary' : 'ui-btn--ghost']"
          @click="emit('group-by-change', opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>
    <div class="card-body ui-card-body trend-chart-body">
      <LoadingSpinner v-if="loading" size="md" />
      <EmptyState v-else-if="!hasData" type="no-data" message="暫無 UPH 趨勢資料" />
      <VChart
        v-else
        class="trend-chart"
        :option="chartOption"
        autoresize
      />
    </div>
  </section>
</template>
