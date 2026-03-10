<script setup>
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const DISPLAY_SCOPE_TOP20_DIMENSIONS = new Set(['type', 'workflow', 'equipment']);

const props = defineProps({
  items: { type: Array, default: () => [] },
  selectedValues: { type: Array, default: () => [] },
  selectedDates: { type: Array, default: () => [] },
  metricLabel: { type: String, default: '報廢量' },
  loading: { type: Boolean, default: false },
  dimension: { type: String, default: 'reason' },
  dimensionLabel: { type: String, default: 'Pareto' },
  displayScope: { type: String, default: 'all' },
});

const emit = defineEmits(['item-toggle']);

const selectedValueSet = computed(
  () => new Set((props.selectedValues || []).map((item) => String(item || '').trim()),
));

const displayItems = computed(() => {
  const items = Array.isArray(props.items) ? props.items : [];
  if (
    props.displayScope === 'top20'
    && DISPLAY_SCOPE_TOP20_DIMENSIONS.has(props.dimension)
  ) {
    return items.slice(0, 20);
  }
  return items;
});

const hasData = computed(() => displayItems.value.length > 0);

const showTop20Badge = computed(
  () => props.displayScope === 'top20' && DISPLAY_SCOPE_TOP20_DIMENSIONS.has(props.dimension),
);

function isSelected(value) {
  return selectedValueSet.value.has(String(value || '').trim());
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

const chartOption = computed(() => {
  const items = displayItems.value;
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        const idx = Number(params?.[0]?.dataIndex || 0);
        const item = items[idx] || {};
        return [
          `<b>${item.reason || '(未填寫)'}</b>`,
          `${props.metricLabel}: ${formatNumber(item.metric_value || 0)}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
          `累計: ${Number(item.cumPct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    legend: {
      data: [props.metricLabel, '累積%'],
      bottom: 0,
    },
    grid: {
      left: 52,
      right: 52,
      top: 20,
      bottom: items.length > 10 ? 110 : 96,
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.reason || '(未填寫)'),
      axisLabel: {
        interval: 0,
        rotate: items.length > 10 ? 55 : items.length > 5 ? 35 : 0,
        fontSize: items.length > 15 ? 9 : items.length > 8 ? 10 : 11,
        overflow: 'truncate',
        width: items.length > 10 ? 60 : 80,
        hideOverlap: true,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '量',
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: props.metricLabel,
        type: 'bar',
        data: items.map((item) => Number(item.metric_value || 0)),
        barMaxWidth: 34,
        itemStyle: {
          color(params) {
            const reason = items[params.dataIndex]?.reason || '';
            return isSelected(reason) ? '#b91c1c' : '#2563eb';
          },
          borderRadius: [4, 4, 0, 0],
        },
      },
      {
        name: '累積%',
        type: 'line',
        yAxisIndex: 1,
        data: items.map((item) => Number(item.cumPct || 0)),
        lineStyle: { color: '#f59e0b', width: 2 },
        itemStyle: { color: '#f59e0b' },
        symbolSize: 6,
      },
    ],
  };
});

function handleChartClick(params) {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const itemValue = displayItems.value?.[params.dataIndex]?.reason;
  if (itemValue) {
    emit('item-toggle', itemValue);
  }
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header pareto-header">
      <div class="card-title ui-card-title">
        {{ metricLabel }} vs {{ dimensionLabel }}（Pareto）
        <span v-if="showTop20Badge" class="pareto-date-badge">TOP 20</span>
        <span v-for="d in selectedDates" :key="d" class="pareto-date-badge">{{ d }}</span>
      </div>
    </div>
    <div class="card-body ui-card-body pareto-layout">
      <div class="pareto-chart-wrap">
        <VChart :option="chartOption" autoresize @click="handleChartClick" />
        <div v-if="!hasData && !loading" class="placeholder chart-empty">No data</div>
      </div>
      <div class="pareto-table-wrap">
        <table class="detail-table pareto-table">
          <thead>
            <tr>
              <th>{{ dimensionLabel }}</th>
              <th>{{ metricLabel }}</th>
              <th>占比</th>
              <th>累積</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in displayItems"
              :key="item.reason"
              :class="{ active: isSelected(item.reason) }"
            >
              <td>
                <button class="reason-link" type="button" @click="$emit('item-toggle', item.reason)">
                  {{ item.reason }}
                </button>
              </td>
              <td>{{ formatNumber(item.metric_value) }}</td>
              <td>{{ formatPct(item.pct) }}</td>
              <td>{{ formatPct(item.cumPct) }}</td>
            </tr>
            <tr v-if="displayItems.length === 0">
              <td colspan="4" class="placeholder">No data</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
