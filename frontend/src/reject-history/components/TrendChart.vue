<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent]);

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
  granularity?: 'day' | 'week' | 'month';
}>();

const emit = defineEmits<{
  (e: 'date-click', date: string): void;
  (e: 'legend-change', selected: Record<string, boolean>): void;
  (e: 'granularity-change', value: 'day' | 'week' | 'month'): void;
}>();

const hasData = computed(() => Array.isArray(props.items) && (props.items?.length ?? 0) > 0);

const granularity = computed(() => props.granularity ?? 'day');

function xLabel(value: string): string {
  const parts = value.split('-');
  if (granularity.value === 'month' && parts.length >= 2) {
    return `${parts[0].slice(2)}/${parts[1]}`;
  }
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
  return value;
}

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
      axisLabel: {
        formatter: xLabel,
        rotate: items.length > 20 ? 45 : 0,
      },
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
        emphasis: {
          itemStyle: {
            shadowBlur: 18,
            shadowColor: 'rgba(220, 38, 38, 0.65)',
            borderColor: 'rgba(255, 255, 255, 0.7)',
            borderWidth: 1.5,
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
        emphasis: {
          itemStyle: {
            shadowBlur: 18,
            shadowColor: 'rgba(2, 132, 199, 0.65)',
            borderColor: 'rgba(255, 255, 255, 0.7)',
            borderWidth: 1.5,
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
      <div class="card-header ui-card-header rh-trend-header">
        <div class="card-title ui-card-title">報廢量趨勢</div>
        <div class="rh-gran-row" role="group" aria-label="時間粒度">
          <button
            type="button"
            :class="['rh-gran-btn', { active: granularity === 'day' }]"
            @click="$emit('granularity-change', 'day')"
          >日</button>
          <button
            type="button"
            :class="['rh-gran-btn', { active: granularity === 'week' }]"
            @click="$emit('granularity-change', 'week')"
          >週</button>
          <button
            type="button"
            :class="['rh-gran-btn', { active: granularity === 'month' }]"
            @click="$emit('granularity-change', 'month')"
          >月</button>
        </div>
      </div>
      <div class="card-body ui-card-body chart-wrap" role="img" aria-label="退貨數量趨勢圖">
        <VChart class="chart-canvas" :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" @legendselectchanged="handleLegendChange" />
        <div v-if="!hasData && !loading" class="placeholder chart-empty">No data</div>
      </div>
    </article>
  </section>
</template>
