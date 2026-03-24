<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const props = defineProps({
  data: { type: Array, default: () => [] },
});

const chartOption = computed(() => {
  const items = props.data || [];
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 16, bottom: 30 },
    xAxis: {
      type: 'category',
      data: items.map((d) => `${String(d.hour).padStart(2, '0')}:00`),
      axisLabel: { fontSize: 10, rotate: 45 },
    },
    yAxis: { type: 'value', min: 0 },
    series: [
      {
        type: 'bar',
        data: items.map((d) => d.count),
        itemStyle: {
          color: '#6366f1',
          borderRadius: [3, 3, 0, 0],
        },
        barMaxWidth: 24,
      },
    ],
  };
});
</script>

<template>
  <div class="chart-container">
    <VChart v-if="data.length > 0" class="chart-host" :option="chartOption" :autoresize="{ throttle: 100 }" />
    <div v-else class="empty-text">尚無時段資料</div>
  </div>
</template>

<style scoped>
.chart-host {
  height: 260px;
}
</style>
