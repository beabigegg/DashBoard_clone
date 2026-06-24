import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDynamicNavigationState,
  normalizeNavigationDrawers,
} from '../../src/portal-shell/navigationState.js';

import { drawers as MANIFEST_DRAWERS, routes as MANIFEST_ROUTES } from '../../src/portal-shell/navigationManifest.js';


test('normalizeNavigationDrawers enforces deterministic order and visibility', () => {
  const input = [
    {
      id: 'dev-tools',
      name: 'Dev',
      order: 3,
      admin_only: true,
      pages: [{ route: '/admin/pages', name: 'Admin Pages', status: 'dev', order: 2 }],
    },
    {
      id: 'reports',
      name: 'Reports',
      order: 1,
      admin_only: false,
      pages: [
        { route: '/wip-overview', name: 'WIP', status: 'released', order: 2 },
        { route: '/hold-overview', name: 'Hold', status: 'dev', order: 1 },
      ],
    },
  ];

  const nonAdmin = normalizeNavigationDrawers(input, { isAdmin: false });
  assert.deepEqual(nonAdmin.map((d) => d.id), ['reports']);
  assert.deepEqual(nonAdmin[0].pages.map((p) => p.route), ['/wip-overview']);

  const admin = normalizeNavigationDrawers(input, { isAdmin: true });
  assert.deepEqual(admin.map((d) => d.id), ['reports', 'dev-tools']);
  assert.deepEqual(admin[0].pages.map((p) => p.route), ['/hold-overview', '/wip-overview']);
});


test('buildDynamicNavigationState resolves render mode via route contract', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/wip-overview', name: 'WIP', status: 'released', order: 1 }],
      },
      {
        id: 'tools',
        name: 'Tools',
        order: 2,
        pages: [{ route: '/job-query', name: 'Job Query', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: true },
  );

  const renderModes = Object.fromEntries(
    state.dynamicRoutes.map((route) => [route.targetRoute, route.renderMode]),
  );
  assert.equal(renderModes['/wip-overview'], 'native');
  assert.equal(renderModes['/job-query'], 'native');
  assert.equal(state.diagnostics.missingContractRoutes.length, 0);
});


test('buildDynamicNavigationState tracks routes missing from contract and keeps native fallback mode', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/legacy-unknown', name: 'Legacy', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: false },
  );

  assert.deepEqual(state.diagnostics.missingContractRoutes, ['/legacy-unknown']);
  assert.equal(state.dynamicRoutes[0].renderMode, 'native');
  assert.deepEqual(state.allowedPaths.sort(), ['/', '/legacy-unknown']);
});


test('buildDynamicNavigationState can include standalone drilldown routes without drawer entries', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/wip-overview', name: 'WIP', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: false, includeStandaloneDrilldown: true },
  );

  const targetRoutes = state.dynamicRoutes.map((route) => route.targetRoute);
  assert.equal(targetRoutes.includes('/wip-overview'), true);
  assert.equal(targetRoutes.includes('/wip-detail'), true);
  assert.equal(targetRoutes.includes('/hold-detail'), true);
  assert.equal(state.allowedPaths.includes('/wip-detail'), true);
  assert.equal(state.allowedPaths.includes('/hold-detail'), true);
});


test('buildDynamicNavigationState resolves admin routes with correct contract metadata', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'dev-tools',
        name: 'Dev',
        order: 1,
        admin_only: true,
        pages: [{ route: '/admin/pages', name: 'Admin Pages', status: 'dev', order: 1 }],
      },
    ],
    { isAdmin: true },
  );

  assert.equal(state.diagnostics.missingContractRoutes.length, 0);
  assert.equal(state.dynamicRoutes.length, 1);
  assert.equal(state.dynamicRoutes[0].targetRoute, '/admin/pages');
  assert.equal(state.dynamicRoutes[0].renderMode, 'native');
  assert.equal(state.dynamicRoutes[0].visibilityPolicy, 'admin_only');
  assert.equal(state.dynamicRoutes[0].scope, 'in-scope');
});


// ============================================================================
// AC-1 / AC-5 manifest nav-tree parity tests (nav-config-to-code)
// ============================================================================

// Build the full released statusMap (all routes from manifest default to released
// except /admin/dashboard which is 'dev')
function buildFullStatusMap() {
  const map = {};
  for (const [route, meta] of Object.entries(MANIFEST_ROUTES)) {
    map[route] = meta.defaultStatus || 'released';
  }
  return map;
}

test('test_manifest_drawer_ids_use_clean_names (AC-5)', () => {
  const ids = MANIFEST_DRAWERS.map((d) => d.id);
  assert.ok(!ids.includes('drawer'), 'should not contain legacy id "drawer"');
  assert.ok(!ids.includes('drawer-2'), 'should not contain legacy id "drawer-2"');
  assert.ok(!ids.includes('drawer-3'), 'should not contain legacy id "drawer-3"');
  assert.ok(!ids.includes('test'), 'should not contain empty "test" drawer id');
  assert.ok(ids.includes('history-reports'), '"history-reports" should be present');
  assert.ok(ids.includes('query-tools'), '"query-tools" should be present');
  assert.ok(ids.includes('trace-tools'), '"trace-tools" should be present');
});

test('test_manifest_excludes_test_drawer (AC-5)', () => {
  const ids = MANIFEST_DRAWERS.map((d) => d.id);
  assert.ok(!ids.includes('test'), '"test" drawer must not exist in manifest');
});

test('test_manifest_display_names_verbatim (AC-5)', () => {
  // Spot-check key display names from current-behavior.md
  assert.equal(MANIFEST_ROUTES['/wip-overview']?.displayName, 'WIP 即時概況');
  assert.equal(MANIFEST_ROUTES['/hold-overview']?.displayName, 'Hold 即時概況');
  assert.equal(MANIFEST_ROUTES['/resource']?.displayName, '設備即時概況');
  assert.equal(MANIFEST_ROUTES['/qc-gate']?.displayName, 'QC-GATE 狀態');
  assert.equal(MANIFEST_ROUTES['/hold-history']?.displayName, 'Hold 歷史績效');
  assert.equal(MANIFEST_ROUTES['/resource-history']?.displayName, '設備歷史績效');
  assert.equal(MANIFEST_ROUTES['/downtime-analysis']?.displayName, '設備停機分析');
  assert.equal(MANIFEST_ROUTES['/reject-history']?.displayName, '報廢歷史查詢');
  assert.equal(MANIFEST_ROUTES['/job-query']?.displayName, '設備維修查詢');
  assert.equal(MANIFEST_ROUTES['/production-history']?.displayName, '生產歷程查詢');
  assert.equal(MANIFEST_ROUTES['/yield-alert-center']?.displayName, '良率查詢');
  assert.equal(MANIFEST_ROUTES['/material-consumption']?.displayName, '原物料用量查詢');
  assert.equal(MANIFEST_ROUTES['/query-tool']?.displayName, '批次追蹤工具');
  assert.equal(MANIFEST_ROUTES['/mid-section-defect']?.displayName, '製程不良追溯分析');
  assert.equal(MANIFEST_ROUTES['/material-trace']?.displayName, '原物料追溯查詢');
  assert.equal(MANIFEST_ROUTES['/admin/pages']?.displayName, '頁面管理');
  assert.equal(MANIFEST_ROUTES['/admin/dashboard']?.displayName, '管理儀表板');
  assert.equal(MANIFEST_ROUTES['/eap-alarm']?.displayName, 'EAP ALARM 分析');
});

test('test_manifest_page_memberships_verbatim (AC-5)', () => {
  // Verify drawer membership assignments from current-behavior.md
  assert.equal(MANIFEST_ROUTES['/wip-overview']?.drawerId, 'reports');
  assert.equal(MANIFEST_ROUTES['/hold-overview']?.drawerId, 'reports');
  assert.equal(MANIFEST_ROUTES['/resource']?.drawerId, 'reports');
  assert.equal(MANIFEST_ROUTES['/qc-gate']?.drawerId, 'reports');

  assert.equal(MANIFEST_ROUTES['/hold-history']?.drawerId, 'history-reports');
  assert.equal(MANIFEST_ROUTES['/resource-history']?.drawerId, 'history-reports');
  assert.equal(MANIFEST_ROUTES['/downtime-analysis']?.drawerId, 'history-reports');

  assert.equal(MANIFEST_ROUTES['/reject-history']?.drawerId, 'query-tools');
  assert.equal(MANIFEST_ROUTES['/job-query']?.drawerId, 'query-tools');
  assert.equal(MANIFEST_ROUTES['/production-history']?.drawerId, 'query-tools');
  assert.equal(MANIFEST_ROUTES['/yield-alert-center']?.drawerId, 'query-tools');
  assert.equal(MANIFEST_ROUTES['/material-consumption']?.drawerId, 'query-tools');

  assert.equal(MANIFEST_ROUTES['/query-tool']?.drawerId, 'trace-tools');
  assert.equal(MANIFEST_ROUTES['/mid-section-defect']?.drawerId, 'trace-tools');
  assert.equal(MANIFEST_ROUTES['/material-trace']?.drawerId, 'trace-tools');

  assert.equal(MANIFEST_ROUTES['/admin/pages']?.drawerId, 'dev-tools');
  assert.equal(MANIFEST_ROUTES['/admin/dashboard']?.drawerId, 'dev-tools');

  assert.equal(MANIFEST_ROUTES['/eap-alarm']?.drawerId, 'eap-analysis');
});

test('test_manifest_nav_tree_non_admin_matches_baseline (AC-1)', () => {
  // Non-admin: dev-tools is hidden (admin_only), /admin/dashboard is dev (hidden for non-admin)
  const statusMap = buildFullStatusMap();
  const state = buildDynamicNavigationState(statusMap, { isAdmin: false });

  // Only non-admin-only drawers should appear
  const drawerIds = state.drawers.map((d) => d.id);
  assert.ok(!drawerIds.includes('dev-tools'), 'dev-tools must be hidden for non-admin');
  assert.ok(!drawerIds.includes('test'), 'test drawer must not exist');

  // Expected visible drawers for non-admin (reports, history-reports, query-tools, trace-tools, eap-analysis)
  assert.ok(drawerIds.includes('reports'), 'reports drawer must be visible');
  assert.ok(drawerIds.includes('history-reports'), 'history-reports drawer must be visible');
  assert.ok(drawerIds.includes('query-tools'), 'query-tools drawer must be visible');
  assert.ok(drawerIds.includes('trace-tools'), 'trace-tools drawer must be visible');
  assert.ok(drawerIds.includes('eap-analysis'), 'eap-analysis drawer must be visible');

  // Drawer order must be 1..5 (dev-tools excluded)
  const orders = state.drawers.map((d) => d.order);
  const sortedOrders = [...orders].sort((a, b) => a - b);
  assert.deepEqual(sortedOrders, [1, 2, 3, 4, 6]);

  // Page counts per drawer (from current-behavior.md)
  const byId = Object.fromEntries(state.drawers.map((d) => [d.id, d]));
  assert.equal(byId['reports'].pages.length, 4); // wip, hold, resource, qc-gate
  assert.equal(byId['history-reports'].pages.length, 3); // hold-history, resource-history, downtime
  assert.equal(byId['query-tools'].pages.length, 5); // reject, job, prod, yield, material-consumption
  assert.equal(byId['trace-tools'].pages.length, 3); // query-tool, mid-section, material-trace
  assert.equal(byId['eap-analysis'].pages.length, 1); // eap-alarm
});

test('test_manifest_nav_tree_admin_matches_baseline (AC-1)', () => {
  // Admin: all drawers visible; /admin/dashboard is 'dev' but admin sees it
  const statusMap = buildFullStatusMap(); // includes /admin/dashboard:'dev'
  const state = buildDynamicNavigationState(statusMap, { isAdmin: true });

  const drawerIds = state.drawers.map((d) => d.id);
  // All 6 drawers should be visible for admin
  assert.ok(drawerIds.includes('reports'), 'reports must be visible for admin');
  assert.ok(drawerIds.includes('history-reports'), 'history-reports must be visible for admin');
  assert.ok(drawerIds.includes('query-tools'), 'query-tools must be visible for admin');
  assert.ok(drawerIds.includes('trace-tools'), 'trace-tools must be visible for admin');
  assert.ok(drawerIds.includes('dev-tools'), 'dev-tools must be visible for admin');
  assert.ok(drawerIds.includes('eap-analysis'), 'eap-analysis must be visible for admin');

  // Drawer orders 1..6
  const orders = state.drawers.map((d) => d.order);
  const sortedOrders = [...orders].sort((a, b) => a - b);
  assert.deepEqual(sortedOrders, [1, 2, 3, 4, 5, 6]);

  const byId = Object.fromEntries(state.drawers.map((d) => [d.id, d]));
  // dev-tools: /admin/pages (released), /admin/dashboard (dev — admin can see)
  assert.equal(byId['dev-tools'].pages.length, 2);
  const devRoutes = byId['dev-tools'].pages.map((p) => p.route);
  assert.ok(devRoutes.includes('/admin/pages'), '/admin/pages must be in dev-tools');
  assert.ok(devRoutes.includes('/admin/dashboard'), '/admin/dashboard must be in dev-tools for admin');
});

test('test_drawer_order_is_1_through_6 (AC-1)', () => {
  // Verify manifest drawer orders are exactly 1..6, distinct
  const orders = MANIFEST_DRAWERS.map((d) => d.order).sort((a, b) => a - b);
  assert.deepEqual(orders, [1, 2, 3, 4, 5, 6]);
});

test('test_trace_tools_page_order_is_distinct (AC-1)', () => {
  const tracePages = Object.entries(MANIFEST_ROUTES)
    .filter(([, meta]) => meta.drawerId === 'trace-tools')
    .sort(([, a], [, b]) => a.order - b.order);

  const orders = tracePages.map(([, meta]) => meta.order);
  const unique = new Set(orders);
  assert.equal(unique.size, orders.length, 'trace-tools page orders must be distinct');
  assert.deepEqual(orders, [1, 2, 3]);
});

test('test_non_admin_does_not_see_admin_dashboard_dev_page (AC-1)', () => {
  // /admin/dashboard is defaultStatus:'dev'; non-admin cannot see it
  const statusMap = buildFullStatusMap();
  const state = buildDynamicNavigationState(statusMap, { isAdmin: false });
  const allRoutes = state.dynamicRoutes.map((r) => r.targetRoute);
  assert.ok(!allRoutes.includes('/admin/dashboard'), '/admin/dashboard must be hidden for non-admin');
});

test('test_admin_dashboard_status_is_dev_in_manifest (AC-1)', () => {
  assert.equal(MANIFEST_ROUTES['/admin/dashboard']?.defaultStatus, 'dev');
});

