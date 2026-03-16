<script setup>
import { computed, nextTick, ref } from 'vue';

import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { TreeChart } from 'echarts/charts';
import { TooltipComponent, ToolboxComponent } from 'echarts/components';

import ExportButton from './ExportButton.vue';
import LoadingOverlay from '../../shared-ui/components/LoadingOverlay.vue';
import PaginationControl from '../../shared-ui/components/PaginationControl.vue';
import { normalizeText } from '../utils/values.js';

use([CanvasRenderer, TreeChart, TooltipComponent, ToolboxComponent]);

const NODE_COLORS = {
  wafer: 'rgb(37, 99, 235)',
  gc: 'rgb(6, 182, 212)',
  ga: 'rgb(16, 185, 129)',
  gd: 'rgb(239, 68, 68)',
  root: 'rgb(59, 130, 246)',
  branch: 'rgb(16, 185, 129)',
  leaf: 'rgb(245, 158, 11)',
  serial: 'rgb(148, 163, 184)',
};

const EDGE_STYLES = Object.freeze({
  split_from: { color: 'rgb(203, 213, 225)', type: 'solid', width: 1.5 },
  merge_source: { color: 'rgb(245, 158, 11)', type: 'dashed', width: 1.8 },
  wafer_origin: { color: 'rgb(37, 99, 235)', type: 'dotted', width: 1.8 },
  gd_rework_source: { color: 'rgb(239, 68, 68)', type: 'dashed', width: 1.8 },
  default: { color: 'rgb(203, 213, 225)', type: 'solid', width: 1.5 },
});

const EDGE_TAGS = Object.freeze({
  split_from: { forward: '←拆', reverse: '→拆' },
  merge_source: { forward: '←併', reverse: '→併' },
  wafer_origin: { forward: '←晶', reverse: '→晶' },
  gd_rework_source: { forward: '←重', reverse: '→重' },
});

const RELATION_TYPE_LABELS = Object.freeze({
  split_from: '拆批',
  merge_source: '併批',
  wafer_origin: '晶圓來源',
  gd_rework_source: '重工來源',
});

const LABEL_BASE_STYLE = Object.freeze({
  backgroundColor: 'rgba(255,255,255,0.92)',
  borderRadius: 3,
  padding: [1, 4],
});

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
  nodeMetaMap: {
    type: Object,
    default: () => new Map(),
  },
  edgeTypeMap: {
    type: Object,
    default: () => new Map(),
  },
  graphEdges: {
    type: Array,
    default: () => [],
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
  title: {
    type: String,
    default: '批次血緣樹',
  },
  description: {
    type: String,
    default: '生產流程追溯：晶批 → 切割 → 封裝 → 成品（點擊節點可多選）',
  },
  emptyMessage: {
    type: String,
    default: '目前尚無 LOT 根節點，請先在上方解析。',
  },
  showSerialLegend: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(['select-nodes']);
const chartRef = ref(null);
const exportingTreeImage = ref(false);
const exportingRelationCsv = ref(false);
const exportErrorMessage = ref('');
const relationPage = ref(1);
const RELATION_PAGE_SIZE = 50;

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

const relationRows = computed(() => {
  const rows = [];
  const seen = new Set();
  const source = Array.isArray(props.graphEdges) ? props.graphEdges : [];

  source.forEach((edge) => {
    if (!edge || typeof edge !== 'object') {
      return;
    }
    const fromCid = normalizeText(edge.from_cid);
    const toCid = normalizeText(edge.to_cid);
    const edgeType = normalizeText(edge.edge_type);
    if (!fromCid || !toCid || !edgeType) {
      return;
    }

    const key = `${fromCid}->${toCid}:${edgeType}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);

    rows.push({
      key,
      fromCid,
      toCid,
      fromName: normalizeText(props.nameMap?.get?.(fromCid) || fromCid),
      toName: normalizeText(props.nameMap?.get?.(toCid) || toCid),
      edgeType,
      edgeLabel: RELATION_TYPE_LABELS[edgeType] || edgeType,
    });
  });

  rows.sort((a, b) => (
    a.edgeLabel.localeCompare(b.edgeLabel, 'zh-Hant')
    || a.fromName.localeCompare(b.fromName, 'zh-Hant')
    || a.toName.localeCompare(b.toName, 'zh-Hant')
  ));
  return rows;
});

const pagedRelationRows = computed(() => relationRows.value.slice(
  (relationPage.value - 1) * RELATION_PAGE_SIZE,
  relationPage.value * RELATION_PAGE_SIZE,
));

const relationTotalPages = computed(() => Math.max(1, Math.ceil(relationRows.value.length / RELATION_PAGE_SIZE)));

function detectNodeType(cid, entry, serials) {
  const explicitType = normalizeText(props.nodeMetaMap?.get?.(cid)?.node_type).toUpperCase();
  if (explicitType === 'WAFER') {
    return 'wafer';
  }
  if (explicitType === 'GC') {
    return 'gc';
  }
  if (explicitType === 'GA') {
    return 'ga';
  }
  if (explicitType === 'GD') {
    return 'gd';
  }

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

function lookupEdgeMeta(parentCid, childCid) {
  const parent = normalizeText(parentCid);
  const child = normalizeText(childCid);
  if (!parent || !child) {
    return { edgeType: '', reversed: false };
  }
  const direct = normalizeText(props.edgeTypeMap?.get?.(`${parent}->${child}`));
  if (direct) {
    return { edgeType: direct, reversed: false };
  }
  const reverse = normalizeText(props.edgeTypeMap?.get?.(`${child}->${parent}`));
  if (reverse) {
    return { edgeType: reverse, reversed: true };
  }
  return { edgeType: '', reversed: false };
}

function relationTag(edgeType, reversed) {
  const spec = EDGE_TAGS[normalizeText(edgeType)];
  if (!spec) {
    return '';
  }
  return reversed ? spec.reverse : spec.forward;
}

function relationSentence({ edgeType, reversed, leftName, currentName }) {
  const left = normalizeText(leftName);
  const current = normalizeText(currentName);
  if (!edgeType || !left || !current) {
    return '';
  }

  if (edgeType === 'split_from') {
    return reversed
      ? `${left} 拆自 ${current}`
      : `${current} 拆自 ${left}`;
  }
  if (edgeType === 'merge_source') {
    return reversed
      ? `${left} 由 ${current} 併批而來`
      : `${current} 由 ${left} 併批而來`;
  }
  if (edgeType === 'wafer_origin') {
    return reversed
      ? `${left} 對應 Wafer ${current}`
      : `${current} 源自 Wafer ${left}`;
  }
  if (edgeType === 'gd_rework_source') {
    return reversed
      ? `${left} 由 ${current} 重工而來`
      : `${current} 由 ${left} 重工而來`;
  }

  return reversed
    ? `${left} 與 ${current}（${edgeType}）`
    : `${current} 與 ${left}（${edgeType}）`;
}

function buildNode(cid, visited, parentCid = '') {
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
    .map((childId) => buildNode(childId, visited, id))
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
          color: 'rgb(100, 116, 139)',
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
  const incomingMeta = lookupEdgeMeta(parentCid, id);
  const incomingEdgeType = incomingMeta.edgeType;
  const incomingEdgeReversed = incomingMeta.reversed;
  const incomingEdgeStyle = EDGE_STYLES[incomingEdgeType] || EDGE_STYLES.default;
  const parentName = normalizeText(props.nameMap?.get?.(normalizeText(parentCid)) || parentCid);
  const shortTag = relationTag(incomingEdgeType, incomingEdgeReversed);
  const displayLabel = shortTag ? `${shortTag} ${name}` : name;

  return {
    name,
    value: {
      cid: id,
      type: effectiveType,
      edgeType: incomingEdgeType || '',
      edgeReversed: incomingEdgeReversed,
      parentName,
      relationTag: shortTag,
    },
    children,
    itemStyle: {
      color,
      borderColor: isSelected ? 'rgb(29, 78, 216)' : color,
      borderWidth: isSelected ? 3 : 1,
    },
    label: {
      ...LABEL_BASE_STYLE,
      position: children.length > 0 ? 'top' : 'right',
      distance: children.length > 0 ? 8 : 6,
      fontWeight: isSelected ? 'bold' : 'normal',
      fontSize: isSerialLike ? 10 : 11,
      color: isSelected ? 'rgb(30, 58, 138)' : (isSerialLike ? 'rgb(100, 116, 139)' : 'rgb(51, 65, 85)'),
      formatter: () => displayLabel,
    },
    symbol: isSerialLike ? 'diamond' : (nodeType === 'root' ? 'roundRect' : 'circle'),
    symbolSize: isSerialLike ? 6 : (nodeType === 'root' ? 14 : 10),
    lineStyle: incomingEdgeStyle,
  };
}

// Build each root into its own independent tree data
const treesData = computed(() => {
  if (props.treeRoots.length === 0) {
    return [];
  }

  return props.treeRoots
    .map((rootId) => buildNode(rootId, new Set()))
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

function countGraphemes(text) {
  return Array.from(normalizeText(text)).length;
}

function walkTreeMetrics(node, depth, metrics) {
  if (!node || typeof node !== 'object') {
    return;
  }

  metrics.maxDepth = Math.max(metrics.maxDepth, depth);
  const relationTag = normalizeText(node?.value?.relationTag);
  const labelText = relationTag
    ? `${relationTag} ${normalizeText(node.name)}`
    : normalizeText(node.name);
  metrics.maxLabelChars = Math.max(metrics.maxLabelChars, countGraphemes(labelText));

  const children = Array.isArray(node.children) ? node.children : [];
  children.forEach((child) => walkTreeMetrics(child, depth + 1, metrics));
}

const treeMetrics = computed(() => {
  const metrics = {
    maxDepth: 1,
    maxLabelChars: 12,
  };

  treesData.value.forEach((tree) => walkTreeMetrics(tree, 1, metrics));
  return metrics;
});

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

const labelWidthPx = computed(() => clampNumber(
  treeMetrics.value.maxLabelChars * 7 + 14,
  120,
  360,
));

const depthSpacingPx = computed(() => clampNumber(
  88 + Math.round(treeMetrics.value.maxLabelChars * 1.4),
  96,
  132,
));

const rootLabelWidthPx = computed(() => {
  const maxChars = props.treeRoots.reduce((max, rootCid) => {
    const rootId = normalizeText(rootCid);
    const rootName = normalizeText(props.nameMap?.get?.(rootId) || rootId);
    return Math.max(max, countGraphemes(rootName));
  }, 8);
  return clampNumber(maxChars * 7 + 24, 72, 260);
});

const chartLayout = computed(() => {
  const left = rootLabelWidthPx.value;
  const right = labelWidthPx.value + 18;
  const depthSpacing = depthSpacingPx.value;
  const depthCount = Math.max(1, treeMetrics.value.maxDepth - 1);
  const requiredWidth = left + right + (depthCount * depthSpacing) + 120;
  const minWidth = clampNumber(requiredWidth, 760, 3000);
  return { left, right, minWidth };
});

const chartMinWidth = computed(() => `${chartLayout.value.minWidth}px`);

const TREE_SERIES_DEFAULTS = Object.freeze({
  type: 'tree',
  layout: 'orthogonal',
  orient: 'LR',
  expandAndCollapse: true,
  initialTreeDepth: 2,
  roam: true,
  symbol: 'circle',
  symbolSize: 10,
  label: {
    show: true,
    position: 'right',
    distance: 6,
    fontSize: 11,
    color: 'rgb(51, 65, 85)',
    overflow: 'break',
    ...LABEL_BASE_STYLE,
  },
  lineStyle: {
    width: 1.5,
    color: 'rgb(203, 213, 225)',
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

  const toolbox = {
    show: true,
    orient: 'vertical',
    right: 8,
    top: 8,
    feature: {
      restore: { title: '重置' },
    },
    iconStyle: {
      borderColor: 'rgb(100, 116, 139)',
    },
    emphasis: {
      iconStyle: {
        borderColor: 'rgb(37, 99, 235)',
      },
    },
  };

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
        lines.push('<span style="color:rgb(100, 116, 139)">成品序列號</span>');
      } else if (val.type === 'wafer') {
        lines.push('<span style="color:rgb(37, 99, 235)">Wafer LOT</span>');
      } else if (val.type === 'gc') {
        lines.push('<span style="color:rgb(6, 182, 212)">GC LOT</span>');
      } else if (val.type === 'ga') {
        lines.push('<span style="color:rgb(16, 185, 129)">GA LOT</span>');
      } else if (val.type === 'gd') {
        lines.push('<span style="color:rgb(239, 68, 68)">GD LOT（重工）</span>');
      } else if (val.type === 'root') {
        lines.push('<span style="color:rgb(59, 130, 246)">根節點（晶批）</span>');
      } else if (val.type === 'leaf') {
        lines.push('<span style="color:rgb(245, 158, 11)">末端節點</span>');
      } else if (val.type === 'branch') {
        lines.push('<span style="color:rgb(16, 185, 129)">中間節點</span>');
      }
      if (val.edgeType) {
        const sentence = relationSentence({
          edgeType: val.edgeType,
          reversed: Boolean(val.edgeReversed),
          leftName: val.parentName,
          currentName: data.name,
        });
        if (sentence) {
          lines.push(`<span style="color:rgb(15, 23, 42);font-size:11px">讀法: ${sentence}</span>`);
        }
        const directionTag = val.relationTag ? `（${val.relationTag}）` : '';
        lines.push(`<span style="color:rgb(148, 163, 184);font-size:11px">關係型別: ${val.edgeType}${directionTag}</span>`);
      }
      if (val.cid && val.cid !== data.name) {
        lines.push(`<span style="color:rgb(148, 163, 184);font-size:11px">CID: ${val.cid}</span>`);
      }
      return lines.join('<br/>');
    },
  };

  // Single root → one series, full area
  if (trees.length === 1) {
    return {
      tooltip,
      toolbox,
      series: [{
        ...TREE_SERIES_DEFAULTS,
        left: chartLayout.value.left,
        right: chartLayout.value.right,
        top: 20,
        bottom: 20,
        label: {
          ...TREE_SERIES_DEFAULTS.label,
          width: labelWidthPx.value,
        },
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
      left: chartLayout.value.left,
      right: chartLayout.value.right,
      top: `${topPercent}%`,
      height: `${heightPercent}%`,
      label: {
        ...TREE_SERIES_DEFAULTS.label,
        width: labelWidthPx.value,
      },
      data: [tree],
    };
  });

  return { tooltip, toolbox, series };
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

function buildExportFileName(ext = 'png') {
  const now = new Date();
  const ts = [
    String(now.getFullYear()).padStart(4, '0'),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join('');
  const rawBase = normalizeText(props.title) || 'lineage_tree';
  const safeBase = rawBase
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '_');
  return `${safeBase}_${ts}.${ext}`;
}

function triggerDownloadByUrl(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function getChartInstance() {
  const chartComponent = chartRef.value;
  if (!chartComponent) {
    return null;
  }
  if (typeof chartComponent.getEchartsInstance === 'function') {
    return chartComponent.getEchartsInstance();
  }
  return chartComponent.chart || null;
}

function escapeCsvField(value) {
  const text = normalizeText(value);
  if (text === '') {
    return '';
  }
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function buildCsvContent() {
  const headers = ['來源批次', '來源CID', '目標批次', '目標CID', '關係', '關係代碼'];
  const lines = [headers.join(',')];

  relationRows.value.forEach((row) => {
    lines.push([
      escapeCsvField(row.fromName),
      escapeCsvField(row.fromCid),
      escapeCsvField(row.toName),
      escapeCsvField(row.toCid),
      escapeCsvField(row.edgeLabel),
      escapeCsvField(row.edgeType),
    ].join(','));
  });

  return `\uFEFF${lines.join('\r\n')}`;
}

function expandAll() {
  const instance = getChartInstance();
  if (!instance) return;
  const series = Array.isArray(chartOption.value?.series) ? chartOption.value.series : [chartOption.value?.series];
  instance.setOption({
    series: series.map((s) => ({ ...s, initialTreeDepth: -1 })),
  }, false);
}

function collapseAll() {
  const instance = getChartInstance();
  if (!instance) return;
  const series = Array.isArray(chartOption.value?.series) ? chartOption.value.series : [chartOption.value?.series];
  instance.setOption({
    series: series.map((s) => ({ ...s, initialTreeDepth: 0 })),
  }, false);
}

function resetView() {
  const instance = getChartInstance();
  if (!instance) return;
  instance.dispatchAction({ type: 'restore' });
}

async function exportTreeAsPng() {
  if (!hasData.value || exportingTreeImage.value) {
    return;
  }

  exportingTreeImage.value = true;
  exportErrorMessage.value = '';

  try {
    await nextTick();
    const instance = getChartInstance();
    if (!instance || typeof instance.getDataURL !== 'function') {
      throw new Error('無法取得樹圖實例');
    }

    const dataUrl = instance.getDataURL({
      type: 'png',
      pixelRatio: Math.min(2, window.devicePixelRatio || 1),
      backgroundColor: 'rgb(255, 255, 255)',
    });
    triggerDownloadByUrl(dataUrl, buildExportFileName('png'));
  } catch (error) {
    exportErrorMessage.value = error?.message || '樹圖匯出失敗';
  } finally {
    exportingTreeImage.value = false;
  }
}

function exportRelationCsv() {
  if (!hasData.value || exportingRelationCsv.value || relationRows.value.length === 0) {
    return;
  }

  exportingRelationCsv.value = true;
  exportErrorMessage.value = '';

  try {
    const csv = buildCsvContent();
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const href = URL.createObjectURL(blob);
    triggerDownloadByUrl(href, buildExportFileName('csv'));
    URL.revokeObjectURL(href);
  } catch (error) {
    exportErrorMessage.value = error?.message || '關係 CSV 匯出失敗';
  } finally {
    exportingRelationCsv.value = false;
  }
}
</script>

<template>
  <section class="card ui-card"><div class="card-body ui-card-body">
    <div class="query-tool-section-header">
      <div>
        <h3 class="card-title ui-card-title">{{ title }}</h3>
        <p class="query-tool-muted">{{ description }}</p>
        <p class="query-tool-muted lineage-direction-note">
          讀圖方向由左至右；節點前綴 <code>←拆/←併/←晶/←重</code> 代表本節點由左側來源而來，
          <code>→拆/→併/→晶/→重</code> 代表左側節點由本節點而來。
        </p>
        <p class="query-tool-muted lineage-direction-note">
          滾輪縮放 · 拖曳平移 · 點擊節點展開/收合分支或多選
        </p>
      </div>

      <div class="flex items-center gap-3">
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="expandAll">全部展開</button>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="collapseAll">全部收合</button>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="resetView">重置視圖</button>
        <ExportButton
          :disabled="!hasData || loading"
          :loading="exportingTreeImage"
          label="匯出樹圖 PNG"
          @click="exportTreeAsPng"
        />
        <ExportButton
          :disabled="!hasData || loading || relationRows.length === 0"
          :loading="exportingRelationCsv"
          label="匯出關係 CSV"
          @click="exportRelationCsv"
        />
        <div class="flex items-center gap-2 text-[10px] text-slate-500">
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-sm" :style="{ background: NODE_COLORS.wafer }" />
            Wafer
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.gc }" />
            GC
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.ga }" />
            GA
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.gd }" />
            GD
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rounded-full" :style="{ background: NODE_COLORS.leaf }" />
            其他 LOT
          </span>
          <span v-if="showSerialLegend" class="inline-flex items-center gap-1">
            <span class="inline-block size-2.5 rotate-45" :style="{ background: NODE_COLORS.serial, width: '8px', height: '8px' }" />
            序列號
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block h-0.5 w-3 bg-slate-300" />
            split(拆批)
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block h-0.5 w-3 border-t-2 border-dashed border-amber-500" />
            merge(併批)
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block h-0.5 w-3 border-t-2 border-dotted border-blue-600" />
            wafer(晶圓來源)
          </span>
          <span class="inline-flex items-center gap-1">
            <span class="inline-block h-0.5 w-3 border-t-2 border-dashed border-red-500" />
            gd-rework(重工來源)
          </span>
        </div>
      </div>
    </div>
    <p v-if="exportErrorMessage" class="error-banner">
      {{ exportErrorMessage }}
    </p>

    <!-- Loading overlay -->
    <div v-if="loading" class="placeholder lineage-loading-placeholder">
      正在載入血緣資料…
    </div>

    <!-- Empty state -->
    <div v-else-if="!hasData" class="placeholder">
      {{ emptyMessage }}
    </div>

    <!-- ECharts Tree -->
    <div v-else class="relative">
      <LoadingOverlay v-if="exportingTreeImage" />
      <VChart
        ref="chartRef"
        class="lineage-tree-chart"
        :style="{ height: chartHeight, width: '100%' }"
        :option="chartOption"
        :autoresize="{ throttle: 100 }"
        @click="handleNodeClick"
      />
    </div>

    <details v-if="relationRows.length > 0" class="lineage-relation-details">
      <summary class="lineage-relation-summary">
        關係清單（{{ relationRows.length }}）
      </summary>
      <div class="query-tool-table-wrap short lineage-relation-table-wrap">
        <table class="query-tool-table">
          <thead>
            <tr>
              <th>來源批次</th>
              <th>目標批次</th>
              <th>關係</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in pagedRelationRows"
              :key="row.key"
            >
              <td class="lineage-relation-cell mono">
                {{ row.fromName }}
              </td>
              <td class="lineage-relation-cell mono">
                {{ row.toName }}
              </td>
              <td class="lineage-relation-cell">
                {{ row.edgeLabel }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControl
        v-if="relationTotalPages > 1"
        v-model="relationPage"
        :total-pages="relationTotalPages"
        :info-text="`第 ${relationPage}/${relationTotalPages} 頁，共 ${relationRows.length} 筆`"
      />
    </details>

    <!-- Not found warning -->
    <div v-if="notFound.length > 0" class="query-tool-success lineage-not-found">
      未命中：{{ notFound.join(', ') }}
    </div>

    <!-- Selection summary -->
    <div v-if="selectedContainerIds.length > 0" class="query-tool-success lineage-selected-summary">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="mr-1 text-xs font-medium lineage-selected-count">已選 {{ selectedContainerIds.length }} 個節點</span>
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
  </div></section>
</template>

<style scoped>
.lineage-tree-chart {
  width: 100%;
  min-height: 300px;
}

.lineage-direction-note {
  font-size: 11px;
}

.lineage-loading-placeholder {
  padding: theme('spacing.token.p48') theme('spacing.token.p12');
}

.lineage-relation-details {
  margin-top: theme('spacing.token.p12');
  border: 1px solid var(--border);
  border-radius: 8px;
  background: theme('colors.token.hf8fafc');
  padding: theme('spacing.token.p8') theme('spacing.token.p12');
}

.lineage-relation-summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: theme('colors.token.h334155');
}

.lineage-relation-table-wrap {
  margin-top: theme('spacing.token.p8');
  max-height: 224px;
}

.lineage-relation-cell {
  font-size: 11px;
}

.lineage-relation-cell.mono {
  font-family: monospace;
}

.lineage-relation-note {
  margin-top: theme('spacing.token.p4');
  font-size: 11px;
}

.lineage-not-found {
  border-color: theme('colors.token.hfde68a');
  background: theme('colors.token.hfefce8');
  color: theme('colors.token.h92400e');
}

.lineage-selected-summary {
  border-color: theme('colors.token.hc7d2fe');
  background: rgba(238, 242, 255, 0.6);
  color: inherit;
}

.lineage-selected-count {
  color: theme('colors.token.h4338ca');
}
</style>
