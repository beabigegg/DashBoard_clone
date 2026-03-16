<script setup>
import { computed } from 'vue';

import { HeatmapChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, DataZoomComponent]);

const props = defineProps({
  heatmap: {
    type: Array,
    default: () => [],
  },
  granularity: {
    type: String,
    default: 'day',
  },
});

const GRANULARITY_LABEL = { day: '日', week: '週', month: '月', year: '年' };

const hasData = computed(() => props.heatmap.length > 0);

const parsedHeatmap = computed(() => {
  const rows = props.heatmap || [];

  const seqByStation = {};
  rows.forEach((row) => {
    seqByStation[row.station] = Number(row.station_seq ?? 999);
  });

  const stations = [...new Set(rows.map((row) => row.station))].sort(
    (a, b) => (seqByStation[a] ?? 999) - (seqByStation[b] ?? 999),
  );
  const dates = [...new Set(rows.map((row) => row.date))].sort();

  const matrixData = rows.map((row) => [
    dates.indexOf(row.date),
    stations.indexOf(row.station),
    Number(row.yield_pct ?? 0),
  ]);

  // Compute dynamic min for better colour contrast
  const values = rows.map((r) => Number(r.yield_pct ?? 0)).filter((v) => v > 0);
  const dataMin = values.length ? Math.max(0, Math.floor(Math.min(...values) - 2)) : 80;

  return { stations, dates, matrixData, dataMin };
});

// Row height per station — ensure enough space for in-cell labels
const ROW_HEIGHT = 42;
const VISIBLE_DATE_COUNT = 14;

const chartHeight = computed(() => {
  const stationCount = parsedHeatmap.value.stations.length;
  return Math.max(340, stationCount * ROW_HEIGHT + 140);
});

const needsDateZoom = computed(() => parsedHeatmap.value.dates.length > VISIBLE_DATE_COUNT);

const chartOption = computed(() => {
  const { stations, dates, matrixData, dataMin } = parsedHeatmap.value;

  // When dataZoom is active, only the visible window matters for label density
  const visibleDateCount = needsDateZoom.value ? VISIBLE_DATE_COUNT : dates.length;
  const showLabel = visibleDateCount <= 31 && stations.length <= 20;
  const rotateLabel = dates.length > 10 ? 45 : 0;

  const dataZoom = needsDateZoom.value
    ? [
        {
          type: 'slider',
          xAxisIndex: 0,
          bottom: 38,
          height: 18,
          startValue: Math.max(0, dates.length - VISIBLE_DATE_COUNT),
          endValue: dates.length - 1,
          brushSelect: false,
          labelFormatter: (_, val) => val,
        },
        { type: 'inside', xAxisIndex: 0 },
      ]
    : [];

  return {
    tooltip: {
      position: 'top',
      formatter(params) {
        const xIdx = Number(params.value?.[0] ?? 0);
        const yIdx = Number(params.value?.[1] ?? 0);
        const val = Number(params.value?.[2] ?? 0);
        return `${stations[yIdx] ?? '--'}<br/>${dates[xIdx] ?? '--'}<br/>良率: <b>${val.toFixed(2)}%</b>`;
      },
    },
    grid: {
      left: 110,
      right: 20,
      top: 20,
      bottom: needsDateZoom.value ? 100 : 80,
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      data: dates,
      splitArea: { show: true },
      axisLabel: { fontSize: 11, rotate: rotateLabel },
    },
    yAxis: {
      type: 'category',
      data: stations,
      splitArea: { show: true },
      axisLabel: { fontSize: 11 },
    },
    dataZoom,
    visualMap: {
      min: dataMin,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 14,
      itemHeight: 140,
      text: ['100%', `${dataMin}%`],
      textStyle: { fontSize: 11 },
      inRange: { color: ['rgb(239, 68, 68)', 'rgb(245, 158, 11)', 'rgb(34, 197, 94)'] },
    },
    series: [
      {
        type: 'heatmap',
        data: matrixData,
        label: {
          show: showLabel,
          formatter: (p) => {
            const v = Number(p.value?.[2] ?? 0);
            return v === 100 ? '' : v.toFixed(1);
          },
          fontSize: 10,
          fontWeight: 600,
          color: 'rgb(255, 255, 255)',
          textShadowColor: 'rgba(0, 0, 0, 0.5)',
          textShadowBlur: 3,
        },
        itemStyle: {
          borderWidth: 1,
          borderColor: 'rgba(255, 255, 255, 0.6)',
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">站別 × 日期 良率熱圖 ({{ GRANULARITY_LABEL[granularity] ?? granularity }})</h3>
    <div v-if="hasData" class="heatmap-body" :style="{ height: `${chartHeight}px` }" role="img" aria-label="良率熱力圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">尚無熱圖資料</div>
  </article>
</template>
