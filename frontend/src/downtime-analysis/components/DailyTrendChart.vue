<script setup lang="ts">
import { computed } from 'vue';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import type { DailyTrendRow } from '../types';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent]);

const props = withDefaults(defineProps<{
  rows: DailyTrendRow[];
}>(), {
  rows: () => [],
});

const hasData = computed(() => props.rows.length > 0);

const chartOption = computed(() => {
  const dates = props.rows.map((r) => r.date);
  const udtData = props.rows.map((r) => r.udt_hours);
  const sdtData = props.rows.map((r) => r.sdt_hours);
  const egtData = props.rows.map((r) => r.egt_hours);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ seriesName: string; value: number; name: string }>;
        const date = p[0]?.name || '';
        const lines = p.map((item) => `${item.seriesName}: ${item.value.toFixed(1)}h`);
        return `${date}<br/>${lines.join('<br/>')}`;
      },
    },
    legend: { data: ['UDT', 'SDT', 'EGT'], top: 0, left: 'center' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '40px', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        rotate: dates.length > 14 ? 45 : 0,
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      name: '小時',
      nameTextStyle: { fontSize: 11 },
    },
    series: [
      { name: 'UDT', type: 'bar', stack: 'total', data: udtData },
      { name: 'SDT', type: 'bar', stack: 'total', data: sdtData },
      { name: 'EGT', type: 'bar', stack: 'total', data: egtData },
    ],
  };
});
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-title">每日停機趨勢</h3>
    <div v-if="!hasData" class="chart-empty" role="status" aria-label="無資料">
      暫無資料
    </div>
    <VChart
      v-else
      class="chart-container"
      :option="chartOption"
      autoresize
      role="img"
      aria-label="每日停機趨勢圖"
    />
  </div>
</template>
