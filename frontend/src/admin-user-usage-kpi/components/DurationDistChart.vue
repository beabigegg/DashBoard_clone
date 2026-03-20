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
      data: items.map((d) => d.bucket),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', min: 0 },
    series: [
      {
        type: 'bar',
        data: items.map((d) => d.count),
        itemStyle: {
          color: '#2563eb',
          borderRadius: [3, 3, 0, 0],
        },
        barMaxWidth: 40,
      },
    ],
  };
});
</script>

<template>
  <div class="chart-container">
    <VChart v-if="data.length > 0" :option="chartOption" :autoresize="{ throttle: 100 }" style="height: 260px" />
    <div v-else class="empty-text">尚無時長資料</div>
  </div>
</template>
