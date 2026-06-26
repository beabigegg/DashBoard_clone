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

  const rotateLabel = items.length > 20 ? 40 : 0;

  return {
    legend: {
      top: 4,
      right: 16,
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 11 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: 'rgb(153, 153, 153)' } },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = Array.isArray(params) ? params : [];
        const idx = (p[0] as Record<string, unknown>)?.dataIndex ?? 0;
        const item = items[Number(idx)] || {};
        return [
          `<b>${(p[0] as Record<string, unknown>)?.name ?? ''}</b>`,
          `良率：<b>${Number(item.yield_pct ?? 0).toFixed(2)}%</b>`,
          `Input：${Number(item.transaction_qty ?? 0).toLocaleString()} pcs`,
          `報廢量：${Number(item.scrap_qty ?? 0).toLocaleString()} pcs`,
        ].join('<br/>');
      },
    },
    grid: { left: 56, right: 60, top: 36, bottom: rotateLabel > 0 ? 80 : 50 },
    xAxis: {
      type: 'category',
      data: items.map((i) => i.date_bucket),
      axisLabel: { fontSize: 11, rotate: rotateLabel },
      boundaryGap: true,
    },
    yAxis: [
      {
        type: 'value',
        min: yMin,
        max: yMax,
        axisLabel: { formatter: '{value}%', fontSize: 11 },
        splitLine: { lineStyle: { type: 'dashed', color: 'rgb(229, 231, 235)' } },
      },
      {
        type: 'value',
        axisLabel: {
          fontSize: 11,
          formatter: (v: number) => v >= 10000 ? `${(v / 1000).toFixed(0)}k` : String(v),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Input',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 18,
        itemStyle: { color: 'rgba(148, 163, 184, 0.55)' },
        data: inputVals,
      },
      {
        name: '良率%',
        type: 'line',
        yAxisIndex: 0,
        smooth: true,
        symbolSize: 5,
        symbol: 'circle',
        z: 3,
        areaStyle: { opacity: 0.12, color: 'rgb(37, 99, 235)' },
        lineStyle: { width: 2, color: 'rgb(37, 99, 235)' },
        itemStyle: { color: 'rgb(37, 99, 235)' },
        data: yieldVals,
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ yAxis: threshold }],
          lineStyle: { color: 'rgb(239, 68, 68)', type: 'dashed', width: 1.5 },
          label: {
            formatter: `門檻 ${threshold}%`,
            color: 'rgb(239, 68, 68)',
            fontSize: 11,
            position: 'end',
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
