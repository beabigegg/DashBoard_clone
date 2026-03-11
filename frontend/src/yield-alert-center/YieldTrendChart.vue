<script setup>
import { computed } from 'vue';

import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, MarkLineComponent]);

const GRANULARITY_LABEL = { day: '日', week: '週', month: '月', year: '年' };

const props = defineProps({
  trend: { type: Array, default: () => [] },
  riskThreshold: { type: Number, default: 98 },
  granularity: { type: String, default: 'day' },
});

const hasData = computed(() => props.trend.length > 0);

const chartOption = computed(() => {
  const items = props.trend || [];
  const threshold = Number(props.riskThreshold || 98);

  const yieldVals = items.map((i) => Number(i.yield_pct ?? 0));
  const dataMin = yieldVals.length ? Math.min(...yieldVals) : 0;
  const dataMax = yieldVals.length ? Math.max(...yieldVals) : 100;
  const yMin = Math.max(0, Math.floor(Math.min(dataMin, threshold) - 2));
  const yMax = Math.ceil(Math.max(dataMax, 100) + 1);

  const rotateLabel = items.length > 20 ? 40 : 0;

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: 'rgb(153, 153, 153)' } },
      formatter(params) {
        const idx = params[0]?.dataIndex ?? 0;
        const item = items[idx] || {};
        return [
          `<b>${params[0]?.name ?? ''}</b>`,
          `良率：<b>${Number(item.yield_pct ?? 0).toFixed(2)}%</b>`,
          `移轉量：${Number(item.transaction_qty ?? 0).toLocaleString()}`,
          `報廢量：${Number(item.scrap_qty ?? 0).toLocaleString()}`,
        ].join('<br/>');
      },
    },
    grid: { left: 52, right: 24, top: 24, bottom: rotateLabel > 0 ? 80 : 50 },
    xAxis: {
      type: 'category',
      data: items.map((i) => i.date_bucket),
      axisLabel: { fontSize: 11, rotate: rotateLabel },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      axisLabel: { formatter: '{value}%', fontSize: 11 },
      splitLine: { lineStyle: { type: 'dashed', color: 'rgb(229, 231, 235)' } },
    },
    series: [
      {
        name: '良率%',
        type: 'line',
        smooth: true,
        symbolSize: 5,
        symbol: 'circle',
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
    <h3 class="chart-title">
      良率趨勢 ({{ GRANULARITY_LABEL[granularity] ?? granularity }})
    </h3>
    <div v-if="hasData" class="chart-body">
      <VChart :option="chartOption" autoresize />
    </div>
    <div v-else class="chart-no-data">尚無趨勢資料</div>
  </article>
</template>
