<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components';

import { prepareParetoData } from '../../core/wip-derive.js';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const props = defineProps({
  type: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  items: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['drilldown']);

const paretoData = computed(() => prepareParetoData(props.items));
const hasData = computed(() => paretoData.value.items.length > 0);
const countLabel = computed(() => `${paretoData.value.items.length} 項`);

const headerClass = computed(() => {
  return props.type === 'quality' ? 'quality' : 'non-quality';
});

function formatNumber(value) {
  if (!value) {
    return '0';
  }
  return Number(value).toLocaleString('zh-TW');
}

function onReasonDrilldown(reason) {
  if (!reason || reason === '未知') {
    return;
  }
  emit('drilldown', reason);
}

const chartOption = computed(() => {
  const barColor = props.type === 'quality' ? 'rgb(239, 68, 68)' : 'rgb(249, 115, 22)';
  const lineColor = props.type === 'quality' ? 'rgb(153, 27, 27)' : 'rgb(154, 52, 18)';

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const reason = params?.[0]?.name || '';
        const qty = params?.[0]?.value || 0;
        const cumPct = params?.[1]?.value || 0;
        return `<strong>${reason}</strong><br/>QTY: ${formatNumber(qty)}<br/>累計: ${cumPct}%`;
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: paretoData.value.reasons,
      axisLabel: {
        rotate: 45,
        interval: 0,
        fontSize: 11,
        formatter(value) {
          return value.length > 8 ? `${value.slice(0, 8)}…` : value;
        },
      },
      axisTick: { alignWithLabel: true },
    },
    yAxis: [
      {
        type: 'value',
        name: 'QTY',
        position: 'left',
      },
      {
        type: 'value',
        name: '累計%',
        position: 'right',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: 'QTY',
        type: 'bar',
        barMaxWidth: 40,
        data: paretoData.value.qtys,
        itemStyle: { color: barColor },
      },
      {
        name: '累計%',
        type: 'line',
        yAxisIndex: 1,
        data: paretoData.value.cumulative,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: lineColor, width: 2 },
        itemStyle: { color: lineColor },
      },
    ],
  };
});

function handleChartClick(params) {
  if (params.componentType !== 'series' || params.seriesType !== 'bar') {
    return;
  }
  const reason = paretoData.value.reasons[params.dataIndex];
  onReasonDrilldown(reason);
}
</script>

<template>
  <section class="pareto-section">
    <div class="pareto-header" :class="headerClass">
      <div class="pareto-title">
        {{ title }}
        <span class="badge">{{ countLabel }}</span>
      </div>
    </div>

    <div class="pareto-body">
      <VChart
        v-if="hasData"
        class="pareto-chart"
        :option="chartOption"
        autoresize
        @click="handleChartClick"
      />
      <div v-else class="pareto-no-data">目前無資料</div>

      <table v-if="hasData" class="pareto-table">
        <thead>
          <tr>
            <th>Hold Reason</th>
            <th>Lots</th>
            <th>QTY</th>
            <th>累計%</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in paretoData.items" :key="`${item.reason || 'unknown'}-${index}`">
            <td>
              <a
                v-if="item.reason"
                href="#"
                class="reason-link"
                @click.prevent="onReasonDrilldown(item.reason)"
              >
                {{ item.reason }}
              </a>
              <span v-else>未知</span>
            </td>
            <td>{{ formatNumber(item.lots) }}</td>
            <td>{{ formatNumber(item.qty) }}</td>
            <td class="cumulative">{{ paretoData.cumulative[index] }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
