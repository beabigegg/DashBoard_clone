<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  activeRange: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['toggle']);

const hasData = computed(() => (props.items || []).length > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const labels = items.map((item) => item.range || '-');
  const qtys = items.map((item) => Number(item.qty || 0));
  const pcts = items.map((item) => Number(item.pct || 0));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const index = Number(params?.[0]?.dataIndex || 0);
        const item = items[index] || {};
        return [
          `<b>${item.range || '-'}</b>`,
          `數量: ${Number(item.qty || 0).toLocaleString('zh-TW')}`,
          `Lot 數: ${Number(item.count || 0).toLocaleString('zh-TW')}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    grid: {
      left: 8,
      right: 8,
      top: 14,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      axisLabel: {
        formatter: (value) => Number(value || 0).toLocaleString('zh-TW'),
      },
    },
    yAxis: {
      type: 'category',
      data: labels,
    },
    series: [
      {
        type: 'bar',
        data: qtys,
        barMaxWidth: 26,
        itemStyle: {
          color(params) {
            const range = labels[params.dataIndex] || '';
            return range === props.activeRange ? 'rgb(220, 38, 38)' : 'rgb(124, 58, 237)';
          },
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: 'right',
          formatter(params) {
            const pct = Number(pcts[params.dataIndex] || 0).toFixed(1);
            const qty = Number(params.value || 0).toLocaleString('zh-TW');
            return `${qty} (${pct}%)`;
          },
          fontSize: 11,
        },
      },
    ],
  };
});

function handleChartClick(params) {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const selected = props.items?.[params.dataIndex]?.range;
  if (!selected) {
    return;
  }
  emit('toggle', selected);
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">Hold Duration Distribution</div>
    </div>
    <div class="card-body ui-card-body">
      <div v-if="hasData" class="duration-chart-wrap">
        <VChart :option="chartOption" autoresize @click="handleChartClick" />
      </div>
      <div v-else class="placeholder">No data</div>
    </div>
  </section>
</template>
