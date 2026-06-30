<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { HeatmapChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  crosstab: {
    type: Object,
    default: () => null,
  },
  // Optional cross-filter selection: { frontReason: string|null, downstreamGroup: string|null }
  selection: {
    type: Object,
    default: () => ({ frontReason: null, downstreamGroup: null }),
  },
});

const emit = defineEmits(['cell-click', 'clear-selection']);

const hasData = computed(() => {
  const c = props.crosstab;
  return c && Array.isArray(c.cells) && c.cells.length > 0;
});

const chartOption = computed(() => {
  if (!hasData.value) return null;

  const { loss_reasons = [], workcenter_groups = [], cells = [] } = props.crosstab;

  // Build a flat matrix for the heatmap: [xIdx, yIdx, reject_rate_pct]
  // x-axis = loss_reasons, y-axis = workcenter_groups
  const matrixData = cells.map((cell) => {
    const x = loss_reasons.indexOf(cell.loss_reason);
    const y = workcenter_groups.indexOf(cell.workcenter_group);
    const pct = Math.round((cell.reject_rate || 0) * 10000) / 100; // 0..1 → %
    return [x, y, pct, cell.reject_qty];
  });

  return {
    animationDuration: 300,
    tooltip: {
      position: 'top',
      formatter(params) {
        const [xIdx, yIdx, pct, qty] = params.data;
        const reason = loss_reasons[xIdx] || '';
        const group = workcenter_groups[yIdx] || '';
        return `${reason}<br/>${group}<br/>不良率: ${pct.toFixed(2)}%<br/>不良數: ${(qty || 0).toLocaleString()}`;
      },
    },
    grid: {
      top: '4%',
      right: '12%',
      bottom: '18%',
      left: '2%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: loss_reasons,
      axisLabel: {
        rotate: loss_reasons.length > 5 ? 30 : 0,
        fontSize: 10,
        overflow: 'truncate',
        width: 80,
      },
      name: '前段不良原因',
      nameLocation: 'middle',
      nameGap: 38,
      nameTextStyle: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: workcenter_groups,
      axisLabel: { fontSize: 10 },
      name: '下游站點',
      nameLocation: 'middle',
      nameGap: 70,
      nameTextStyle: { fontSize: 11 },
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'vertical',
      right: '0%',
      top: '5%',
      bottom: '18%',
      text: ['高', '低'],
      inRange: { color: ['rgb(240,249,255)', 'rgb(239,68,68)'] },
      textStyle: { fontSize: 10 },
      formatter(v) { return `${v.toFixed(0)}%`; },
    },
    series: [
      {
        type: 'heatmap',
        data: matrixData.map(([x, y, pct, qty]) => [x, y, pct, qty]),
        label: {
          show: loss_reasons.length <= 8 && workcenter_groups.length <= 8,
          fontSize: 9,
          formatter(p) { return `${p.data[2].toFixed(1)}%`; },
        },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.2)' } },
      },
    ],
  };
});

function handleChartClick(params) {
  if (params.componentType !== 'series') return;
  const c = props.crosstab;
  if (!c) return;
  const [xIdx, yIdx] = params.data;
  emit('cell-click', {
    frontReason: c.loss_reasons[xIdx] || null,
    downstreamGroup: c.workcenter_groups[yIdx] || null,
  });
}
</script>

<template>
  <div class="forward-heatmap-chart">
    <div class="chart-header">
      <h3 class="chart-title">不良率熱圖 (前段原因 × 下游站點)</h3>
      <div class="chart-header-actions">
        <slot name="chart-toggle" />
        <button
          v-if="selection && (selection.frontReason || selection.downstreamGroup)"
          type="button"
          class="clear-selection-btn"
          aria-label="清除選取"
          data-testid="heatmap-clear-selection"
          @click="$emit('clear-selection')"
        >
          清除選取
        </button>
      </div>
    </div>
    <div
      v-if="chartOption"
      role="img"
      aria-label="前段不良原因與下游站點不良率熱圖"
    >
      <VChart
        class="heatmap-canvas"
        :option="chartOption"
        :autoresize="{ throttle: 100 }"
        data-testid="heatmap-chart"
        @click="handleChartClick"
      />
    </div>
    <div v-else class="chart-empty">暫無資料</div>
  </div>
</template>

<style scoped>
.forward-heatmap-chart {
  display: flex;
  flex-direction: column;
}
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.chart-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.heatmap-canvas {
  width: 100%;
  height: 380px;
}
.chart-empty {
  height: 380px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-tertiary, theme('colors.text.muted'));
}
</style>
