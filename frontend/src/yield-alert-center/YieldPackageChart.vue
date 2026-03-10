<script setup>
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  packageSummary: { type: Array, default: () => [] },
  riskThreshold: { type: Number, default: 98 },
});

const hasData = computed(() => props.packageSummary.length > 0);

const sortedRows = computed(() =>
  [...(props.packageSummary || [])].sort(
    (a, b) => Number(b.scrap_qty ?? 0) - Number(a.scrap_qty ?? 0),
  ),
);

const chartOption = computed(() => {
  const rows = sortedRows.value;
  const threshold = props.riskThreshold;
  const labels = rows.map((r) => r.package || '(NA)');

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        if (!Array.isArray(params) || !params.length) return '';
        const idx = Number(params[0].dataIndex ?? 0);
        const row = rows[idx] || {};
        return [
          `<b>${row.package || '(NA)'}</b>`,
          `報廢量：<b>${Number(row.scrap_qty ?? 0).toLocaleString()}</b>`,
          `移轉量：${Number(row.transaction_qty ?? 0).toLocaleString()}`,
          `良率：<b>${Number(row.yield_pct ?? 0).toFixed(2)}%</b>`,
        ].join('<br/>');
      },
    },
    legend: {
      data: ['報廢量', '良率(%)'],
      top: 0,
      textStyle: { fontSize: 12 },
    },
    grid: { left: 60, right: 60, top: 40, bottom: 60 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: labels.length > 8 ? 35 : 0,
        fontSize: 11,
        interval: 0,
        overflow: 'truncate',
        width: 70,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '報廢量',
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11 },
      },
      {
        type: 'value',
        name: '良率(%)',
        nameTextStyle: { fontSize: 11 },
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%', fontSize: 11 },
      },
    ],
    series: [
      {
        name: '報廢量',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 36,
        data: rows.map((r) => {
          const v = Number(r.scrap_qty ?? 0);
          return { value: v, itemStyle: { color: '#6366f1' } };
        }),
      },
      {
        name: '良率(%)',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
        data: rows.map((r) => {
          const v = Number(r.yield_pct ?? 0);
          return v;
        }),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: '#ef4444', width: 1 },
          data: [{ yAxis: threshold, label: { formatter: `門檻 ${threshold}%`, fontSize: 10 } }],
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">各 Package 報廢量與良率</h3>
    <div v-if="hasData" class="chart-body">
      <VChart :option="chartOption" autoresize />
    </div>
    <div v-else class="chart-no-data">尚無 Package 資料</div>
  </article>
</template>
