<script setup>
import { computed, ref } from 'vue';

import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { TreeChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';

import { normalizeText } from '../utils/values.js';

use([CanvasRenderer, TreeChart, TooltipComponent]);

const NODE_COLORS = {
  root: '#3B82F6',
  branch: '#10B981',
  leaf: '#F59E0B',
  serial: '#94A3B8',
};

const props = defineProps({
  treeRoots: {
    type: Array,
    default: () => [],
  },
  lineageMap: {
    type: Object,
    required: true,
  },
  nameMap: {
    type: Object,
    default: () => new Map(),
  },
  leafSerials: {
    type: Object,
    default: () => new Map(),
  },
  notFound: {
    type: Array,
    default: () => [],
  },
  selectedContainerIds: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['select-nodes']);

const selectedSet = computed(() => new Set(props.selectedContainerIds.map(normalizeText).filter(Boolean)));

const rootsSet = computed(() => new Set(props.treeRoots.map(normalizeText).filter(Boolean)));

const allSerialNames = computed(() => {
  const names = new Set();
  if (props.leafSerials) {
    for (const serials of props.leafSerials.values()) {
      if (Array.isArray(serials)) {
        serials.forEach((sn) => names.add(sn));
      }
    }
  }
  return names;
});

function detectNodeType(cid, entry, serials) {
  if (rootsSet.value.has(cid)) {
    return 'root';
  }
  const children = entry?.children || [];
  if (children.length === 0 && serials.length > 0) {
    return 'leaf';
  }
  if (children.length === 0 && serials.length === 0) {
    return 'leaf';
  }
  return 'branch';
}

function buildNode(cid, visited) {
  const id = normalizeText(cid);
  if (!id || visited.has(id)) {
    return null;
  }
  visited.add(id);

  const entry = props.lineageMap.get(id);
  const name = props.nameMap?.get?.(id) || id;
  const serials = props.leafSerials?.get?.(id) || [];
  const childIds = entry?.children || [];
  const nodeType = detectNodeType(id, entry, serials);
  const isSelected = selectedSet.value.has(id);

  const children = childIds
    .map((childId) => buildNode(childId, visited))
    .filter(Boolean);

  if (children.length === 0 && serials.length > 0) {
    serials.forEach((sn) => {
      children.push({
        name: sn,
        value: { type: 'serial', cid: id },
        itemStyle: {
          color: NODE_COLORS.serial,
          borderColor: NODE_COLORS.serial,
        },
        label: {
          fontSize: 10,
          color: '#64748B',
        },
        symbol: 'diamond',
        symbolSize: 6,
      });
    });
  }

  // Leaf node whose display name matches a known serial → render as serial style
  const isSerialLike = nodeType === 'leaf'
    && serials.length === 0
    && children.length === 0
    && allSerialNames.value.has(name);
  const effectiveType = isSerialLike ? 'serial' : nodeType;
  const color = NODE_COLORS[effectiveType] || NODE_COLORS.branch;

  return {
    name,
    value: { cid: id, type: effectiveType },
    children,
    itemStyle: {
      color,
      borderColor: isSelected ? '#1D4ED8' : color,
      borderWidth: isSelected ? 3 : 1,
    },
    label: {
      fontWeight: isSelected ? 'bold' : 'normal',
      fontSize: isSerialLike ? 10 : 11,
      color: isSelected ? '#1E3A8A' : (isSerialLike ? '#64748B' : '#334155'),
    },
    symbol: isSerialLike ? 'diamond' : (nodeType === 'root' ? 'roundRect' : 'circle'),
    symbolSize: isSerialLike ? 6 : (nodeType === 'root' ? 14 : 10),
  };
}

// Build each root into its own independent tree data
const treesData = computed(() => {
  if (props.treeRoots.length === 0) {
    return [];
  }

  const globalVisited = new Set();
  return props.treeRoots
    .map((rootId) => buildNode(rootId, globalVisited))
    .filter(Boolean);
});

const hasData = computed(() => treesData.value.length > 0);

function countLeaves(node) {
  if (!node.children || node.children.length === 0) {
    return 1;
  }
  return node.children.reduce((sum, child) => sum + countLeaves(child), 0);
}

const chartHeight = computed(() => {
  const totalLeaves = treesData.value.reduce((sum, tree) => sum + countLeaves(tree), 0);
  const base = Math.max(300, Math.min(1200, totalLeaves * 36));
  return `${base}px`;
});

const TREE_SERIES_DEFAULTS = Object.freeze({
  type: 'tree',
  layout: 'orthogonal',
  orient: 'LR',
  expandAndCollapse: true,
  initialTreeDepth: -1,
  roam: 'move',
  symbol: 'circle',
  symbolSize: 10,
  label: {
    show: true,
    position: 'right',
    fontSize: 11,
    color: '#334155',
    overflow: 'truncate',
    ellipsis: '…',
    width: 160,
  },
  lineStyle: {
    width: 1.5,
    color: '#CBD5E1',
    curveness: 0.5,
  },
  emphasis: {
    focus: 'ancestor',
    itemStyle: { borderWidth: 2 },
    label: { fontWeight: 'bold' },
  },
  animationDuration: 350,
  animationDurationUpdate: 300,
});

const chartOption = computed(() => {
  const trees = treesData.value;
  if (trees.length === 0) {
    return null;
  }

  const tooltip = {
    trigger: 'item',
    triggerOn: 'mousemove',
    formatter(params) {
      const data = params?.data;
      if (!data) {
        return '';
      }
      const val = data.value || {};
      const lines = [`<b>${data.name}</b>`];
      if (val.type === 'serial') {
        lines.push('<span style="color:#64748B">成品序列號</span>');
      } else if (val.type === 'root') {
        lines.push('<span style="color:#3B82F6">根節點（晶批）</span>');
      } else if (val.type === 'leaf') {
        lines.push('<span style="color:#F59E0B">末端節點</span>');
      } else if (val.type === 'branch') {
        lines.push('<span style="color:#10B981">中間節點</span>');
      }
      if (val.cid && val.cid !== data.name) {
        lines.push(`<span style="color:#94A3B8;font-size:11px">CID: ${val.cid}</span>`);
      }
      return lines.join('<br/>');
    },
  };

  // Single root → one series, full area
  if (trees.length === 1) {
    return {
      tooltip,
      series: [{
        ...TREE_SERIES_DEFAULTS,
        left: 40,
        right: 180,
        top: 20,
        bottom: 20,
        data: [trees[0]],
      }],
    };
  }

  // Multiple roots → one series per tree, each in its own vertical band
  const leafCounts = trees.map(countLeaves);
  const totalLeaves = leafCounts.reduce((a, b) => a + b, 0);
  const GAP_PX = 12;
  const totalGapPercent = ((trees.length - 1) * GAP_PX / 800) * 100;
  const usablePercent = 100 - totalGapPercent;

  let cursor = 0;
  const series = trees.map((tree, index) => {
    const fraction = leafCounts[index] / totalLeaves;
    const heightPercent = Math.max(10, usablePercent * fraction);
    const topPercent = cursor;
    cursor += heightPercent + (GAP_PX / 800) * 100;

    return {
      ...TREE_SERIES_DEFAULTS,
      left: 40,
      right: 180,
      top: `${topPercent}%`,
      height: `${heightPercent}%`,
      data: [tree],
    };
  });

  return { tooltip, series };
});

function handleNodeClick(params) {
  const data = params?.data;
  if (!data?.value?.cid) {
    return;
  }
  if (data.value.type === 'serial') {
    return;
  }

  const cid = data.value.cid;
  const current = new Set(selectedSet.value);
  if (current.has(cid)) {
    current.delete(cid);
  } else {
    current.add(cid);
  }
  emit('select-nodes', [...current]);
}
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3 shadow-soft">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 class="text-sm font-semibold text-slate-800">批次血緣樹</h3>
        <p class="text-xs text-slate-500">生產流程追溯：晶批 → 切割 → 封裝 → 成品（點擊節點可多選）</p>
      </div>

      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 text-[10px] text-slate-500">
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-sm" :style="{ background: NODE_COLORS.root }" />
            晶批
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.branch }" />
            中間
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.leaf }" />
            末端
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rotate-45" :style="{ background: NODE_COLORS.serial, width: '8px', height: '8px' }" />
            序列號
          </span>
        </div>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="flex items-center justify-center rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 py-16">
      <div class="flex flex-col items-center gap-2">
        <span class="inline-block size-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
        <span class="text-xs text-slate-500">正在載入血緣資料…</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!hasData" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-10 text-center text-xs text-slate-500">
      目前尚無 LOT 根節點，請先在上方解析。
    </div>

    <!-- ECharts Tree -->
    <div v-else class="relative">
      <VChart
        class="lineage-tree-chart"
        :style="{ height: chartHeight }"
        :option="chartOption"
        autoresize
        @click="handleNodeClick"
      />
    </div>

    <!-- Not found warning -->
    <div v-if="notFound.length > 0" class="mt-3 rounded-card border border-state-warning/40 bg-amber-50 px-3 py-2 text-xs text-amber-700">
      未命中：{{ notFound.join(', ') }}
    </div>

    <!-- Selection summary -->
    <div v-if="selectedContainerIds.length > 0" class="mt-3 rounded-card border border-brand-200 bg-brand-50/60 px-3 py-2">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="mr-1 text-xs font-medium text-brand-700">已選 {{ selectedContainerIds.length }} 個節點</span>
        <span
          v-for="cid in selectedContainerIds.slice(0, 8)"
          :key="cid"
          class="inline-flex items-center rounded-full border border-brand-300 bg-white px-2 py-0.5 font-mono text-xs text-brand-800 shadow-sm"
        >
          {{ nameMap?.get?.(cid) || cid }}
        </span>
        <span v-if="selectedContainerIds.length > 8" class="text-xs text-brand-600">+{{ selectedContainerIds.length - 8 }} 更多</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.lineage-tree-chart {
  width: 100%;
  min-height: 300px;
}
</style>
