<script setup>
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const DIMENSION_OPTIONS = [
  { value: 'reason', label: '不良原因' },
  { value: 'package', label: 'PACKAGE' },
  { value: 'type', label: 'TYPE' },
  { value: 'workflow', label: 'WORKFLOW' },
  { value: 'workcenter', label: '站點' },
  { value: 'equipment', label: '機台' },
];
const DISPLAY_SCOPE_TOP20_DIMENSIONS = new Set(['type', 'workflow', 'equipment']);

const props = defineProps({
  items: { type: Array, default: () => [] },
  selectedValues: { type: Array, default: () => [] },
  selectedDates: { type: Array, default: () => [] },
  metricLabel: { type: String, default: '報廢量' },
  loading: { type: Boolean, default: false },
  dimension: { type: String, default: 'reason' },
  showDimensionSelector: { type: Boolean, default: false },
  displayScope: { type: String, default: 'all' },
});

const emit = defineEmits(['item-toggle', 'dimension-change', 'display-scope-change']);

const hasData = computed(() => Array.isArray(props.items) && props.items.length > 0);
const selectedValueSet = computed(() => new Set((props.selectedValues || []).map((item) => String(item || '').trim())));
const showDisplayScopeSelector = computed(
  () => DISPLAY_SCOPE_TOP20_DIMENSIONS.has(props.dimension),
);

const dimensionLabel = computed(() => {
  const opt = DIMENSION_OPTIONS.find((o) => o.value === props.dimension);
  return opt ? opt.label : '報廢原因';
});

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
  const items = props.items || [];
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
      bottom: 96,
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.reason || '(未填寫)'),
      axisLabel: {
        interval: 0,
        rotate: items.length > 6 ? 35 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 100,
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
  const itemValue = props.items?.[params.dataIndex]?.reason;
  if (itemValue) {
    emit('item-toggle', itemValue);
  }
}
</script>

<template>
  <section class="card">
    <div class="card-header pareto-header">
      <div class="card-title">
        {{ metricLabel }} vs {{ dimensionLabel }}（Pareto）
        <span v-for="d in selectedDates" :key="d" class="pareto-date-badge">{{ d }}</span>
      </div>
      <div class="pareto-controls">
        <select
          v-if="showDimensionSelector"
          class="dimension-select"
          :value="dimension"
          @change="emit('dimension-change', $event.target.value)"
        >
          <option v-for="opt in DIMENSION_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select
          v-if="showDisplayScopeSelector"
          class="dimension-select pareto-scope-select"
          :value="displayScope"
          @change="emit('display-scope-change', $event.target.value)"
        >
          <option value="all">全部顯示</option>
          <option value="top20">只顯示 TOP 20</option>
        </select>
      </div>
    </div>
    <div class="card-body pareto-layout">
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
              v-for="item in items"
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
            <tr v-if="!items || items.length === 0">
              <td colspan="4" class="placeholder">No data</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
