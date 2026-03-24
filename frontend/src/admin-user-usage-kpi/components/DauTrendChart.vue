<script setup>
import { computed } from 'vue';

import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  data: { type: Array, default: () => [] },
});

const chartOption = computed(() => {
  const items = props.data || [];
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['不重複使用者', '登入次數'], bottom: 0 },
    grid: { left: 50, right: 20, top: 16, bottom: 40 },
    xAxis: {
      type: 'category',
      data: items.map((d) => d.date?.slice(5) || ''),
      axisLabel: { fontSize: 10, rotate: items.length > 15 ? 45 : 0 },
    },
    yAxis: { type: 'value', min: 0 },
    series: [
      {
        name: '不重複使用者',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        areaStyle: { opacity: 0.1 },
        itemStyle: { color: '#2563eb' },
        data: items.map((d) => d.unique_users),
      },
      {
        name: '登入次數',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        areaStyle: { opacity: 0.1 },
        itemStyle: { color: '#8b5cf6' },
        data: items.map((d) => d.sessions),
      },
    ],
  };
});
</script>

<template>
  <div class="chart-container">
    <VChart v-if="data.length > 0" class="chart-host" :option="chartOption" :autoresize="{ throttle: 100 }" />
    <div v-else class="empty-text">尚無趨勢資料</div>
  </div>
</template>

<style scoped>
.chart-host {
  height: 260px;
}
</style>
