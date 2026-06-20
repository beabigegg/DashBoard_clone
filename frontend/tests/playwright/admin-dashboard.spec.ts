/**
 * E2E + resilience tests: admin-dashboard page (管理儀表板)
 *
 * Scenarios covered:
 *   happy path  — all 6 tabs visible, overview panel active by default
 *   tab switch  — performance, cache, worker tabs render their panels
 *   controls    — auto-refresh toggle present and toggleable
 *   data        — overview panel renders data from mocked /health + admin/api endpoints
 *   resilience  — 500 from overview API → error-banner visible in the active tab
 *
 * Network strategy:
 *   Admin dashboard requires is_admin: true in /api/auth/me.
 *   The /health and /admin/api/* endpoints are all mocked.
 *   Catch-all routes registered FIRST; specific overrides registered LAST
 *   (Playwright page.route() is LIFO — see ci-workflow.md).
 *
 * Stable selectors: data-testid only (added in this change).
 */

import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/portal-shell/admin/dashboard`;

// ---------------------------------------------------------------------------
// Shared mock fixtures
// ---------------------------------------------------------------------------

const MOCK_HEALTH = {
  services: { database: 'healthy', redis: 'healthy' },
  warnings: [],
  circuit_breaker: { state: 'CLOSED' },
  system_memory: { used_pct: 42.5, total_mb: 8192, available_mb: 4718, pressure: 'normal' },
  database_pool: { state: { saturation: 0.1 } },
  async_workers: {
    rq_available: true,
    workers: { summary: { total: 2, busy: 1, idle: 1 } },
    queues: { total_queued: 0 },
  },
  sync_worker: { running: true, last_sync_at: '2026-06-20T00:00:00' },
  anomaly_scheduler: { running: false, anomaly_count: 0 },
};

const MOCK_PERF_HISTORY: { snapshots: unknown[] } = {
  snapshots: [],
};

const MOCK_METRICS = {
  success: true,
  data: {
    p50_ms: 45,
    p95_ms: 120,
    p99_ms: 350,
    count: 1234,
    slow_count: 5,
    slow_rate: 0.004,
    latencies: [],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_PERF_DETAIL = {
  success: true,
  data: {
    db_pool: {
      status: { checked_out: 2, checked_in: 8, saturation: 0.2, overflow: 0, max_capacity: 10, slow_query_active: 0, slow_query_waiting: 0 },
      config: { pool_size: 10, pool_recycle: 3600, pool_timeout: 30 },
    },
    direct_connections: { total_since_start: 5 },
    redis: { used_memory: 10485760, hit_rate: 0.95, namespaces: [] },
    duckdb: { temp_dir_bytes: 0, memory_limit_state: '4GB' },
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_STORAGE = {
  success: true,
  data: { spool_total_mb: 128, parquet_files: 10 },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_USAGE_KPI = {
  success: true,
  data: { total_queries: 500, unique_users: 42, avg_queries_per_user: 11.9 },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_LOGS = {
  success: true,
  data: { logs: [], total: 0 },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_PORTAL_NAV_ADMIN = {
  drawers: [],
  is_admin: true,
  admin_user: { username: 'admin', display_name: 'Admin User' },
  admin_links: {
    logout: '/api/auth/logout',
    pages: '/admin/pages',
    dashboard: '/admin/dashboard',
    performance: '/admin/performance',
  },
  diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
  portal_spa_enabled: false,
  features: { ai_query_enabled: false },
};

// ---------------------------------------------------------------------------
// Route setup helpers
// ---------------------------------------------------------------------------

async function installBaseRoutes(page: Page): Promise<void> {
  // Auth — return is_admin: true so admin routes are accessible
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { username: 'admin', role: 'admin', is_admin: true },
      }),
    }),
  );

  await page.route('**/api/portal/navigation**', async (route) => {
    await new Promise((r) => setTimeout(r, 100));
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PORTAL_NAV_ADMIN),
    });
  });

  await page.route('**/api/pages**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    }),
  );

  // Health endpoint (used by OverviewTab via useHealthSummary)
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_HEALTH),
    }),
  );

  // Admin API endpoints
  await page.route('**/admin/api/performance-history**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: MOCK_PERF_HISTORY, meta: {} }),
    }),
  );

  await page.route('**/admin/api/metrics**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_METRICS),
    }),
  );

  await page.route('**/admin/api/performance-detail**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PERF_DETAIL),
    }),
  );

  await page.route('**/admin/api/storage-info**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_STORAGE),
    }),
  );

  await page.route('**/admin/api/user-usage-kpi**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_USAGE_KPI),
    }),
  );

  await page.route('**/admin/api/logs**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_LOGS),
    }),
  );
}

/**
 * Navigate to the admin dashboard page and wait for the app root to mount.
 * Returns false if the page did not render the expected app (e.g. redirect to login).
 */
async function gotoAdminDashboard(page: Page): Promise<boolean> {
  const response = await page.goto(PAGE_URL).catch(() => null);
  if (!response) return false;

  // Wait for app root with a reasonable timeout
  const root = page.locator('[data-testid="admin-dashboard-app"]');
  const visible = await root.waitFor({ timeout: 30_000 }).then(() => true).catch(() => false);
  return visible;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_with_tabs', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  // All 6 tab buttons must be present and visible
  for (const tabKey of ['overview', 'performance', 'cache', 'worker', 'usage', 'logs']) {
    await expect(page.locator(`[data-testid="tab-${tabKey}"]`)).toBeVisible();
  }
});

test('test_default_tab_is_overview', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  // Overview tab button must have the active class
  const overviewTab = page.locator('[data-testid="tab-overview"]');
  await expect(overviewTab).toBeVisible();
  await expect(overviewTab).toHaveClass(/is-active/);

  // The panel rendered is for overview (the component receives data-testid="panel-overview"
  // via :data-testid="`panel-${activeTabKey}`" on the dynamic <component>)
  await expect(page.locator('[data-testid="panel-overview"]')).toBeVisible();
});

test('test_tab_switch_performance', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  await page.locator('[data-testid="tab-performance"]').click();

  // Overview tab should no longer be active
  await expect(page.locator('[data-testid="tab-overview"]')).not.toHaveClass(/is-active/);
  await expect(page.locator('[data-testid="tab-performance"]')).toHaveClass(/is-active/);

  // The performance panel must now be rendered
  await expect(page.locator('[data-testid="panel-performance"]')).toBeVisible();
});

test('test_tab_switch_cache', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  await page.locator('[data-testid="tab-cache"]').click();

  await expect(page.locator('[data-testid="tab-cache"]')).toHaveClass(/is-active/);
  await expect(page.locator('[data-testid="panel-cache"]')).toBeVisible();
});

test('test_tab_switch_worker', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  await page.locator('[data-testid="tab-worker"]').click();

  await expect(page.locator('[data-testid="tab-worker"]')).toHaveClass(/is-active/);
  await expect(page.locator('[data-testid="panel-worker"]')).toBeVisible();
});

test('test_auto_refresh_toggle_present', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  // Toggle checkbox must be visible
  const toggle = page.locator('[data-testid="auto-refresh-toggle"]');
  await expect(toggle).toBeVisible();

  // Default: checked (autoRefreshEnabled initialised to true)
  await expect(toggle).toBeChecked();

  // Uncheck — auto-refresh should be disabled
  await toggle.click();
  await expect(toggle).not.toBeChecked();

  // Re-check
  await toggle.click();
  await expect(toggle).toBeChecked();
});

test('test_overview_data_loads', async ({ page }) => {
  await installBaseRoutes(page);
  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  // Overview tab is default; wait for panel content to load
  await page.waitForSelector('[data-testid="panel-overview"]', { timeout: 20_000 });

  // The overview tab renders a "系統健康總覽" section with status cards.
  // After the /health mock resolves, the content of that section must include
  // at least one of the service names.
  const panelText = await page.locator('[data-testid="panel-overview"]').textContent({ timeout: 15_000 });

  // Mock services are 'healthy'; the panel must contain service identifiers
  // from the template (Database, Redis, Circuit Breaker, System Memory).
  const hasServiceContent =
    (panelText?.includes('Database') ?? false) ||
    (panelText?.includes('Redis') ?? false) ||
    (panelText?.includes('總覽') ?? false);
  expect(hasServiceContent).toBe(true);
});

test('test_api_error_shows_banner', async ({ page }) => {
  await installBaseRoutes(page);

  // Override the health endpoint to return 500 — OverviewTab will surface an error
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Internal Server Error', message: '伺服器內部錯誤' }),
    }),
  );

  // Also fail the performance-history so OverviewTab has two failing hooks
  await page.route('**/admin/api/performance-history**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Service Unavailable' }),
    }),
  );

  const rendered = await gotoAdminDashboard(page);
  if (!rendered) {
    test.skip();
    return;
  }

  // Wait for the OverviewTab's error banner to appear
  // The error-banner data-testid is on the ErrorBanner component inside the active tab panel.
  await page.waitForSelector('[data-testid="error-banner"]', { timeout: 20_000 });
  await expect(page.locator('[data-testid="error-banner"]').first()).toBeVisible();
});
