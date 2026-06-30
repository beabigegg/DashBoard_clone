<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { SankeyChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';

use([CanvasRenderer, SankeyChart, TooltipComponent]);

// ECharts Sankey palette — named constants per css-contract Rule 6.2/6.3
const SANKEY_SOURCE_COLOR = 'rgb(99, 102, 241)';   // indigo-500 (detection loss-reason)
const SANKEY_TARGET_COLOR = 'rgb(34, 197, 94)';    // green-500  (downstream workcenter)
const SANKEY_LINK_COLOR   = 'rgba(99, 102, 241, 0.22)';

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

const emit = defineEmits(['node-click', 'clear-selection']);

const hasData = computed(() => {
  const c = props.crosstab;
  return c && Array.isArray(c.cells) && c.cells.length > 0
    && Array.isArray(c.loss_reasons) && c.loss_reasons.length > 0;
});

const chartOption = computed(() => {
  if (!hasData.value) return null;

  const { loss_reasons, workcenter_groups, cells } = props.crosstab;

  // Build nodes: source nodes are prefixed to avoid collision with same-name targets
  const sourceNodes = loss_reasons.map((r) => ({
    name: `[前段] ${r}`,
    itemStyle: { color: SANKEY_SOURCE_COLOR },
  }));
  const targetNodes = (workcenter_groups || []).map((g) => ({
    name: `[下游] ${g}`,
    itemStyle: { color: SANKEY_TARGET_COLOR },
  }));

  // Selection highlight: dim non-selected if a selection is active
  const sel = props.selection || {};
  const hasSelection = sel.frontReason || sel.downstreamGroup;

  if (hasSelection) {
    sourceNodes.forEach((n) => {
      const reason = n.name.replace('[前段] ', '');
      if (sel.frontReason && reason !== sel.frontReason) {
        n.itemStyle = { color: 'rgba(148,163,184,0.4)' };
      }
    });
    targetNodes.forEach((n) => {
      const group = n.name.replace('[下游] ', '');
      if (sel.downstreamGroup && group !== sel.downstreamGroup) {
        n.itemStyle = { color: 'rgba(148,163,184,0.4)' };
      }
    });
  }

  const nodes = [...sourceNodes, ...targetNodes];

  // Build links from cells; zero-qty links are already omitted server-side
  const links = cells.map((cell) => ({
    source: `[前段] ${cell.loss_reason}`,
    target: `[下游] ${cell.workcenter_group}`,
    value: cell.reject_qty,
    lineStyle: {
      color: SANKEY_LINK_COLOR,
      opacity: hasSelection ? (
        (!sel.frontReason || sel.frontReason === cell.loss_reason) &&
        (!sel.downstreamGroup || sel.downstreamGroup === cell.workcenter_group)
          ? 0.55 : 0.08
      ) : 0.3,
    },
  }));

  return {
    animationDuration: 400,
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove',
      formatter(params) {
        if (params.dataType === 'edge') {
          const src = params.data.source.replace('[前段] ', '');
          const tgt = params.data.target.replace('[下游] ', '');
          return `${src} → ${tgt}<br/>不良數: ${params.data.value.toLocaleString()}`;
        }
        const rawName = params.name.replace(/^\[(前段|下游)\] /, '');
        return rawName;
      },
    },
    series: [
      {
        type: 'sankey',
        data: nodes,
        links,
        orient: 'horizontal',
        left: '2%',
        right: '2%',
        top: '8%',
        bottom: '6%',
        nodeWidth: 16,
        nodeGap: 10,
        draggable: false,
        emphasis: { focus: 'trajectory' },
        label: {
          fontSize: 11,
          formatter(p) {
            return p.name.replace(/^\[(前段|下游)\] /, '');
          },
        },
      },
    ],
  };
});

function handleChartClick(params) {
  // Only respond to node clicks
  if (params.dataType !== 'node') return;
  const name = params.name || '';
  if (name.startsWith('[前段] ')) {
    emit('node-click', { frontReason: name.replace('[前段] ', ''), downstreamGroup: null });
  } else if (name.startsWith('[下游] ')) {
    emit('node-click', { frontReason: null, downstreamGroup: name.replace('[下游] ', '') });
  }
}
</script>

<template>
  <div class="forward-flow-chart">
    <div class="chart-header">
      <h3 class="chart-title">前段不良原因 → 下游站點流向 (Sankey)</h3>
      <div class="chart-header-actions">
        <slot name="chart-toggle" />
        <button
          v-if="selection && (selection.frontReason || selection.downstreamGroup)"
          type="button"
          class="clear-selection-btn"
          aria-label="清除選取"
          data-testid="sankey-clear-selection"
          @click="$emit('clear-selection')"
        >
          清除選取
        </button>
      </div>
    </div>
    <div
      v-if="chartOption"
      role="img"
      aria-label="前段不良原因 → 下游站點 Sankey 流向圖"
    >
      <VChart
        class="sankey-canvas"
        :option="chartOption"
        :autoresize="{ throttle: 100 }"
        data-testid="sankey-chart"
        @click="handleChartClick"
      />
    </div>
    <div v-else class="chart-empty">暫無資料</div>
  </div>
</template>

<style scoped>
.forward-flow-chart {
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
.sankey-canvas {
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
