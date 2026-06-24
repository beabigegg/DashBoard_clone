/**
 * Navigation Manifest — frontend/src/portal-shell/navigationManifest.js
 *
 * Single source of truth for navigation STRUCTURE (drawer grouping, ordering,
 * display names). No runtime write path.
 *
 * Contract: data-shape-contract.md §3.11b
 * Baseline:  specs/changes/nav-config-to-code/current-behavior.md
 *
 * Rules:
 *   - Every route key MUST exist in nativeModuleRegistry.js (mount gate).
 *   - drawer orders MUST be distinct integers (1..6).
 *   - page orders MUST be distinct within each drawer.
 *   - displayName values are verbatim from current-behavior.md (AC-1/AC-5).
 *   - Standalone routes (/, /wip-detail, /hold-detail, /anomaly-overview)
 *     have drawerId: null — they are in STANDALONE_DRILLDOWN_ROUTES.
 *   - Only /admin/dashboard has defaultStatus: 'dev'; all others use 'released'
 *     (or omit — absence defaults to 'released').
 *   - Do NOT duplicate nativeModuleRegistry or routeContracts policy fields.
 */

/** @type {Array<{id: string, name: string, order: number, admin_only: boolean}>} */
export const drawers = Object.freeze([
  { id: 'reports',         name: '即時報表', order: 1, admin_only: false },
  { id: 'history-reports', name: '歷史報表', order: 2, admin_only: false },
  { id: 'query-tools',     name: '查詢工具', order: 3, admin_only: false },
  { id: 'trace-tools',     name: '追溯工具', order: 4, admin_only: false },
  { id: 'dev-tools',       name: '開發工具', order: 5, admin_only: true  },
  { id: 'eap-analysis',    name: 'EAP',      order: 6, admin_only: false },
]);

/**
 * Map of route → {drawerId, order, displayName, defaultStatus?}
 *
 * Drawer membership and page order reproduce current-behavior.md exactly.
 * Within trace-tools: /query-tool=1, /mid-section-defect=2, /material-trace=3
 * (resolves the order-3 tie from current-behavior.md via explicit distinct orders).
 *
 * @type {Record<string, {drawerId: string|null, order: number, displayName: string, defaultStatus?: string}>}
 */
export const routes = Object.freeze({
  // ── 即時報表 (reports, order 1) ──────────────────────────────────────────
  '/wip-overview': {
    drawerId: 'reports',
    order: 1,
    displayName: 'WIP 即時概況',
  },
  '/hold-overview': {
    drawerId: 'reports',
    order: 2,
    displayName: 'Hold 即時概況',
  },
  '/resource': {
    drawerId: 'reports',
    order: 4,
    displayName: '設備即時概況',
  },
  '/qc-gate': {
    drawerId: 'reports',
    order: 6,
    displayName: 'QC-GATE 狀態',
  },

  // ── 歷史報表 (history-reports, order 2) ─────────────────────────────────
  '/hold-history': {
    drawerId: 'history-reports',
    order: 3,
    displayName: 'Hold 歷史績效',
  },
  '/resource-history': {
    drawerId: 'history-reports',
    order: 5,
    displayName: '設備歷史績效',
  },
  '/downtime-analysis': {
    drawerId: 'history-reports',
    order: 6,
    displayName: '設備停機分析',
  },

  // ── 查詢工具 (query-tools, order 3) ─────────────────────────────────────
  '/reject-history': {
    drawerId: 'query-tools',
    order: 1,
    displayName: '報廢歷史查詢',
  },
  '/job-query': {
    drawerId: 'query-tools',
    order: 2,
    displayName: '設備維修查詢',
  },
  '/production-history': {
    drawerId: 'query-tools',
    order: 3,
    displayName: '生產歷程查詢',
  },
  '/yield-alert-center': {
    drawerId: 'query-tools',
    order: 4,
    displayName: '良率查詢',
  },
  '/material-consumption': {
    drawerId: 'query-tools',
    order: 6,
    displayName: '原物料用量查詢',
  },

  // ── 追溯工具 (trace-tools, order 4) ─────────────────────────────────────
  // Explicit distinct orders resolve the order-3 tie from current-behavior.md.
  '/query-tool': {
    drawerId: 'trace-tools',
    order: 1,
    displayName: '批次追蹤工具',
  },
  '/mid-section-defect': {
    drawerId: 'trace-tools',
    order: 2,
    displayName: '製程不良追溯分析',
  },
  '/material-trace': {
    drawerId: 'trace-tools',
    order: 3,
    displayName: '原物料追溯查詢',
  },

  // ── 開發工具 (dev-tools, order 5, admin_only) ───────────────────────────
  '/admin/pages': {
    drawerId: 'dev-tools',
    order: 1,
    displayName: '頁面管理',
  },
  '/admin/dashboard': {
    drawerId: 'dev-tools',
    order: 2,
    displayName: '管理儀表板',
    defaultStatus: 'dev',
  },

  // ── EAP (eap-analysis, order 6) ─────────────────────────────────────────
  '/eap-alarm': {
    drawerId: 'eap-analysis',
    order: 1,
    displayName: 'EAP ALARM 分析',
  },

  // ── Standalone / drilldown routes (no drawer) ───────────────────────────
  // These are code-owned by STANDALONE_DRILLDOWN_ROUTES in navigationState.js.
  '/': {
    drawerId: null,
    order: 0,
    displayName: '首頁',
  },
  '/wip-detail': {
    drawerId: null,
    order: 0,
    displayName: 'WIP 明細',
  },
  '/hold-detail': {
    drawerId: null,
    order: 0,
    displayName: 'Hold 明細',
  },
  '/anomaly-overview': {
    drawerId: null,
    order: 0,
    displayName: '異常概覽',
  },
});
