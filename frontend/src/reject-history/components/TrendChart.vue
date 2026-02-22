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
    grid: { left: 48, right: 24, top: 22, bottom: 70 },
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
        color: '#dc2626',
        data: items.map((item) => Number(item.REJECT_TOTAL_QTY || 0)),
        itemStyle: {
          color(params) {
            const date = items[params.dataIndex]?.bucket_date || '';
            return dateSet && !dateSet.has(date) ? '#f9a8a8' : '#dc2626';
          },
        },
        barMaxWidth: 28,
      },
      {
        name: '不扣帳報廢量',
        type: 'bar',
        color: '#0284c7',
        data: items.map((item) => Number(item.DEFECT_QTY || 0)),
        itemStyle: {
          color(params) {
            const date = items[params.dataIndex]?.bucket_date || '';
            return dateSet && !dateSet.has(date) ? '#a5d8f0' : '#0284c7';
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
    <article class="card">
      <div class="card-header"><div class="card-title">報廢量趨勢</div></div>
      <div class="card-body chart-wrap">
        <VChart :option="chartOption" autoresize @click="handleChartClick" @legendselectchanged="handleLegendChange" />
        <div v-if="!hasData && !loading" class="placeholder chart-empty">No data</div>
      </div>
    </article>
  </section>
</template>
