<script setup lang="ts">
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

import { toPcs } from './utils';

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
  const yieldVals = rows.map((r) => Number(r.yield_pct ?? 0));
  const yieldMin = yieldVals.length ? Math.min(...yieldVals) : 0;
  const rightMin = Math.max(0, Math.floor(Math.min(yieldMin, threshold) - 2));
  const rightMax = 100;
  const labels = rows.map((r) => r.package || '(NA)');

  const barColors = rows.map((r) => {
    const yld = Number(r.yield_pct ?? 0);
    if (yld < threshold - 3) return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgb(239, 68, 68)' }, { offset: 1, color: 'rgba(239, 68, 68, 0.6)' }] };
    if (yld < threshold)     return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgb(245, 158, 11)' }, { offset: 1, color: 'rgba(245, 158, 11, 0.6)' }] };
    return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgb(99, 102, 241)' }, { offset: 1, color: 'rgba(99, 102, 241, 0.55)' }] };
  });

  return {
    animation: true,
    animationDuration: 700,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 400,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(0,0,0,0.04)' } },
      backgroundColor: 'rgba(255,255,255,0.97)',
      borderColor: '#e2e6ef',
      borderWidth: 1,
      textStyle: { fontSize: 12, color: '#222' },
      extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;',
      // TODO: type echarts callback
      formatter(params: unknown) {
        if (!Array.isArray(params) || !params.length) return '';
        const idx = Number((params[0] as Record<string, unknown>).dataIndex ?? 0);
        const row = rows[idx] || {};
        const yldPct = Number(row.yield_pct ?? 0);
        const color = yldPct < threshold ? '#ef4444' : '#22c55e';
        return [
          `<b style="font-size:13px">${row.package || '(NA)'}</b>`,
          `<span style="color:#666">報廢量：</span><b>${toPcs(row.scrap_qty).toLocaleString()}</b> pcs`,
          `<span style="color:#666">移轉量：</span>${toPcs(row.transaction_qty).toLocaleString()} pcs`,
          `<span style="color:#666">良率：</span><b style="color:${color}">${yldPct.toFixed(2)}%</b>`,
        ].join('<br/>');
      },
    },
    legend: {
      data: ['報廢量', '良率(%)'],
      top: 4,
      right: 12,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: 12, color: '#555' },
    },
    grid: { left: 60, right: 72, top: 52, bottom: 64 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: '#e2e6ef' } },
      axisTick: { show: false },
      axisLabel: {
        rotate: labels.length > 8 ? 35 : 0,
        fontSize: 11,
        color: '#555',
        interval: 0,
        overflow: 'truncate',
        width: 70,
      },
    },
    yAxis: [
      {
        type: 'value',
        axisLabel: {
          fontSize: 11,
          color: '#888',
          formatter: (v: number) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : String(v),
        },
        splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
      },
      {
        type: 'value',
        min: rightMin,
        max: rightMax,
        axisLabel: { formatter: '{value}%', fontSize: 11, color: '#888', margin: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '報廢量',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 40,
        barMinHeight: 2,
        itemStyle: {
          color: (params: unknown) => barColors[(params as Record<string, unknown>).dataIndex as number] ?? 'rgb(99,102,241)',
          borderRadius: [4, 4, 0, 0],
        },
        emphasis: {
          itemStyle: { shadowBlur: 12, shadowColor: 'rgba(99,102,241,0.4)' },
        },
        data: rows.map((r) => toPcs(r.scrap_qty)),
      },
      {
        name: '良率(%)',
        type: 'line',
        yAxisIndex: 1,
        smooth: 0.4,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 2.5, color: 'rgb(245, 158, 11)', shadowBlur: 6, shadowColor: 'rgba(245,158,11,0.3)' },
        itemStyle: { color: 'rgb(245, 158, 11)', borderWidth: 2, borderColor: '#fff' },
        areaStyle: { opacity: 0.08, color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.25)' }, { offset: 1, color: 'rgba(245,158,11,0)' }] } },
        emphasis: {
          scale: true,
          lineStyle: { width: 3 },
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(245,158,11,0.5)' },
        },
        data: rows.map((r) => Number(r.yield_pct ?? 0)),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: 'rgb(239, 68, 68)', width: 1.5, opacity: 0.7 },
          label: { formatter: `門檻 ${threshold}%`, fontSize: 10, color: 'rgb(239,68,68)', position: 'insideStartTop' },
          data: [{ yAxis: threshold }],
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <h3 class="chart-title">各 Package 報廢量與良率</h3>
    <div v-if="hasData" class="chart-body" role="img" aria-label="良率封裝圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">尚無 Package 資料</div>
  </article>
</template>
