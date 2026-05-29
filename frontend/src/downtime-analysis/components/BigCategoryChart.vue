<script setup lang="ts">
import { computed } from 'vue';
import { PieChart } from 'echarts/charts';
import { LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import type { BigCategoryRow } from '../types';

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent]);

const props = withDefaults(defineProps<{
  rows: BigCategoryRow[];
}>(), {
  rows: () => [],
});

const hasData = computed(() => props.rows.length > 0);

const chartOption = computed(() => {
  const pieData = props.rows.map((r) => ({
    name: r.category,
    value: r.hours,
  }));

  return {
    tooltip: {
      trigger: 'item',
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as { name: string; value: number; percent: number };
        return `${p.name}<br/>時數: ${p.value.toFixed(1)}h<br/>佔比: ${p.percent.toFixed(1)}%`;
      },
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { fontSize: 11 },
    },
    series: [
      {
        name: '停機類別',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false, position: 'center' },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold',
            // TODO: type echarts callback
            formatter(params: unknown) {
              const p = params as { name: string; percent: number };
              return `${p.name}\n${p.percent.toFixed(1)}%`;
            },
          },
        },
        labelLine: { show: false },
        data: pieData,
      },
    ],
  };
});
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-title">停機類別分佈</h3>
    <div v-if="!hasData" class="chart-empty" role="status" aria-label="無資料">
      暫無資料
    </div>
    <VChart
      v-else
      class="chart-container"
      :option="chartOption"
      autoresize
      role="img"
      aria-label="停機類別分佈圖"
    />
  </div>
</template>
