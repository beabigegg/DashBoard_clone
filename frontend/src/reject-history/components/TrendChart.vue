<script setup>
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

const props = defineProps({
  items: { type: Array, default: () => [] },
  selectedDates: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(['date-click', 'legend-change']);

const hasData = computed(() => Array.isArray(props.items) && props.items.length > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const dateSet = props.selectedDates.length > 0 ? new Set(props.selectedDates) : null;
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['扣帳報廢量', '不扣帳報廢量'],
      bottom: 0,
    },
    grid: { left: 48, right: 24, top: 22, bottom: 70, containLabel: false },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.bucket_date || ''),
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter(value) {
          return Number(value || 0).toLocaleString('zh-TW');
        },
      },
    },
    series: [
      {
        name: '扣帳報廢量',
        type: 'bar',
        color: 'rgb(220, 38, 38)',
        data: items.map((item) => Number(item.REJECT_TOTAL_QTY || 0)),
        itemStyle: {
          color(params) {
            const date = items[params.dataIndex]?.bucket_date || '';
            return dateSet && !dateSet.has(date) ? 'rgb(249, 168, 168)' : 'rgb(220, 38, 38)';
          },
        },
        barMaxWidth: 28,
      },
      {
        name: '不扣帳報廢量',
        type: 'bar',
        color: 'rgb(2, 132, 199)',
        data: items.map((item) => Number(item.DEFECT_QTY || 0)),
        itemStyle: {
          color(params) {
            const date = items[params.dataIndex]?.bucket_date || '';
            return dateSet && !dateSet.has(date) ? 'rgb(165, 216, 240)' : 'rgb(2, 132, 199)';
          },
        },
        barMaxWidth: 28,
      },
    ],
  };
});

function handleChartClick(params) {
  if (params?.componentType !== 'series') {
    return;
  }
  const date = props.items?.[params.dataIndex]?.bucket_date;
  if (date) {
    emit('date-click', date);
  }
}

function handleLegendChange(params) {
  if (params?.selected) {
    emit('legend-change', { ...params.selected });
  }
}
</script>

<template>
  <section class="chart-grid">
    <article class="card ui-card">
      <div class="card-header ui-card-header"><div class="card-title ui-card-title">報廢量趨勢</div></div>
      <div class="card-body ui-card-body chart-wrap" role="img" aria-label="退貨數量趨勢圖">
        <VChart class="chart-canvas" :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" @legendselectchanged="handleLegendChange" />
        <div v-if="!hasData && !loading" class="placeholder chart-empty">No data</div>
      </div>
    </article>
  </section>
</template>
