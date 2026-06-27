<script setup lang="ts">
/**
 * LineageTreeChart — SVG-based lineage tree (replaces ECharts TreeChart)
 * Layout: d3-hierarchy tree()  |  Rendering: hand-crafted SVG cards
 *
 * Card design: left colour stripe + white/tinted body + drop shadow
 * Pan/zoom: wheel to zoom, drag to pan (no external dependency)
 */
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, triggerRef, watch } from 'vue';
import { hierarchy, tree as d3Tree } from 'd3-hierarchy';
import type { HierarchyPointNode } from 'd3-hierarchy';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import ExportButton from './ExportButton.vue';
import PaginationControl from '../../shared-ui/components/PaginationControl.vue';
import { normalizeText } from '../utils/values';

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────

const CARD_H       = 38;    // card height px
const STRIPE_W     = 5;     // left colour stripe width
const CARD_R       = 7;     // corner radius
const CARD_MIN_W   = 110;
const CARD_MAX_W   = 270;
const TOGGLE_W     = 32;    // width of [-] / [+N] toggle pills
const NODE_V_GAP   = 30;    // vertical gap between sibling cards
const DEPTH_STEP   = 280;   // horizontal step per tree level
const SERIAL_R     = 5;     // diamond (serial) half-size
const BADGE_H      = 16;    // type badge height
const PAD_L        = 10;    // left padding inside card body (after stripe)
const PAD_R        = 10;    // right padding

const NODE_COLORS: Record<string, string> = {
  wafer:  '#2563eb',
  gc:     '#06b6d4',
  ga:     '#10b981',
  gd:     '#ef4444',
  root:   '#3b82f6',
  branch: '#64748b',
  leaf:   '#f59e0b',
  serial: '#94a3b8',
  toggle: '#a5b4fc',
};

const CARD_BG: Record<string, string> = {
  wafer:  'rgba(37,99,235,0.06)',
  gc:     'rgba(6,182,212,0.06)',
  ga:     'rgba(16,185,129,0.06)',
  gd:     'rgba(239,68,68,0.06)',
  root:   'rgba(59,130,246,0.06)',
  branch: '#f8fafc',
  leaf:   'rgba(245,158,11,0.06)',
};

const SHADOW_COLOR: Record<string, string> = {
  wafer:  'rgba(37,99,235,0.22)',
  gc:     'rgba(6,182,212,0.22)',
  ga:     'rgba(16,185,129,0.22)',
  gd:     'rgba(239,68,68,0.22)',
  root:   'rgba(59,130,246,0.22)',
  branch: 'rgba(0,0,0,0.10)',
  leaf:   'rgba(245,158,11,0.22)',
  toggle: 'rgba(99,102,241,0.18)',
};

const EDGE_LINE: Record<string, { stroke: string; width: number; dash?: string }> = {
  split_from:       { stroke: '#94a3b8', width: 1.5 },
  merge_source:     { stroke: '#f59e0b', width: 1.8, dash: '6,4' },
  wafer_origin:     { stroke: '#2563eb', width: 1.8, dash: '2,3' },
  gd_rework_source: { stroke: '#ef4444', width: 1.8, dash: '6,4' },
  default:          { stroke: '#94a3b8', width: 1.5 },
};

const EDGE_TAGS: Record<string, { forward: string; reverse: string }> = {
  split_from:       { forward: '←拆', reverse: '→拆' },
  merge_source:     { forward: '←併', reverse: '→併' },
  wafer_origin:     { forward: '←晶', reverse: '→晶' },
  gd_rework_source: { forward: '←重', reverse: '→重' },
};

const EDGE_TAG_COLOR: Record<string, string> = {
  split_from:       '#94a3b8',
  merge_source:     '#d97706',
  wafer_origin:     '#2563eb',
  gd_rework_source: '#dc2626',
};

const RELATION_TYPE_LABELS: Record<string, string> = {
  split_from: '拆批', merge_source: '併批', wafer_origin: '晶圓來源', gd_rework_source: '重工來源',
};

const TYPE_BADGE: Record<string, string> = { wafer: '晶', gc: 'GC', ga: 'GA', gd: 'GD' };

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface NodeData {
  id: string;
  name: string;
  type: string;
  edgeType: string;
  edgeReversed: boolean;
  parentName: string;
  relationTag: string;
  cardW: number;
  isToggle?: 'minus' | 'plus';
  isSerial?: boolean;
  children?: NodeData[];
}

type D3Point = HierarchyPointNode<NodeData>;

interface LayoutNode {
  data: NodeData;
  svgX: number;
  svgY: number;
}

interface LayoutLink {
  source: LayoutNode;
  target: LayoutNode;
}

// ─────────────────────────────────────────────────────────────
// Props & emits
// ─────────────────────────────────────────────────────────────

const props = defineProps({
  treeRoots:            { type: Array,   default: () => [] },
  lineageMap:           { type: Object,  required: true },
  nameMap:              { type: Object,  default: () => new Map() },
  nodeMetaMap:          { type: Object,  default: () => new Map() },
  edgeTypeMap:          { type: Object,  default: () => new Map() },
  graphEdges:           { type: Array,   default: () => [] },
  leafSerials:          { type: Object,  default: () => new Map() },
  notFound:             { type: Array,   default: () => [] },
  selectedContainerIds: { type: Array,   default: () => [] },
  loading:              { type: Boolean, default: false },
  title:                { type: String,  default: '批次血緣樹' },
  description:          { type: String,  default: '生產流程追溯：晶批 → 切割 → 封裝 → 成品' },
  emptyMessage:         { type: String,  default: '目前尚無 LOT 根節點，請先在上方解析。' },
  showSerialLegend:     { type: Boolean, default: true },
  isReverse:            { type: Boolean, default: false },
});

const emit = defineEmits(['select-nodes']);

// ─────────────────────────────────────────────────────────────
// Reactive state
// ─────────────────────────────────────────────────────────────

const collapsedCids = shallowRef(new Set<string>());

const selectedSet = computed(() =>
  new Set((props.selectedContainerIds as string[]).map(normalizeText).filter(Boolean))
);
const rootsSet = computed(() =>
  new Set((props.treeRoots as string[]).map(normalizeText).filter(Boolean))
);
const allSerialNames = computed(() => {
  const s = new Set<string>();
  const lm = props.leafSerials as Map<string, string[]>;
  if (lm) for (const serials of lm.values()) if (Array.isArray(serials)) serials.forEach(sn => s.add(sn));
  return s;
});

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function charPx(text: string): number {
  let px = 0;
  for (const ch of text) px += ch.codePointAt(0)! > 127 ? 13 : 7.5;
  return px;
}

function calcCardW(displayLabel: string, hasBadge: boolean): number {
  const badgePx = hasBadge ? charPx(TYPE_BADGE['ga'] || 'GA') + 14 : 0; // approximate badge
  return Math.min(Math.max(charPx(displayLabel) + badgePx + STRIPE_W + PAD_L + PAD_R, CARD_MIN_W), CARD_MAX_W);
}

function lookupEdge(parentCid: string, childCid: string) {
  const em = props.edgeTypeMap as Map<string, string>;
  const p = normalizeText(parentCid), c = normalizeText(childCid);
  if (!p || !c) return { edgeType: '', reversed: false };
  const direct = normalizeText(em?.get?.(`${p}->${c}`));
  if (direct) return { edgeType: direct, reversed: false };
  const rev = normalizeText(em?.get?.(`${c}->${p}`));
  if (rev) return { edgeType: rev, reversed: true };
  return { edgeType: '', reversed: false };
}

function getRelTag(edgeType: string, reversed: boolean): string {
  const spec = EDGE_TAGS[normalizeText(edgeType)];
  if (!spec) return '';
  return reversed ? spec.reverse : spec.forward;
}

function detectType(cid: string, childIds: string[], serials: string[]): string {
  const meta = (props.nodeMetaMap as Map<string, { node_type?: string }>)?.get?.(cid);
  const ex = normalizeText(meta?.node_type).toUpperCase();
  if (ex === 'WAFER') return 'wafer';
  if (ex === 'GC')    return 'gc';
  if (ex === 'GA')    return 'ga';
  if (ex === 'GD')    return 'gd';
  if (rootsSet.value.has(cid)) return 'root';
  return childIds.length === 0 ? 'leaf' : 'branch';
}

function nodeColor(type: string): string {
  return NODE_COLORS[type] || NODE_COLORS.branch;
}

// ─────────────────────────────────────────────────────────────
// Tree data builder (D3-compatible plain objects)
// ─────────────────────────────────────────────────────────────

/**
 * Mark all descendants of `cid` as visited without building NodeData.
 * Called when a node is collapsed so its subtree nodes don't "escape"
 * to higher levels via other parent paths.
 */
function collectDescendants(cid: string, visited: Set<string>) {
  const lm = props.lineageMap as Map<string, { children?: string[] }>;
  const childIds = (lm?.get?.(cid)?.children || []) as string[];
  for (const rawChild of childIds) {
    const childId = normalizeText(rawChild);
    if (!childId || visited.has(childId)) continue;
    visited.add(childId);
    collectDescendants(childId, visited);
  }
}

function buildNode(cid: unknown, visited: Set<string>, parentCid = ''): NodeData | null {
  const id = normalizeText(cid);
  if (!id || visited.has(id)) return null;
  visited.add(id);

  const nm    = props.nameMap  as Map<string, string>;
  const lm    = props.lineageMap as Map<string, { children?: string[] }>;
  const slm   = props.leafSerials as Map<string, string[]>;

  const name     = nm?.get?.(id) || id;
  const serials  = slm?.get?.(id) || [];
  const childIds = (lm?.get?.(id)?.children || []) as string[];
  const type     = detectType(id, childIds, serials as string[]);

  const { edgeType, reversed } = lookupEdge(parentCid, id);
  const relTag     = getRelTag(edgeType, reversed);
  const parentName = normalizeText(nm?.get?.(normalizeText(parentCid)) || parentCid);
  const displayLabel = relTag ? `${relTag} ${name}` : name;
  const badge      = TYPE_BADGE[type] || '';
  const cardW      = calcCardW(displayLabel, !!badge);

  // Serial-like leaf: node whose name matches a known serial number
  const isSerialLike = type === 'leaf'
    && (serials as string[]).length === 0
    && allSerialNames.value.has(name);

  if (isSerialLike) {
    return { id, name, type: 'serial', edgeType, edgeReversed: reversed, parentName, relationTag: relTag, cardW: 0, isSerial: true, children: [] };
  }

  const isCollapsed = collapsedCids.value.has(id);
  let children: NodeData[] = [];

  if (isCollapsed && childIds.length > 0) {
    // Pre-mark the entire collapsed subtree so those nodes don't appear
    // at higher levels via other parent paths (DAG multi-parent case).
    collectDescendants(id, visited);
    children = [{
      id: `__expand__${id}`, name: `+${childIds.length}`, type: 'toggle',
      edgeType: '', edgeReversed: false, parentName: '', relationTag: '',
      cardW: TOGGLE_W, isToggle: 'plus', children: [],
    }];
  } else {
    const orderedIds = props.isReverse
      ? [...childIds].sort((a, b) => {
          const pri: Record<string, number> = { split_from: 0, merge_source: 1, gd_rework_source: 2, wafer_origin: 3 };
          return (pri[normalizeText(lookupEdge(id, a).edgeType)] ?? 1) - (pri[normalizeText(lookupEdge(id, b).edgeType)] ?? 1);
        })
      : childIds as string[];

    const built = orderedIds.map(c2 => buildNode(c2, visited, id)).filter((n): n is NodeData => n !== null);

    // Serial leaf children (inline serial nodes)
    if (built.length === 0 && (serials as string[]).length > 0) {
      (serials as string[]).forEach((sn: string) => {
        built.push({ id: `__sn__${id}__${sn}`, name: sn, type: 'serial', edgeType: '', edgeReversed: false, parentName: name, relationTag: '', cardW: 0, isSerial: true, children: [] });
      });
    }

    // [-] collapse toggle at the BOTTOM of the children list
    if (built.length > 0 && childIds.length > 0 && !rootsSet.value.has(id)) {
      built.push({ id: `__collapse__${id}`, name: '−', type: 'toggle', edgeType: '', edgeReversed: false, parentName: '', relationTag: '', cardW: TOGGLE_W, isToggle: 'minus', children: [] });
    }

    children = built;
  }

  return { id, name, type, edgeType, edgeReversed: reversed, parentName, relationTag: relTag, cardW, children };
}

// ─────────────────────────────────────────────────────────────
// D3 layout
// ─────────────────────────────────────────────────────────────

const treeData = computed((): NodeData | null => {
  collapsedCids.value; selectedSet.value; // reactive deps
  const roots = (props.treeRoots as string[]).map(r => buildNode(r, new Set())).filter((n): n is NodeData => n !== null);
  if (roots.length === 0) return null;
  return roots.length === 1
    ? roots[0]
    : { id: '__vroot__', name: '', type: 'virtual', edgeType: '', edgeReversed: false, parentName: '', relationTag: '', cardW: 0, children: roots };
});

const layout = computed<{ nodes: LayoutNode[]; links: LayoutLink[]; w: number; h: number } | null>(() => {
  const root = treeData.value;
  if (!root) return null;

  const hier    = hierarchy<NodeData>(root, d => d.children);
  const layoutFn = d3Tree<NodeData>().nodeSize([CARD_H + NODE_V_GAP, DEPTH_STEP]);
  const laid    = layoutFn(hier);

  // d3 tree: x = breadth (→ SVG Y for LR),  y = depth (→ SVG X for LR)
  type D3N = { data: NodeData; x: number; y: number };
  type D3L = { source: D3N; target: D3N };

  const all   = (laid.descendants() as unknown as D3N[]).filter(n => n.data.type !== 'virtual');
  const links = (laid.links() as unknown as D3L[]).filter(l => l.source.data.type !== 'virtual');

  const toLayout = (n: D3N): LayoutNode => ({ data: n.data, svgX: n.y, svgY: n.x });

  const nodes: LayoutNode[] = all.map(toLayout);
  const layoutLinks: LayoutLink[] = links.map(l => ({ source: toLayout(l.source), target: toLayout(l.target) }));

  // Compute bounding box & offset so content starts at (pad, pad)
  const pad = 50;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    const hw = n.data.cardW / 2 || SERIAL_R;
    minX = Math.min(minX, n.svgX - hw);
    maxX = Math.max(maxX, n.svgX + hw);
    minY = Math.min(minY, n.svgY - CARD_H / 2);
    maxY = Math.max(maxY, n.svgY + CARD_H / 2);
  }
  const ox = -minX + pad, oy = -minY + pad;
  nodes.forEach(n => { n.svgX += ox; n.svgY += oy; });
  layoutLinks.forEach(l => {
    l.source.svgX += ox; l.source.svgY += oy;
    l.target.svgX += ox; l.target.svgY += oy;
  });

  return { nodes, links: layoutLinks, w: maxX - minX + pad * 2, h: maxY - minY + pad * 2 };
});

const hasData = computed(() => !!layout.value?.nodes.length);

// ─────────────────────────────────────────────────────────────
// Pan / Zoom
// ─────────────────────────────────────────────────────────────

const svgRef  = ref<SVGSVGElement | null>(null);
const wrapRef = ref<HTMLDivElement | null>(null);
const tx = ref(0), ty = ref(0), sc = ref(0.9);
let drag: { cx: number; cy: number; tx0: number; ty0: number } | null = null;

function onWheel(e: WheelEvent) {
  e.preventDefault();
  sc.value = Math.max(0.15, Math.min(4, sc.value * (e.deltaY < 0 ? 1.1 : 0.9)));
}
function onMD(e: MouseEvent) {
  if (e.button !== 0) return;
  drag = { cx: e.clientX, cy: e.clientY, tx0: tx.value, ty0: ty.value };
}
function onMM(e: MouseEvent) {
  if (!drag) return;
  tx.value = drag.tx0 + (e.clientX - drag.cx);
  ty.value = drag.ty0 + (e.clientY - drag.cy);
}
function onMU() { drag = null; }

function fitView() {
  if (!layout.value || !wrapRef.value) return;
  const { w, h } = layout.value;
  const { clientWidth: cw, clientHeight: ch } = wrapRef.value;
  const newSc = Math.min(0.95, cw / w, ch / h);
  sc.value = newSc;
  tx.value = (cw - w * newSc) / 2;
  ty.value = (ch - h * newSc) / 2;
}

// New query: reset → full expand → collapseAll → fitView.
// User interactions (expand/collapse single nodes) do NOT trigger fitView.
watch(() => (props.treeRoots as string[]).join(','), async (newVal) => {
  if (!newVal) return;
  // Clear old collapsed state so treeData builds the complete tree
  collapsedCids.value = new Set();
  triggerRef(collapsedCids);
  await nextTick();    // treeData recomputes fully expanded
  collapseAll();       // mark every branch node as collapsed
  await nextTick();    // layout recomputes in collapsed form
  fitView();           // scale to fit the now-compact view
}, { immediate: true });

onMounted(() => {
  window.addEventListener('mousemove', onMM);
  window.addEventListener('mouseup',   onMU);
});
onUnmounted(() => {
  window.removeEventListener('mousemove', onMM);
  window.removeEventListener('mouseup',   onMU);
});

// ─────────────────────────────────────────────────────────────
// SVG geometry
// ─────────────────────────────────────────────────────────────

/** Cubic bezier path: right-edge of source card → left-edge of target card */
function edgePath(src: LayoutNode, tgt: LayoutNode): string {
  const isSerial = tgt.data.isSerial;
  const srcX = src.svgX + src.data.cardW / 2;
  const tgtX = tgt.svgX - (isSerial ? SERIAL_R + 2 : tgt.data.cardW / 2);
  const mx   = (srcX + tgtX) / 2;
  return `M ${srcX} ${src.svgY} C ${mx} ${src.svgY}, ${mx} ${tgt.svgY}, ${tgtX} ${tgt.svgY}`;
}

function edgeLineStyle(tgt: LayoutNode) {
  const s = EDGE_LINE[tgt.data.edgeType] || EDGE_LINE.default;
  return { stroke: s.stroke, strokeWidth: s.width, strokeDasharray: s.dash || '' };
}

/** Card outer rect path (rounded rect with CARD_R) for shadow */
function shadowAttrs(cw: number) {
  return { x: -cw / 2, y: -CARD_H / 2, width: cw, height: CARD_H, rx: CARD_R };
}

/** Left stripe path — rounded only on the left side */
function stripePath(cw: number): string {
  const r = CARD_R, x0 = -cw / 2, x1 = x0 + STRIPE_W, h = CARD_H;
  return `M ${x1} ${-h/2} L ${x0+r} ${-h/2} Q ${x0} ${-h/2} ${x0} ${-h/2+r}`
       + ` L ${x0} ${h/2-r} Q ${x0} ${h/2} ${x0+r} ${h/2}`
       + ` L ${x1} ${h/2} Z`;
}

/** Card body path — white/tinted, rounded only on the right side */
function bodyPath(cw: number): string {
  const r = CARD_R, x0 = -cw / 2 + STRIPE_W, x1 = cw / 2, h = CARD_H;
  return `M ${x0} ${-h/2} L ${x1-r} ${-h/2} Q ${x1} ${-h/2} ${x1} ${-h/2+r}`
       + ` L ${x1} ${h/2-r} Q ${x1} ${h/2} ${x1-r} ${h/2}`
       + ` L ${x0} ${h/2} Z`;
}

// Badge for type-badged nodes: returns { text, x, w }
function badgeInfo(type: string, cw: number) {
  const label = TYPE_BADGE[type] || '';
  if (!label) return null;
  const bw = charPx(label) + 10;
  const bx = -cw / 2 + STRIPE_W + PAD_L;
  return { label, bx, bw, bh: BADGE_H, color: nodeColor(type) };
}

// Text X start (after stripe + optional badge)
function textX(type: string, cw: number): number {
  const badge = badgeInfo(type, cw);
  if (badge) return badge.bx + badge.bw + 5;
  return -cw / 2 + STRIPE_W + PAD_L;
}

// Diamond path for serial nodes
function diamondPath(): string {
  const r = SERIAL_R;
  return `M 0 ${-r} L ${r} 0 L 0 ${r} L ${-r} 0 Z`;
}

// ─────────────────────────────────────────────────────────────
// Node click
// ─────────────────────────────────────────────────────────────

function handleClick(node: LayoutNode) {
  const { data } = node;
  if (data.isToggle === 'minus') {
    const pid = normalizeText(data.id.replace('__collapse__', ''));
    if (pid) { const s = new Set(collapsedCids.value); s.add(pid); collapsedCids.value = s; triggerRef(collapsedCids); }
    return;
  }
  if (data.isToggle === 'plus') {
    const pid = normalizeText(data.id.replace('__expand__', ''));
    if (pid) { const s = new Set(collapsedCids.value); s.delete(pid); collapsedCids.value = s; triggerRef(collapsedCids); }
    return;
  }
}

// ─────────────────────────────────────────────────────────────
// Expand / Collapse all
// ─────────────────────────────────────────────────────────────

function expandAll() { collapsedCids.value = new Set(); triggerRef(collapsedCids); }

function collapseAll() {
  const set = new Set<string>();
  function walk(n: NodeData) {
    for (const c of (n.children || [])) {
      const e = (props.lineageMap as Map<string, { children?: string[] }>).get(c.id);
      if ((e?.children?.length || 0) > 0) set.add(c.id);
      walk(c);
    }
  }
  if (treeData.value) walk(treeData.value);
  collapsedCids.value = set;
  triggerRef(collapsedCids);
}

// ─────────────────────────────────────────────────────────────
// Relation rows table
// ─────────────────────────────────────────────────────────────

const RELATION_PAGE_SIZE = 50;
const relationPage = ref(1);

const relationRows = computed(() => {
  const rows: Array<Record<string, string>> = [];
  const seen = new Set<string>();
  const nm = props.nameMap as Map<string, string>;
  ((props.graphEdges as unknown[]) || []).forEach((edge: unknown) => {
    if (!edge || typeof edge !== 'object') return;
    const e = edge as Record<string, unknown>;
    const fc = normalizeText(e.from_cid), tc = normalizeText(e.to_cid), et = normalizeText(e.edge_type);
    if (!fc || !tc || !et) return;
    const key = `${fc}->${tc}:${et}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ key, fromCid: fc, toCid: tc, fromName: nm?.get?.(fc) || fc, toName: nm?.get?.(tc) || tc, edgeType: et, edgeLabel: RELATION_TYPE_LABELS[et] || et });
  });
  rows.sort((a, b) => a.edgeLabel.localeCompare(b.edgeLabel, 'zh-Hant') || a.fromName.localeCompare(b.fromName, 'zh-Hant'));
  return rows;
});

const pagedRelationRows = computed(() => relationRows.value.slice((relationPage.value - 1) * RELATION_PAGE_SIZE, relationPage.value * RELATION_PAGE_SIZE));
const relationTotalPages = computed(() => Math.max(1, Math.ceil(relationRows.value.length / RELATION_PAGE_SIZE)));

// ─────────────────────────────────────────────────────────────
// Export
// ─────────────────────────────────────────────────────────────

const exportingPng = ref(false), exportingCsv = ref(false), exportError = ref('');

function fileName(ext = 'png') {
  const now = new Date();
  const ts = [now.getFullYear(), String(now.getMonth()+1).padStart(2,'0'), String(now.getDate()).padStart(2,'0'), String(now.getHours()).padStart(2,'0'), String(now.getMinutes()).padStart(2,'0'), String(now.getSeconds()).padStart(2,'0')].join('');
  return `${(normalizeText(props.title) || 'lineage').replace(/[\\/:*?"<>|]/g,'-').replace(/\s+/g,'_')}_${ts}.${ext}`;
}
function dl(url: string, name: string) { const a = document.createElement('a'); a.href=url; a.download=name; a.rel='noopener'; document.body.appendChild(a); a.click(); document.body.removeChild(a); }

async function exportPng() {
  if (!svgRef.value || exportingPng.value || !layout.value) return;
  exportingPng.value = true; exportError.value = '';
  try {
    const { w, h } = layout.value;
    const clone = svgRef.value.cloneNode(true) as SVGSVGElement;
    clone.setAttribute('width', String(Math.ceil(w)));
    clone.setAttribute('height', String(Math.ceil(h)));
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const zg = clone.querySelector('.lt-zoom') as SVGGElement | null;
    if (zg) zg.setAttribute('transform', 'translate(0,0) scale(1)');
    const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const img  = new Image();
    await new Promise<void>((res, rej) => { img.onload = () => res(); img.onerror = rej; img.src = url; });
    const cv = document.createElement('canvas');
    const px = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.ceil(w)*px; cv.height = Math.ceil(h)*px;
    const ctx = cv.getContext('2d')!;
    ctx.scale(px, px); ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    dl(cv.toDataURL('image/png'), fileName('png'));
  } catch(e) { exportError.value = (e as Error)?.message || '匯出失敗'; }
  finally { exportingPng.value = false; }
}

function exportCsv() {
  if (!hasData.value || exportingCsv.value || !relationRows.value.length) return;
  exportingCsv.value = true; exportError.value = '';
  try {
    const esc = (v: unknown) => { const t = normalizeText(v); return /[",\n\r]/.test(t) ? `"${t.replace(/"/g,'""')}"` : t; };
    const lines = [['來源批次','來源CID','目標批次','目標CID','關係','關係代碼'].join(','),
      ...relationRows.value.map(r => [esc(r.fromName),esc(r.fromCid),esc(r.toName),esc(r.toCid),esc(r.edgeLabel),esc(r.edgeType)].join(','))];
    const url = URL.createObjectURL(new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8;' }));
    dl(url, fileName('csv')); URL.revokeObjectURL(url);
  } catch(e) { exportError.value = (e as Error)?.message || 'CSV 匯出失敗'; }
  finally { exportingCsv.value = false; }
}

// ─────────────────────────────────────────────────────────────
// Selection
// ─────────────────────────────────────────────────────────────

function removeSelection(cid: unknown) {
  const s = new Set(selectedSet.value); s.delete(normalizeText(cid)); emit('select-nodes', [...s]);
}
</script>

<template>
  <section class="card ui-card"><div class="card-body ui-card-body">

    <!-- Header: toolbar + legend only, no title/description redundancy -->
    <div class="lt-toolbar-row">
      <div class="lt-toolbar">
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="expandAll">全部展開</button>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="collapseAll">全部收合</button>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="!hasData || loading" @click="fitView">重置視圖</button>
        <ExportButton :disabled="!hasData || loading" :loading="exportingPng" label="匯出 PNG" @click="exportPng" />
        <ExportButton :disabled="!hasData || loading || !relationRows.length" :loading="exportingCsv" label="匯出關係 CSV" @click="exportCsv" />
        <!-- Legend -->
        <div class="lt-legend">
          <span v-for="[k,label] in [['wafer','Wafer'],['gc','GC'],['ga','GA'],['gd','GD'],['leaf','其他LOT']]" :key="k" class="lt-legend-item">
            <span class="lt-legend-dot" :style="{ background: NODE_COLORS[k] }" />
            {{ label }}
          </span>
          <span v-if="showSerialLegend" class="lt-legend-item">
            <span class="lt-legend-diamond" :style="{ borderColor: NODE_COLORS.serial }" />
            序列號
          </span>
          <span class="lt-legend-item"><span class="lt-legend-line" />split</span>
          <span class="lt-legend-item"><span class="lt-legend-line lt-legend-line--dashed" :style="{ borderColor: EDGE_LINE.merge_source.stroke }" />merge</span>
          <span class="lt-legend-item"><span class="lt-legend-line lt-legend-line--dotted" :style="{ borderColor: EDGE_LINE.wafer_origin.stroke }" />wafer</span>
          <span class="lt-legend-item"><span class="lt-legend-line lt-legend-line--dashed" :style="{ borderColor: EDGE_LINE.gd_rework_source.stroke }" />rework</span>
        </div><!-- /lt-legend -->
      </div><!-- /lt-toolbar -->
    </div><!-- /lt-toolbar-row -->

    <ErrorBanner :message="exportError" @dismiss="exportError = ''" />

    <!-- States -->
    <div v-if="loading"    class="placeholder lt-placeholder">正在載入血緣資料…</div>
    <div v-else-if="!hasData" class="placeholder lt-placeholder">{{ emptyMessage }}</div>

    <!-- SVG canvas -->
    <div
      v-else
      ref="wrapRef"
      class="lt-canvas-wrap"
      @wheel.prevent="onWheel"
      @mousedown="onMD"
    >
      <svg
        ref="svgRef"
        class="lt-svg"
        xmlns="http://www.w3.org/2000/svg"
      >
        <!-- ── Defs: shadow filters ── -->
        <defs>
          <filter v-for="type in ['wafer','gc','ga','gd','root','branch','leaf','toggle']"
                  :key="type"
                  :id="`lt-shd-${type}`"
                  x="-30%" y="-40%" width="160%" height="180%">
            <feDropShadow dx="0" dy="2" stdDeviation="4"
                          :flood-color="SHADOW_COLOR[type] || 'rgba(0,0,0,0.1)'"
                          flood-opacity="1" />
          </filter>
          <filter id="lt-shd-selected" x="-30%" y="-40%" width="160%" height="180%">
            <feDropShadow dx="0" dy="3" stdDeviation="7" flood-color="rgba(0,0,0,0.28)" flood-opacity="1" />
          </filter>
        </defs>

        <!-- ── Zoom/pan group ── -->
        <g class="lt-zoom" :transform="`translate(${tx},${ty}) scale(${sc})`">

          <!-- ── Links (skip toggle nodes — they need no connector line) ── -->
          <g class="lt-links">
            <path
              v-for="(link, i) in (layout?.links ?? []).filter(l => !l.target.data.isToggle)"
              :key="i"
              :d="edgePath(link.source, link.target)"
              fill="none"
              :stroke="edgeLineStyle(link.target).stroke"
              :stroke-width="edgeLineStyle(link.target).strokeWidth"
              :stroke-dasharray="edgeLineStyle(link.target).strokeDasharray || undefined"
              stroke-linecap="round"
            />
          </g>

          <!-- ── Nodes ── -->
          <g class="lt-nodes">
            <g
              v-for="node in layout?.nodes ?? []"
              :key="node.data.id"
              :transform="`translate(${node.svgX},${node.svgY})`"
              class="lt-node"
              :class="{
                'lt-node--toggle': node.data.isToggle,
                'lt-node--serial': node.data.isSerial,
                'lt-node--selected': selectedSet.has(node.data.id),
              }"
              @click="handleClick(node)"
            >
              <!-- ─ Serial diamond ─ -->
              <template v-if="node.data.isSerial">
                <path :d="diamondPath()" :fill="NODE_COLORS.serial" opacity="0.9" />
                <text
                  :x="SERIAL_R + 5"
                  y="0"
                  dominant-baseline="middle"
                  font-size="10"
                  fill="#64748b"
                  font-family="monospace"
                >{{ node.data.name }}</text>
              </template>

              <!-- ─ Toggle pill ([-] or [+N]) ─ -->
              <template v-else-if="node.data.isToggle">
                <!-- Shadow -->
                <rect v-bind="shadowAttrs(node.data.cardW)"
                      :filter="`url(#lt-shd-toggle)`"
                      fill="white" />
                <!-- Pill body -->
                <rect
                  :x="-node.data.cardW/2" :y="-CARD_H/2"
                  :width="node.data.cardW" :height="CARD_H"
                  :rx="CARD_H/2"
                  :fill="node.data.isToggle === 'minus' ? 'rgb(224,231,255)' : 'rgb(254,243,199)'"
                  :stroke="node.data.isToggle === 'minus' ? 'rgb(129,140,248)' : 'rgb(245,158,11)'"
                  stroke-width="1.5"
                />
                <text
                  x="0" y="0"
                  text-anchor="middle"
                  dominant-baseline="middle"
                  font-size="12"
                  font-weight="700"
                  :fill="node.data.isToggle === 'minus' ? 'rgb(67,56,202)' : 'rgb(146,64,14)'"
                >{{ node.data.name }}</text>
              </template>

              <!-- ─ Content card ─ -->
              <template v-else>
                <!-- Shadow layer -->
                <rect
                  v-bind="shadowAttrs(node.data.cardW)"
                  :filter="`url(#${selectedSet.has(node.data.id) ? 'lt-shd-selected' : 'lt-shd-' + node.data.type})`"
                  fill="white"
                />
                <!-- Left colour stripe (rounded on left) -->
                <path
                  :d="stripePath(node.data.cardW)"
                  :fill="nodeColor(node.data.type)"
                />
                <!-- Card body (tinted white, rounded on right) -->
                <path
                  :d="bodyPath(node.data.cardW)"
                  :fill="selectedSet.has(node.data.id) ? (CARD_BG[node.data.type] || '#f8fafc') : (CARD_BG[node.data.type] || '#f8fafc')"
                />
                <!-- Selection border overlay -->
                <rect
                  v-if="selectedSet.has(node.data.id)"
                  v-bind="shadowAttrs(node.data.cardW)"
                  fill="none"
                  :stroke="nodeColor(node.data.type)"
                  stroke-width="2.5"
                />

                <!-- Type badge -->
                <g v-if="badgeInfo(node.data.type, node.data.cardW)" :transform="`translate(0,0)`">
                  <rect
                    :x="badgeInfo(node.data.type, node.data.cardW)!.bx"
                    :y="-BADGE_H/2"
                    :width="badgeInfo(node.data.type, node.data.cardW)!.bw"
                    :height="BADGE_H"
                    :rx="3"
                    :fill="nodeColor(node.data.type)"
                  />
                  <text
                    :x="badgeInfo(node.data.type, node.data.cardW)!.bx + badgeInfo(node.data.type, node.data.cardW)!.bw / 2"
                    y="0"
                    text-anchor="middle"
                    dominant-baseline="middle"
                    font-size="9"
                    font-weight="700"
                    fill="white"
                    font-family="system-ui, sans-serif"
                  >{{ badgeInfo(node.data.type, node.data.cardW)!.label }}</text>
                </g>

                <!-- Node label text (relation tag + name) -->
                <text
                  :x="textX(node.data.type, node.data.cardW)"
                  y="0"
                  dominant-baseline="middle"
                  font-size="11.5"
                  font-family="system-ui, ui-sans-serif, sans-serif"
                  :font-weight="selectedSet.has(node.data.id) ? '700' : '500'"
                >
                  <!-- Relation tag in muted colour -->
                  <tspan
                    v-if="node.data.relationTag"
                    :fill="EDGE_TAG_COLOR[node.data.edgeType] || '#94a3b8'"
                    font-size="10"
                    font-weight="500"
                  >{{ node.data.relationTag }} </tspan>
                  <!-- Node name -->
                  <tspan
                    :fill="selectedSet.has(node.data.id) ? '#0f172a' : '#1e293b'"
                    font-family="ui-monospace, monospace"
                  >{{ node.data.name }}</tspan>
                </text>
              </template>
            </g>
          </g>

        </g><!-- /lt-zoom -->
      </svg>
    </div>

    <!-- Relation table -->
    <details v-if="relationRows.length > 0" class="lt-relation-details">
      <summary class="lt-relation-summary">關係清單（{{ relationRows.length }}）</summary>
      <div class="query-tool-table-wrap short lt-relation-table-wrap">
        <table class="query-tool-table">
          <thead><tr><th>來源批次</th><th>目標批次</th><th>關係</th></tr></thead>
          <tbody>
            <tr v-for="row in pagedRelationRows" :key="row.key">
              <td class="lt-rel-cell mono">{{ row.fromName }}</td>
              <td class="lt-rel-cell mono">{{ row.toName }}</td>
              <td class="lt-rel-cell">{{ row.edgeLabel }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControl v-if="relationTotalPages > 1" v-model="relationPage" :total-pages="relationTotalPages" :info-text="`第 ${relationPage}/${relationTotalPages} 頁，共 ${relationRows.length} 筆`" />
    </details>

    <!-- Not-found warning -->
    <div v-if="notFound.length > 0" class="query-tool-success lt-not-found">
      未命中：{{ (notFound as string[]).join(', ') }}
    </div>

    <!-- Selection chips -->
    <div v-if="selectedContainerIds.length > 0" class="query-tool-success lt-selected-bar">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="mr-1 text-xs font-medium" style="color:var(--brand-800)">已選 {{ selectedContainerIds.length }} 個節點</span>
        <span
          v-for="cid in (selectedContainerIds as string[]).slice(0, 8)"
          :key="cid"
          class="lt-chip"
        >
          {{ (props.nameMap as Map<string,string>)?.get?.(cid) || cid }}
          <button type="button" class="lt-chip-x" @click="removeSelection(cid)">×</button>
        </span>
        <span v-if="selectedContainerIds.length > 8" class="text-xs" style="color:var(--brand-600)">+{{ selectedContainerIds.length - 8 }} 更多</span>
      </div>
    </div>

  </div></section>
</template>

<style scoped>
/* Override ui-card-body default padding — keep this component compact */
section.ui-card > .ui-card-body {
  padding: 10px 16px;
}

/* Canvas wrapper — fixed viewport, pan/zoom inside */
.lt-canvas-wrap {
  position: relative;
  overflow: hidden;
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 10px;
  background: #f9fafb;
  cursor: grab;
  height: 640px;
}
.lt-canvas-wrap:active { cursor: grabbing; }

.lt-svg {
  display: block;
  width: 100%;
  height: 100%;
  user-select: none;
}

/* Node cursor */
.lt-node { cursor: pointer; transition: opacity 0.15s; }
.lt-node:hover { opacity: 0.88; }
.lt-node--toggle { cursor: pointer; }
.lt-node--serial { cursor: default; }

/* Compact toolbar row (no title block above it) */
.lt-toolbar-row {
  margin-bottom: 10px;
}
.lt-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: theme('spacing.token.p8');
}

/* Legend */
.lt-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 10px;
  color: theme('colors.text.subtle');
}
.lt-legend-item { display: inline-flex; align-items: center; gap: 4px; }
.lt-legend-dot {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.lt-legend-diamond {
  display: inline-block;
  width: 8px; height: 8px;
  border: 1.5px solid;
  transform: rotate(45deg);
  flex-shrink: 0;
}
.lt-legend-line {
  display: inline-block;
  width: 18px; height: 0;
  border-top: 1.5px solid #94a3b8;
}
.lt-legend-line--dashed { border-style: dashed; }
.lt-legend-line--dotted { border-style: dotted; }

/* Hint text */
.lt-hint { font-size: 11px; }
.lt-placeholder { padding: theme('spacing.token.p48') theme('spacing.token.p12'); text-align: center; }

/* Relation table */
.lt-relation-details {
  margin-top: theme('spacing.token.p12');
  border: 1px solid var(--border);
  border-radius: 8px;
  background: theme('colors.surface.muted');
  padding: theme('spacing.token.p8') theme('spacing.token.p12');
}
.lt-relation-summary { cursor: pointer; font-size: 12px; font-weight: 600; color: theme('colors.text.secondary'); }
.lt-relation-table-wrap { margin-top: theme('spacing.token.p8'); max-height: 224px; }
.lt-rel-cell { font-size: 11px; }
.lt-rel-cell.mono { font-family: monospace; }

/* Warnings */
.lt-not-found {
  border-color: theme('colors.token.hfde68a');
  background: theme('colors.token.hfefce8');
  color: theme('colors.token.h92400e');
  margin-top: theme('spacing.token.p8');
}
.lt-selected-bar {
  border-color: theme('colors.brand.100');
  background: rgba(238,242,255,0.6);
  color: inherit;
  margin-top: theme('spacing.token.p8');
}

/* Selection chips */
.lt-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border-radius: 9999px;
  border: 1px solid theme('colors.brand.100');
  background: white;
  padding: 1px 4px 1px 8px;
  font-family: monospace;
  font-size: 11px;
  color: theme('colors.brand.800');
}
.lt-chip-x {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px;
  border: none; border-radius: 50%; background: transparent;
  color: theme('colors.brand.500'); font-size: 13px; cursor: pointer; padding: 0;
  transition: background 0.15s;
}
.lt-chip-x:hover { background: theme('colors.brand.100'); color: theme('colors.brand.700'); }
</style>
