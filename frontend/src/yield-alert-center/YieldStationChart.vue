<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const props = defineProps({
  stationSummary: { type: Array, default: () => [] },
  riskThreshold: { type: Number, default: 98 },
});

const hasData = computed(() => props.stationSummary.length > 0);

// Sort ascending so worst stations appear at top (with inverse:true on yAxis)
const sortedRows = computed(() =>
  [...(props.stationSummary || [])].sort(
    (a, b) => Number(a.yield_pct ?? 0) - Number(b.yield_pct ?? 0),
  ),
);

const chartHeight = computed(() => Math.max(240, sortedRows.value.length * 32 + 60));

const chartOption = computed(() => {
  const rows = sortedRows.value;
  const threshold = props.riskThreshold;

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        if (!Array.isArray(params) || !params.length) return '';
        const idx = Number(params[0].dataIndex ?? 0);
        const row = rows[idx] || {};
        return [
          `<b>${row.station || '--'}</b>`,
          `良率：<b>${Number(row.yield_pct ?? 0).toFixed(2)}%</b>`,
          `移轉量：${Number(row.transaction_qty ?? 0).toLocaleString()}`,
          `報廢量：${Number(row.scrap_qty ?? 0).toLocaleString()}`,
        ].join('<br/>');
      },
    },
    grid: { left: 90, right: 60, top: 16, bottom: 24 },
    xAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%', fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((r) => r.station),
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 22,
        data: rows.map((r) => {
          const v = Number(r.yield_pct ?? 0);
          const color =
            v >= threshold ? 'rgb(34, 197, 94)' : v >= threshold - 3 ? 'rgb(245, 158, 11)' : 'rgb(239, 68, 68)';
          return { value: v, itemStyle: { color } };
        }),
        label: {
          show: true,
          position: 'right',
          formatter: (p) => `${Number(p.value ?? 0).toFixed(1)}%`,
          fontSize: 11,
          color: 'rgb(85, 85, 85)',
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">各站良率表現（由低到高）</h3>
    <div v-if="hasData" class="chart-body" :style="{ height: `${chartHeight}px` }" role="img" aria-label="良率站點圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">尚無站別資料</div>
  </article>
</template>
