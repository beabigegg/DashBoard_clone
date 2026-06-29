<script setup>
import { computed, ref } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent]);

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  data: {
    type: Array,
    default: () => [],
  },
  enableClick: {
    type: Boolean,
    default: false,
  },
  showCumulative: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(['bar-click']);

// Sort toggle: 'qty' (default) or 'rate'
const sortMode = ref('qty');

function toggleSort() {
  sortMode.value = sortMode.value === 'qty' ? 'rate' : 'qty';
}

const sortedData = computed(() => {
  if (!props.data || !props.data.length) return [];
  if (sortMode.value === 'qty') return props.data;

  // Re-sort by defect_rate and recalculate cumulative %
  const sorted = [...props.data].sort((a, b) => (b.defect_rate || 0) - (a.defect_rate || 0));
  const totalDefects = sorted.reduce((s, d) => s + (d.defect_qty || 0), 0);
  let cumsum = 0;
  return sorted.map((item) => {
    cumsum += item.defect_qty || 0;
    return {
      ...item,
      cumulative_pct: totalDefects > 0 ? Math.round((cumsum / totalDefects) * 1e4) / 100 : 0,
    };
  });
});

const totalLotCount = computed(() => {
  if (!props.data || !props.data.length) return 0;
  return props.data.reduce((s, d) => s + (d.lot_count || 0), 0);
});

const chartOption = computed(() => {
  const data = sortedData.value;
  if (!data.length) return null;

  const names = data.map((d) => d.name);
  const defectQty = data.map((d) => d.defect_qty);
  const cumulativePct = data.map((d) => d.cumulative_pct);
  const defectRate = data.map((d) => d.defect_rate);

  const legendItems = props.showCumulative ? ['不良數', '不良率', '累計占比'] : ['不良數', '不良率'];

  return {
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const idx = params[0]?.dataIndex;
        if (idx == null) return '';
        const item = data[idx];
        const total = totalLotCount.value;
        let html = `<b>${item.name}</b><br/>`;
        html += `不良數: ${(item.defect_qty || 0).toLocaleString()}<br/>`;
        html += `投入數: ${(item.input_qty || 0).toLocaleString()}<br/>`;
        html += `不良率: ${(item.defect_rate || 0).toFixed(2)}%<br/>`;
        if (item.lot_count != null) {
          const pct = total > 0 ? ((item.lot_count / total) * 100).toFixed(1) : '0.0';
          html += `關聯 LOT 數: ${item.lot_count} (${pct}%)<br/>`;
        }
        if (props.showCumulative) {
          html += `累計占比: ${(item.cumulative_pct || 0).toFixed(1)}%`;
        }
        return html;
      },
    },
    legend: {
      data: legendItems,
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      top: 40,
      right: props.showCumulative ? 60 : 40,
      bottom: 50,
      left: 50,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        rotate: names.length > 6 ? 30 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 80,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '不良數',
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11 },
      },
      {
        type: 'value',
        name: '%',
        ...(props.showCumulative ? { max: 100 } : {}),
        nameTextStyle: { fontSize: 11 },
        axisLabel: { fontSize: 11, formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: '不良數',
        type: 'bar',
        data: defectQty,
        itemStyle: { color: 'rgb(99, 102, 241)', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 40,
      },
      {
        name: '不良率',
        type: 'line',
        yAxisIndex: 1,
        data: defectRate,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: 'rgb(245, 158, 11)', width: 2 },
        itemStyle: { color: 'rgb(245, 158, 11)' },
      },
      ...(props.showCumulative ? [{
        name: '累計占比',
        type: 'line',
        yAxisIndex: 1,
        data: cumulativePct,
        symbol: 'diamond',
        symbolSize: 6,
        lineStyle: { color: 'rgb(239, 68, 68)', width: 2, type: 'dashed' },
        itemStyle: { color: 'rgb(239, 68, 68)' },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: true, position: 'insideEndTop', formatter: '80%', fontSize: 10, color: 'rgb(148, 163, 184)' },
          lineStyle: { color: 'rgb(148, 163, 184)', type: 'dotted', width: 1 },
          data: [{ yAxis: 80 }],
        },
      }] : []),
    ],
  };
});

function handleChartClick(params) {
  if (!props.enableClick) return;
  if (params.componentType === 'series' && params.seriesType === 'bar') {
    emit('bar-click', { name: params.name, dataIndex: params.dataIndex });
  }
}
</script>

<template>
  <div class="chart-card" role="img" aria-label="中段缺陷柏拉圖">
    <div class="chart-header">
      <h3 class="chart-title">{{ title }}</h3>
      <button
        type="button"
        class="sort-toggle"
        :title="sortMode === 'qty' ? '切換為依不良率排序' : '切換為依不良數排序'"
        @click="toggleSort"
      >
        {{ sortMode === 'qty' ? '依數量' : '依比率' }}
      </button>
      <slot name="header-extra" />
    </div>
    <VChart
      v-if="chartOption"
      class="chart-canvas"
      :option="chartOption"
      :autoresize="{ throttle: 100 }"
      @click="handleChartClick"
    />
    <div v-else class="chart-empty">暫無資料</div>
  </div>
</template>

<style scoped>
.sort-toggle {
  font-size: 11px;
  padding: theme('spacing.token.p1') theme('spacing.token.p6');
  border: 1px solid var(--border-color, theme('colors.token.hd1d5db'));
  border-radius: 4px;
  background: var(--bg-secondary, theme('colors.token.hf9fafb'));
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  cursor: pointer;
  margin-left: theme('spacing.token.p6');
  white-space: nowrap;
}
.sort-toggle:hover {
  background: var(--bg-tertiary, theme('colors.token.hf3f4f6'));
}
</style>
