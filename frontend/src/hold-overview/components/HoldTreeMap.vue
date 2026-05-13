<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { TreemapChart } from 'echarts/charts';
import { TooltipComponent, VisualMapComponent } from 'echarts/components';

use([CanvasRenderer, TreemapChart, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  items: {
    type: Array as () => Record<string, unknown>[],
    default: () => [],
  },
  activeFilter: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['select']);

const hasData = computed(() => Array.isArray(props.items) && props.items.length > 0);
const normalizedActiveFilter = computed(() => normalizeFilter(props.activeFilter as TreemapFilter | null));

interface TreemapFilter { workcenter?: string; reason?: string; }

function normalizeFilter(filter: TreemapFilter | null | undefined): TreemapFilter | null {
  if (!filter || typeof filter !== 'object') {
    return null;
  }
  const workcenter = String(filter.workcenter || '').trim() || null;
  const reason = String(filter.reason || '').trim() || null;
  if (!workcenter || !reason) {
    return null;
  }
  return { workcenter, reason };
}

function formatNumber(value: unknown): string {
  return Number(value || 0).toLocaleString('zh-TW');
}

function buildLeafItem(item: Record<string, unknown>, activeFilter: TreemapFilter | null) {
  const workcenter = String(item?.workcenter || '').trim();
  const reason = String(item?.reason || '').trim();
  const lots = Number(item?.lots || 0);
  const qty = Number(item?.qty || 0);
  const avgAge = Number(item?.avgAge || 0);
  const isActive = Boolean(
    activeFilter &&
      activeFilter.workcenter === workcenter &&
      activeFilter.reason === reason,
  );
  const isInactive = Boolean(activeFilter && !isActive);

  return {
    name: reason,
    value: [qty, avgAge],
    workcenter,
    reason,
    lots,
    qty,
    avgAge,
    itemStyle: {
      borderColor: isActive ? 'rgb(17, 24, 39)' : 'rgb(255, 255, 255)',
      borderWidth: isActive ? 3 : 1,
      opacity: isInactive ? 0.72 : 1,
    },
  };
}

const treeData = computed(() => {
  const activeFilter = normalizedActiveFilter.value;
  const workcenterMap = new Map<string, { name: string; children: ReturnType<typeof buildLeafItem>[]; value?: number }>();

  (props.items || []).forEach((item: Record<string, unknown>) => {
    const workcenter = String(item?.workcenter || '').trim();
    const reason = String(item?.reason || '').trim();
    if (!workcenter || !reason) {
      return;
    }

    if (!workcenterMap.has(workcenter)) {
      workcenterMap.set(workcenter, {
        name: workcenter,
        children: [],
      });
    }
    const parent = workcenterMap.get(workcenter)!;
    parent.children.push(buildLeafItem(item, activeFilter));
  });

  const data = Array.from(workcenterMap.values());
  data.forEach((parent) => {
    parent.value = parent.children.reduce((sum: number, child) => sum + Number(child.qty || 0), 0);
    parent.children.sort((a, b) => Number(b.qty || 0) - Number(a.qty || 0));
  });

  return data.sort((a, b) => Number(b.value || 0) - Number(a.value || 0));
});

const chartOption = computed(() => ({
  tooltip: {
    confine: true,
    // TODO: type echarts callback
    formatter(params: any) {
      const node = params?.data || {};
      if (!node?.reason) {
        return `<strong>${params?.name || ''}</strong>`;
      }
      return [
        `<strong>${node.workcenter || '-'}</strong>`,
        `Reason: ${node.reason || '-'}`,
        `Lots: ${formatNumber(node.lots)}`,
        `QTY: ${formatNumber(node.qty)}`,
        `平均滯留: ${Number(node.avgAge || 0).toFixed(1)}天`,
      ].join('<br/>');
    },
  },
  visualMap: {
    type: 'piecewise',
    show: false,
    dimension: 1,
    pieces: [
      { lt: 1, color: 'rgb(34, 197, 94)' },
      { gte: 1, lt: 3, color: 'rgb(234, 179, 8)' },
      { gte: 3, lt: 7, color: 'rgb(249, 115, 22)' },
      { gte: 7, color: 'rgb(239, 68, 68)' },
    ],
  },
  series: [
    {
      name: 'Hold TreeMap',
      type: 'treemap',
      roam: false,
      nodeClick: 'link',
      breadcrumb: { show: false },
      leafDepth: 1,
      visualDimension: 1,
      upperLabel: {
        show: true,
        height: 24,
        color: 'rgb(15, 23, 42)',
        fontWeight: 600,
      },
      label: {
        show: true,
        // TODO: type echarts callback
        formatter(params: any) {
          const reason = params?.data?.reason || params?.name || '';
          return reason.length > 14 ? `${reason.slice(0, 14)}…` : reason;
        },
      },
      itemStyle: {
        borderColor: 'rgb(255, 255, 255)',
        borderWidth: 1,
        gapWidth: 2,
      },
      levels: [
        {
          itemStyle: {
            borderColor: 'rgb(209, 213, 219)',
            borderWidth: 1,
            gapWidth: 2,
          },
          upperLabel: {
            show: true,
          },
        },
        {
          itemStyle: {
            borderColor: 'rgb(255, 255, 255)',
            borderWidth: 1,
            gapWidth: 1,
          },
        },
      ],
      data: treeData.value,
    },
  ],
}));

// TODO: type echarts callback
function handleChartClick(params: any) {
  if (params.componentType !== 'series' || params.seriesType !== 'treemap') {
    return;
  }
  const node = params?.data;
  if (!node || !node.workcenter || !node.reason) {
    return;
  }

  const next = {
    workcenter: String(node.workcenter || ''),
    reason: String(node.reason || ''),
  };
  const current = normalizedActiveFilter.value;
  if (
    current &&
    current.workcenter === next.workcenter &&
    current.reason === next.reason
  ) {
    emit('select', null);
    return;
  }
  emit('select', next);
}
</script>

<template>
  <section class="treemap-section" role="img" aria-label="Hold 樹狀圖">
    <div class="treemap-legend">
      <span><i class="legend-color legend-green"></i>綠(&lt;1天)</span>
      <span><i class="legend-color legend-yellow"></i>黃(1-3天)</span>
      <span><i class="legend-color legend-orange"></i>橙(3-7天)</span>
      <span><i class="legend-color legend-red"></i>紅(&gt;7天)</span>
    </div>

    <VChart
      v-if="hasData"
      class="treemap-chart"
      :option="chartOption"
      :autoresize="{ throttle: 100 }"
      @click="handleChartClick"
    />
    <div v-else class="placeholder treemap-empty">目前無 Hold 資料</div>
  </section>
</template>

<style scoped>
.legend-green { --legend-color: theme('colors.token.h22c55e'); }
.legend-yellow { --legend-color: theme('colors.token.heab308'); }
.legend-orange { --legend-color: theme('colors.token.hf97316'); }
.legend-red { --legend-color: theme('colors.token.hef4444'); }
</style>
