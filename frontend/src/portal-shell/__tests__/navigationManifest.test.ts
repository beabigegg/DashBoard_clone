/**
 * navigationManifest.test.js
 *
 * AC-5: Structural invariants for the navigation manifest.
 *   - Every manifest route exists in nativeModuleRegistry (mount gate).
 *   - defaultStatus:'dev' appears ONLY on /admin/dashboard.
 *   - Drawer ids use clean names (no 'drawer', 'drawer-2', 'drawer-3', 'test').
 *   - Drawer orders are distinct (1..6).
 *   - No empty 'test' drawer.
 */
import { describe, it, expect } from 'vitest';
import { drawers, routes } from '../navigationManifest.js';
import { getNativeModuleLoader } from '../nativeModuleRegistry.js';

describe('navigationManifest structural invariants (AC-5)', () => {
  it('test_all_manifest_routes_exist_in_native_module_registry', () => {
    // Only check routes that are in a drawer or are navigable (not root /)
    const navigableRoutes = Object.entries(routes)
      .filter(([route]) => route !== '/')
      .map(([route]) => route);

    const missing = navigableRoutes.filter((route) => !getNativeModuleLoader(route));
    expect(missing).toEqual([]);
  });

  it('test_default_status_dev_only_on_admin_dashboard', () => {
    const devRoutes = Object.entries(routes)
      .filter(([, meta]) => meta.defaultStatus === 'dev')
      .map(([route]) => route);

    expect(devRoutes).toEqual(['/admin/dashboard']);
  });

  it('test_all_drawer_ids_use_clean_names', () => {
    const ids = drawers.map((d) => d.id);
    expect(ids).not.toContain('drawer');
    expect(ids).not.toContain('drawer-2');
    expect(ids).not.toContain('drawer-3');
    expect(ids).not.toContain('test');
    // Expected clean ids
    expect(ids).toContain('reports');
    expect(ids).toContain('history-reports');
    expect(ids).toContain('query-tools');
    expect(ids).toContain('trace-tools');
    expect(ids).toContain('dev-tools');
    expect(ids).toContain('eap-analysis');
  });

  it('test_drawer_orders_are_distinct', () => {
    const orders = drawers.map((d) => d.order);
    const unique = new Set(orders);
    expect(unique.size).toBe(drawers.length);
    expect(orders.sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('test_no_test_drawer', () => {
    const ids = drawers.map((d) => d.id);
    const names = drawers.map((d) => d.name);
    expect(ids).not.toContain('test');
    expect(names).not.toContain('test');
  });

  it('test_dev_tools_is_admin_only', () => {
    const devTools = drawers.find((d) => d.id === 'dev-tools');
    expect(devTools).toBeDefined();
    expect(devTools.admin_only).toBe(true);
  });

  it('test_all_other_drawers_not_admin_only', () => {
    const nonDevTools = drawers.filter((d) => d.id !== 'dev-tools');
    const allPublic = nonDevTools.every((d) => d.admin_only === false);
    expect(allPublic).toBe(true);
  });

  it('test_page_orders_distinct_within_each_drawer', () => {
    // Group page orders by drawerId
    const ordersByDrawer = {};
    for (const [route, meta] of Object.entries(routes)) {
      if (!meta.drawerId) continue;
      if (!ordersByDrawer[meta.drawerId]) ordersByDrawer[meta.drawerId] = [];
      ordersByDrawer[meta.drawerId].push({ route, order: meta.order });
    }
    for (const [drawerId, pages] of Object.entries(ordersByDrawer)) {
      const orders = pages.map((p) => p.order);
      const unique = new Set(orders);
      expect(unique.size).toBe(orders.length,
        `Drawer '${drawerId}' has duplicate page orders: ${JSON.stringify(pages)}`);
    }
  });

  it('test_trace_tools_page_orders_are_1_2_3', () => {
    const tracePages = Object.entries(routes)
      .filter(([, meta]) => meta.drawerId === 'trace-tools')
      .map(([route, meta]) => ({ route, order: meta.order }))
      .sort((a, b) => a.order - b.order);

    expect(tracePages.map((p) => p.order)).toEqual([1, 2, 3]);
    // order 1 = /query-tool
    expect(tracePages[0].route).toBe('/query-tool');
    // order 2 = /mid-section-defect
    expect(tracePages[1].route).toBe('/mid-section-defect');
    // order 3 = /material-trace
    expect(tracePages[2].route).toBe('/material-trace');
  });

  it('test_display_names_not_empty', () => {
    for (const [route, meta] of Object.entries(routes)) {
      expect(meta.displayName).toBeTruthy(`Route '${route}' has empty displayName`);
    }
  });
});
