<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart, HeatmapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
]);

/**
 * Centralised ECharts color palette.
 * All hex values for chart rendering are defined here (governance exception).
 */
const CHART_PALETTE = {
  bar: '#0080C8',
  barSecondary: '#00A3E0',
  line: '#006BA8',
  lineSecondary: '#00A3E0',
  cumLine: '#ef4444',
  heatmapMin: '#e6f4fb',
  heatmapMax: '#004A76',
  axisLabel: '#64748b',
  axisTick: '#e2e8f0',
  tooltipBg: '#1f2937',
  kpiPositive: '#22c55e',
  kpiNegative: '#ef4444',
};

const props = defineProps({
  chartData: {
    type: [Object, Array],
    default: null,
  },
  queryUsed: {
    type: String,
    default: null,
  },
});

const chartType = computed(() => {
  const q = (props.queryUsed || '').toLowerCase();
  if (q.endsWith('_pareto')) return 'pareto';
  if (q.endsWith('_trend')) return 'trend';
  if (q.endsWith('_summary') || q === 'wip_summary') return 'kpi';
  if (q.endsWith('_matrix')) return 'heatmap';
  if (q.endsWith('_list') || q.endsWith('_lot_list')) return 'table';
  // Auto-detect from data shape
  return detectFromData(props.chartData);
});

function detectFromData(data) {
  if (!data) return 'empty';
  if (Array.isArray(data)) {
    if (data.length === 0) return 'empty';
    const first = data[0];
    if (first && typeof first === 'object') {
      const keys = Object.keys(first);
      if (keys.some((k) => /date|time|day/i.test(k))) return 'trend';
      return 'table';
    }
  }
  if (typeof data === 'object' && !Array.isArray(data)) {
    if (data.categories && data.values) return 'pareto';
    if (data.series || data.xAxis) return 'trend';
    if (data.items && Array.isArray(data.items)) return 'kpi';
    return 'kpi';
  }
  return 'empty';
}

const isEmpty = computed(() => {
  if (!props.chartData) return true;
  if (Array.isArray(props.chartData) && props.chartData.length === 0) return true;
  return false;
});

const paretoOption = computed(() => {
  const data = props.chartData;
  if (!data) return {};

  const categories = data.categories || (Array.isArray(data) ? data.map((d) => d.name || d.label || '') : []);
  const values = data.values || (Array.isArray(data) ? data.map((d) => d.value || d.qty || 0) : []);

  // Compute cumulative percentages
  const total = values.reduce((s, v) => s + v, 0);
  const cumPcts = [];
  let cum = 0;
  for (const v of values) {
    cum += v;
    cumPcts.push(total > 0 ? Math.round((cum / total) * 1000) / 10 : 0);
  }

  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '12%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: {
        rotate: 35,
        fontSize: 10,
        color: CHART_PALETTE.axisLabel,
        formatter: (v) => (v.length > 6 ? v.slice(0, 6) + '...' : v),
      },
    },
    yAxis: [
      { type: 'value', axisLabel: { fontSize: 10, color: CHART_PALETTE.axisLabel } },
      {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { fontSize: 10, formatter: '{value}%', color: CHART_PALETTE.axisLabel },
      },
    ],
    series: [
      {
        type: 'bar',
        data: values,
        barMaxWidth: 24,
        itemStyle: { color: CHART_PALETTE.bar },
      },
      {
        type: 'line',
        yAxisIndex: 1,
        data: cumPcts,
        smooth: true,
        lineStyle: { color: CHART_PALETTE.cumLine, width: 2 },
        itemStyle: { color: CHART_PALETTE.cumLine },
        symbol: 'circle',
        symbolSize: 4,
      },
    ],
  };
});

const trendOption = computed(() => {
  const data = props.chartData;
  if (!data) return {};

  // Expect either { xAxis: [...], series: [...] } or array of objects with date field
  let xData = [];
  let seriesList = [];

  if (Array.isArray(data)) {
    const keys = Object.keys(data[0] || {});
    const timeKey = keys.find((k) => /date|time|day/i.test(k)) || keys[0];
    const valueKeys = keys.filter((k) => k !== timeKey);
    xData = data.map((d) => d[timeKey]);
    seriesList = valueKeys.map((k, i) => ({
      type: 'line',
      name: k,
      data: data.map((d) => d[k]),
      smooth: true,
      lineStyle: { color: i === 0 ? CHART_PALETTE.line : CHART_PALETTE.lineSecondary, width: 2 },
      itemStyle: { color: i === 0 ? CHART_PALETTE.line : CHART_PALETTE.lineSecondary },
      symbol: 'circle',
      symbolSize: 3,
    }));
  } else {
    xData = data.xAxis || data.categories || [];
    const rawSeries = data.series || [];
    seriesList = rawSeries.map((s, i) => ({
      type: 'line',
      name: s.name || `Series ${i + 1}`,
      data: s.data || [],
      smooth: true,
      lineStyle: { color: i === 0 ? CHART_PALETTE.line : CHART_PALETTE.lineSecondary, width: 2 },
      itemStyle: { color: i === 0 ? CHART_PALETTE.line : CHART_PALETTE.lineSecondary },
      symbol: 'circle',
      symbolSize: 3,
    }));
  }

  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '3%', bottom: '8%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { fontSize: 10, color: CHART_PALETTE.axisLabel },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, color: CHART_PALETTE.axisLabel },
    },
    series: seriesList,
  };
});

const heatmapOption = computed(() => {
  const data = props.chartData;
  if (!data) return {};

  const xLabels = data.xAxis || data.columns || [];
  const yLabels = data.yAxis || data.rows || [];
  const points = data.data || data.values || [];

  let max = 1;
  for (const p of points) {
    const v = Array.isArray(p) ? p[2] : p.value;
    if (v > max) max = v;
  }

  return {
    tooltip: { trigger: 'item' },
    grid: { left: '15%', right: '6%', bottom: '15%', top: '5%' },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisLabel: { fontSize: 9, rotate: 30, color: CHART_PALETTE.axisLabel },
    },
    yAxis: {
      type: 'category',
      data: yLabels,
      axisLabel: { fontSize: 9, color: CHART_PALETTE.axisLabel },
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      show: false,
      inRange: { color: [CHART_PALETTE.heatmapMin, CHART_PALETTE.heatmapMax] },
    },
    series: [
      {
        type: 'heatmap',
        data: points,
        emphasis: { itemStyle: { shadowBlur: 5 } },
      },
    ],
  };
});

const tableRows = computed(() => {
  if (!props.chartData) return [];
  const data = Array.isArray(props.chartData) ? props.chartData : props.chartData.items || [];
  return data.slice(0, 10);
});

const tableColumns = computed(() => {
  if (tableRows.value.length === 0) return [];
  return Object.keys(tableRows.value[0]);
});

const kpiItems = computed(() => {
  if (!props.chartData) return [];
  if (Array.isArray(props.chartData)) return props.chartData;
  if (props.chartData.items) return props.chartData.items;
  // Single KPI object
  return Object.entries(props.chartData).map(([k, v]) => ({ label: k, value: v }));
});
</script>

<template>
  <div class="ai-chart-renderer">
    <!-- Empty state -->
    <div v-if="isEmpty" class="ai-chart-empty">
      暫無資料
    </div>

    <!-- Pareto (bar + cumulative line) -->
    <VChart
      v-else-if="chartType === 'pareto'"
      class="ai-chart-canvas ai-chart-canvas--bar"
      :option="paretoOption"
      autoresize
    />

    <!-- Trend (line chart) -->
    <VChart
      v-else-if="chartType === 'trend'"
      class="ai-chart-canvas ai-chart-canvas--bar"
      :option="trendOption"
      autoresize
    />

    <!-- Heatmap -->
    <VChart
      v-else-if="chartType === 'heatmap'"
      class="ai-chart-canvas ai-chart-canvas--heatmap"
      :option="heatmapOption"
      autoresize
    />

    <!-- KPI cards -->
    <div v-else-if="chartType === 'kpi'" class="ai-kpi-grid">
      <div
        v-for="(item, idx) in kpiItems"
        :key="idx"
        class="ai-kpi-card"
      >
        <span class="ai-kpi-label">{{ item.label || item.name || item.key }}</span>
        <span class="ai-kpi-value">{{ item.value ?? item.count ?? '-' }}</span>
      </div>
    </div>

    <!-- Table -->
    <div v-else-if="chartType === 'table'" class="ai-table-wrap">
      <table class="ai-compact-table">
        <thead>
          <tr>
            <th v-for="col in tableColumns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in tableRows" :key="idx">
            <td v-for="col in tableColumns" :key="col">{{ row[col] ?? '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ai-chart-renderer {
  width: 100%;
}

.ai-chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: theme('colors.text.muted');
  font-size: 13px;
}

.ai-chart-canvas {
  width: 100%;
}

.ai-chart-canvas--bar {
  height: 200px;
}

.ai-chart-canvas--heatmap {
  height: 160px;
}

.ai-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: theme('spacing.token.p8');
}

.ai-kpi-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: theme('spacing.token.p8');
  background: theme('colors.surface.muted');
  border-radius: theme('borderRadius.card');
  border: 1px solid theme('colors.stroke.soft');
}

.ai-kpi-label {
  font-size: 11px;
  color: theme('colors.text.secondary');
  text-align: center;
  word-break: break-word;
}

.ai-kpi-value {
  font-size: 18px;
  font-weight: 700;
  color: theme('colors.text.primary');
  margin-top: theme('spacing.token.p2');
}

.ai-table-wrap {
  max-height: 260px;
  overflow: auto;
  border: 1px solid theme('colors.stroke.soft');
  border-radius: theme('borderRadius.card');
}

.ai-compact-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ai-compact-table th {
  position: sticky;
  top: 0;
  background: theme('colors.surface.muted');
  color: theme('colors.text.secondary');
  font-weight: 600;
  padding: theme('spacing.token.p4') theme('spacing.token.p6');
  text-align: left;
  border-bottom: 1px solid theme('colors.stroke.soft');
  white-space: nowrap;
}

.ai-compact-table td {
  padding: theme('spacing.token.p3') theme('spacing.token.p6');
  border-bottom: 1px solid theme('colors.stroke.soft');
  white-space: nowrap;
}

.ai-compact-table tbody tr:hover {
  background: theme('colors.surface.hover');
}
</style>
