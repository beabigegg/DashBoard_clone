<script setup lang="ts">
import { computed } from 'vue';

import { Download } from 'lucide-vue-next';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, MarkLineComponent, LegendComponent]);

const GRANULARITY_LABEL = { day: '日', week: '週', month: '月', year: '年' };

const props = defineProps({
  trend: { type: Array, default: () => [] },
  riskThreshold: { type: Number, default: 98 },
  granularity: { type: String, default: 'day' },
});

const hasData = computed(() => props.trend.length > 0);

function downloadCSV() {
  const items = props.trend || [];
  if (!items.length) return;
  const granLabel = props.granularity || 'day';
  const header = ['日期', '移轉量', '報廢量', '良率(%)'].join(',');
  const rows = items.map((r) => [
    r.date_bucket,
    Number(r.transaction_qty ?? 0),
    Number(r.scrap_qty ?? 0),
    Number(r.yield_pct ?? 0).toFixed(4),
  ].join(','));
  const csv = ['﻿', header, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `良率趨勢_${granLabel}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const chartOption = computed(() => {
  const items = props.trend || [];
  const threshold = Number(props.riskThreshold || 98);

  const yieldVals = items.map((i) => Number(i.yield_pct ?? 0));
  const inputVals = items.map((i) => Number(i.transaction_qty ?? 0));
  const dataMin = yieldVals.length ? Math.min(...yieldVals) : 0;
  const dataMax = yieldVals.length ? Math.max(...yieldVals) : 100;
  const yMin = Math.max(0, Math.floor(Math.min(dataMin, threshold) - 2));
  const yMax = Math.ceil(Math.max(dataMax, 100) + 1);

  const dense = items.length > 40;
  const rotateLabel = items.length > 20 ? 35 : 0;

  // Bar color: reflect yield health for each period
  const barColors = yieldVals.map((yld) => {
    if (yld < threshold - 3) return 'rgba(239,68,68,0.28)';
    if (yld < threshold)     return 'rgba(245,158,11,0.32)';
    return 'rgba(148,163,184,0.38)';
  });

  return {
    animation: true,
    animationDuration: 900,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 400,
    animationEasingUpdate: 'cubicInOut',
    legend: {
      top: 6,
      right: 16,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: 11, color: '#6b7280' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: '#6366f1', width: 1, opacity: 0.4, type: 'dashed' } },
      backgroundColor: 'rgba(255,255,255,0.97)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      padding: [10, 14],
      extraCssText: 'box-shadow:0 4px 20px rgba(0,0,0,0.1);border-radius:8px;',
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = Array.isArray(params) ? params : [];
        const idx = Number((p[0] as Record<string, unknown>)?.dataIndex ?? 0);
        const item = items[idx] || {};
        const yld = Number(item.yield_pct ?? 0);
        const yldColor = yld < threshold ? '#ef4444' : '#10b981';
        return [
          `<div style="font-weight:600;color:#111827;margin-bottom:6px;font-size:12px">${(p[0] as Record<string, unknown>)?.name ?? ''}</div>`,
          `<div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:3px"><span style="color:#6b7280">良率</span><b style="color:${yldColor}">${yld.toFixed(2)}%</b></div>`,
          `<div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:3px"><span style="color:#6b7280">Input</span><span>${Number(item.transaction_qty ?? 0).toLocaleString()} pcs</span></div>`,
          `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:#6b7280">報廢</span><span>${Number(item.scrap_qty ?? 0).toLocaleString()} pcs</span></div>`,
        ].join('');
      },
    },
    grid: { left: 60, right: 72, top: 44, bottom: rotateLabel > 0 ? 80 : 52 },
    xAxis: {
      type: 'category',
      data: items.map((i) => i.date_bucket),
      axisLabel: { fontSize: 11, color: '#9ca3af', rotate: rotateLabel },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: [
      {
        type: 'value',
        min: yMin,
        max: yMax,
        axisLabel: { formatter: '{value}%', fontSize: 11, color: '#9ca3af' },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#f3f4f6' } },
      },
      {
        type: 'value',
        axisLabel: {
          fontSize: 11,
          color: '#9ca3af',
          formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v),
          margin: 10,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Input',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 22,
        barMinWidth: 4,
        itemStyle: {
          color: (params: unknown) => barColors[(params as Record<string, unknown>).dataIndex as number] ?? 'rgba(148,163,184,0.38)',
          borderRadius: [2, 2, 0, 0],
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 8,
            shadowColor: 'rgba(0,0,0,0.18)',
          },
        },
        data: inputVals,
      },
      {
        name: '良率%',
        type: 'line',
        yAxisIndex: 0,
        smooth: 0.3,
        symbolSize: dense ? 4 : 7,
        symbol: 'circle',
        showSymbol: !dense,
        z: 3,
        lineStyle: { width: 2.5, color: '#6366f1' },
        itemStyle: { color: '#6366f1', borderColor: '#fff', borderWidth: 2 },
        emphasis: {
          disabled: false,
          scale: true,
          focus: 'series',
          itemStyle: {
            symbolSize: dense ? 8 : 11,
            shadowBlur: 12,
            shadowColor: 'rgba(99,102,241,0.55)',
            borderWidth: 2.5,
            borderColor: '#fff',
          },
        },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(99,102,241,0.22)' },
              { offset: 1, color: 'rgba(99,102,241,0)' },
            ],
          },
        },
        data: yieldVals,
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ yAxis: threshold }],
          lineStyle: { color: '#ef4444', type: 'dashed', width: 1.5, opacity: 0.65 },
          label: {
            formatter: `門檻 ${threshold}%`,
            color: '#ef4444',
            fontSize: 11,
            position: 'insideStartTop',
            backgroundColor: 'rgba(254,242,242,0.9)',
            borderRadius: 3,
            padding: [2, 6],
          },
        },
      },
    ],
  };
});
</script>

<template>
  <article class="chart-card">
    <div class="trend-title-row">
      <h3 class="chart-title chart-title--inline">
        良率趨勢 ({{ GRANULARITY_LABEL[granularity] ?? granularity }})
      </h3>
      <button
        class="trend-download-btn"
        :disabled="!hasData"
        @click="downloadCSV"
        title="下載聚合資料 CSV"
      >
        <Download :size="13" />
        下載資料
      </button>
    </div>
    <div v-if="hasData" class="chart-body" role="img" aria-label="良率趨勢圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="chart-no-data">尚無趨勢資料</div>
  </article>
</template>
