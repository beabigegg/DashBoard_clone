<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

interface TrendItem {
  bucket_date: string;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  REJECT_RATE_PCT?: number;
  DEFECT_RATE_PCT?: number;
}

const props = defineProps<{
  items?: TrendItem[];
  selectedDates?: string[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'date-click', date: string): void;
  (e: 'legend-change', selected: Record<string, boolean>): void;
}>();

const hasData = computed(() => Array.isArray(props.items) && (props.items?.length ?? 0) > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const selectedDates = props.selectedDates ?? [];
  const dateSet: Set<string> | null = selectedDates.length > 0 ? new Set(selectedDates) : null;
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
      data: items.map((item: TrendItem) => item.bucket_date || ''),
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter(value: unknown) {
          return Number(value || 0).toLocaleString('zh-TW');
        },
      },
    },
    series: [
      {
        name: '扣帳報廢量',
        type: 'bar',
        color: 'rgb(220, 38, 38)',
        data: items.map((item: TrendItem) => Number(item.REJECT_TOTAL_QTY || 0)),
        itemStyle: {
          // TODO: type — echarts itemStyle color callback params is typed via echarts internals
          color(params: { dataIndex: number }) {
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
        data: items.map((item: TrendItem) => Number(item.DEFECT_QTY || 0)),
        itemStyle: {
          // TODO: type — echarts itemStyle color callback params is typed via echarts internals
          color(params: { dataIndex: number }) {
            const date = items[params.dataIndex]?.bucket_date || '';
            return dateSet && !dateSet.has(date) ? 'rgb(165, 216, 240)' : 'rgb(2, 132, 199)';
          },
        },
        barMaxWidth: 28,
      },
    ],
  };
});

function handleChartClick(params: { componentType?: string; dataIndex: number }): void {
  if (params?.componentType !== 'series') {
    return;
  }
  const date = props.items?.[params.dataIndex]?.bucket_date;
  if (date) {
    emit('date-click', date);
  }
}

function handleLegendChange(params: { selected?: Record<string, boolean> }): void {
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
