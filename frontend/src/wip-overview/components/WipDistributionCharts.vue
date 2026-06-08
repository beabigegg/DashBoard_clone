<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, TooltipComponent, GridComponent]);

const COLOR_NORMAL = '#60a5fa';   // blue-400
const COLOR_SELECT = '#1d4ed8';   // blue-700
const COLOR_DIM    = '#cbd5e1';   // slate-300

interface MatrixData {
  workcenters?: string[];
  package_totals?: Record<string, unknown>;
  workcenter_totals?: Record<string, unknown>;
  matrix?: Record<string, Record<string, unknown>>;
  [key: string]: unknown;
}

const props = defineProps<{
  data?: MatrixData | null;
  selectedPackage?: string | null;
  selectedStation?: string | null;
}>();

const emit = defineEmits<{
  (e: 'select-package', pkg: string | null): void;
  (e: 'select-station', station: string | null): void;
}>();

// ── Package chart ────────────────────────────────────────────────────────
// Context: if a station is selected, show that station's package breakdown
//          otherwise show global package totals
const pkgChartData = computed(() => {
  const matrixData = props.data?.matrix || {};
  const station = props.selectedStation;

  let raw: Record<string, number>;
  if (station && matrixData[station]) {
    raw = Object.fromEntries(
      Object.entries(matrixData[station]).map(([k, v]) => [k, Number(v)]),
    );
  } else {
    raw = Object.fromEntries(
      Object.entries(props.data?.package_totals || {}).map(([k, v]) => [k, Number(v)]),
    );
  }

  return Object.entries(raw)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
});

const pkgChartHeight = computed(() => Math.max(220, pkgChartData.value.length * 26));

const pkgChartOption = computed(() => {
  const anySelected = !!props.selectedPackage;
  // Reverse so largest value is at top of horizontal bar
  const reversed = [...pkgChartData.value].reverse();
  const names = reversed.map(([k]) => k);
  const values = reversed.map(([k, v]) => ({
    value: v,
    itemStyle: {
      color: anySelected
        ? k === props.selectedPackage ? COLOR_SELECT : COLOR_DIM
        : COLOR_NORMAL,
    },
  }));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' as const },
      // TODO: type echarts callback
      formatter: (params: { name: string; value: number }[]) =>
        `<b>${params[0].name}</b>: ${params[0].value.toLocaleString('zh-TW')}`,
    },
    grid: { left: '2%', right: '16%', top: 4, bottom: 4, containLabel: true },
    xAxis: { type: 'value' as const, axisLabel: { fontSize: 10 } },
    yAxis: {
      type: 'category' as const,
      data: names,
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: 'bar' as const,
        data: values,
        barMaxWidth: 18,
        cursor: 'pointer',
        emphasis: { focus: 'self' as const },
        label: {
          show: true,
          position: 'right' as const,
          fontSize: 10,
          // TODO: type echarts callback
          formatter: (params: { value: number }) => params.value.toLocaleString('zh-TW'),
        },
      },
    ],
  };
});

// ── Station chart ────────────────────────────────────────────────────────
// Context: if a package is selected, show each station's qty for that package
//          otherwise show global workcenter totals
const stationChartData = computed(() => {
  const workcenters = props.data?.workcenters || [];
  const matrixData = props.data?.matrix || {};
  const pkg = props.selectedPackage;

  return workcenters.map((wc) => {
    const value = pkg
      ? Number(matrixData[wc]?.[pkg] || 0)
      : Number(props.data?.workcenter_totals?.[wc] || 0);
    return [wc, value] as [string, number];
  });
});

const stationChartHeight = computed(() => Math.max(220, stationChartData.value.length * 26));

const stationChartOption = computed(() => {
  const anySelected = !!props.selectedStation;
  // Reverse so first process step appears at top
  const reversed = [...stationChartData.value].reverse();
  const names = reversed.map(([k]) => k);
  const values = reversed.map(([k, v]) => ({
    value: v,
    itemStyle: {
      color: anySelected
        ? k === props.selectedStation ? COLOR_SELECT : COLOR_DIM
        : COLOR_NORMAL,
    },
  }));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' as const },
      // TODO: type echarts callback
      formatter: (params: { name: string; value: number }[]) =>
        `<b>${params[0].name}</b>: ${params[0].value.toLocaleString('zh-TW')}`,
    },
    grid: { left: '2%', right: '16%', top: 4, bottom: 4, containLabel: true },
    xAxis: { type: 'value' as const, axisLabel: { fontSize: 10 } },
    yAxis: {
      type: 'category' as const,
      data: names,
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: 'bar' as const,
        data: values,
        barMaxWidth: 18,
        cursor: 'pointer',
        emphasis: { focus: 'self' as const },
        label: {
          show: true,
          position: 'right' as const,
          fontSize: 10,
          // TODO: type echarts callback
          formatter: (params: { value: number }) => params.value.toLocaleString('zh-TW'),
        },
      },
    ],
  };
});

// ── Click handlers ───────────────────────────────────────────────────────

function onPkgClick(params: { name: string }) {
  emit('select-package', params.name === props.selectedPackage ? null : params.name);
}

function onStationClick(params: { name: string }) {
  emit('select-station', params.name === props.selectedStation ? null : params.name);
}

const hasData = computed(() =>
  pkgChartData.value.length > 0 || stationChartData.value.some(([, v]) => v > 0),
);

// Subtitle for context-awareness
const pkgChartTitle = computed(() =>
  props.selectedStation ? `Package WIP — ${props.selectedStation}` : 'WIP by Package (QTY)',
);

const stationChartTitle = computed(() =>
  props.selectedPackage ? `各站 WIP — ${props.selectedPackage}` : '各站 WIP 數量',
);
</script>

<template>
  <div v-if="hasData" class="wip-charts-row">
    <!-- Package distribution bar -->
    <section class="card ui-card wip-chart-card">
      <div class="card-header ui-card-header">
        <div class="card-title ui-card-title">{{ pkgChartTitle }}</div>
        <button
          v-if="selectedPackage"
          type="button"
          class="ui-btn ui-btn--ghost ui-btn--sm wip-chart-clear-btn"
          @click="emit('select-package', null)"
        >✕ 清除</button>
      </div>
      <div class="card-body ui-card-body wip-chart-body">
        <v-chart
          class="wip-echarts"
          :option="pkgChartOption"
          :style="{ height: `${pkgChartHeight}px` }"
          autoresize
          @click="onPkgClick"
        />
      </div>
    </section>

    <!-- Station distribution bar -->
    <section class="card ui-card wip-chart-card">
      <div class="card-header ui-card-header">
        <div class="card-title ui-card-title">{{ stationChartTitle }}</div>
        <button
          v-if="selectedStation"
          type="button"
          class="ui-btn ui-btn--ghost ui-btn--sm wip-chart-clear-btn"
          @click="emit('select-station', null)"
        >✕ 清除</button>
      </div>
      <div class="card-body ui-card-body wip-chart-body">
        <v-chart
          class="wip-echarts"
          :option="stationChartOption"
          :style="{ height: `${stationChartHeight}px` }"
          autoresize
          @click="onStationClick"
        />
      </div>
    </section>
  </div>
</template>
