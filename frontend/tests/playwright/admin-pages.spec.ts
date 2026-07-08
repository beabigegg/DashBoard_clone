/**
 * E2E tests: admin-pages page (頁面管理)
 *
 * Scenarios covered (post nav-config-to-code):
 *   happy path       — page loads with pages panel (no drawer management panel)
 *   pages table      — pages render in table after API response
 *   status toggle    — status badge (Released/Dev) visible and round-trips via PUT
 *   panel title      — shows "所有頁面"
 *   drawer absent    — DrawerManagementPanel NOT in DOM; no GET /admin/api/drawers call
 *   resilience       — API error shows error panel
 *
 * Network strategy:
 *   All API mocked. Standalone page at /admin/pages.
 *   Admin auth: /api/auth/me returns is_admin=true.
 *
 * Changed in nav-config-to-code:
 *   - Removed: drawer creation tests (POST /api/drawers), MOCK_DRAWERS, MOCK_CREATE_DRAWER_RESP
 *   - Removed: tests asserting "抽屜管理" panel title
 *   - Added:  test_drawer_management_panel_absent
 *   - Added:  test_status_toggle_released_to_dev_round_trip (AC-2)
 *   - Updated: navigation mock uses new status-feed shape (statuses map, no drawers)
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/portal-shell`;

// Slim pages list matching the new GET /admin/api/pages shape: {route, status}
const MOCK_PAGES = {
  success: true,
  data: {
    pages: [
      { route: '/wip-overview', status: 'released' },
      { route: '/hold-history', status: 'released' },
      { route: '/downtime-analysis', status: 'dev' },
    ],
  },
};

const MOCK_PAGES_AFTER_TOGGLE = {
  success: true,
  data: {
    pages: [
      { route: '/wip-overview', status: 'dev' },
      { route: '/hold-history', status: 'released' },
      { route: '/downtime-analysis', status: 'dev' },
    ],
  },
};

async function setupMocks(page: Page): Promise<void> {
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { name: 'Admin', role: 'admin', is_admin: true },
      }),
    }),
  );

  // New status-feed shape: statuses map (no drawers)
  // /admin/pages must be in dev-tools drawer in manifest; portal-shell will
  // auto-navigate to first route. We include /admin/pages as non-dev so it renders.
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        statuses: {},            // all routes use manifest defaultStatus (released)
        is_admin: true,
        admin_user: { username: 'admin', displayName: 'Admin User' },
        admin_links: { logout: '/api/auth/logout', dashboard: '/admin/dashboard', pages: '/admin/pages' },
        features: { ai_query_enabled: false },
        diagnostics: {},
      }),
    }),
  );

  await page.route('**/admin/api/pages**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PAGES),
    }),
  );
}

async function gotoAdminPagesPage(page: Page): Promise<void> {
  await page.goto(PAGE_URL).catch(() => {});
  await page.waitForSelector('[data-testid="admin-pages-app"]', { timeout: 30_000 });
  await page.waitForSelector('.empty-state:has-text("載入中...")', { state: 'detached', timeout: 15_000 }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_with_pages_panel', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // Only the pages panel should be visible (no drawer management panel)
  const panelTitles = await page.locator('.panel-title').allTextContents();
  expect(panelTitles.some((t) => t.includes('所有頁面'))).toBe(true);
});

test('test_drawer_management_panel_absent (AC-2/AC-3)', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // "抽屜管理" panel title must NOT be present
  const panelTitles = await page.locator('.panel-title').allTextContents();
  expect(panelTitles.some((t) => t.includes('抽屜管理'))).toBe(false);
  // Drawer create button must NOT be in DOM
  expect(await page.locator('[data-testid="create-drawer-btn"]').count()).toBe(0);
  expect(await page.locator('[data-testid="create-drawer-name"]').count()).toBe(0);
});

test('test_target_permissions_panel_absent (AC-7, move-target-permissions-panel)', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // The "生產達成率 — 目標值編輯權限" panel relocated to admin-dashboard's
  // `permissions` tab and must no longer render on /admin/pages.
  const panelTitles = await page.locator('.panel-title').allTextContents();
  expect(panelTitles.some((t) => t.includes('生產達成率') || t.includes('目標值編輯權限'))).toBe(false);
  expect(await page.locator('[data-testid="pa-permissions-panel"]').count()).toBe(0);
  expect(await page.locator('[data-testid="pa-permissions-toggle"]').count()).toBe(0);
});

test('test_no_get_admin_drawers_request (AC-3)', async ({ page }) => {
  await setupMocks(page);
  const drawerRequests: string[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/admin/api/drawers')) {
      drawerRequests.push(req.url());
    }
  });
  await gotoAdminPagesPage(page);
  await page.waitForTimeout(2_000); // wait for all requests to settle
  expect(drawerRequests.length).toBe(0);
});

test('test_pages_table_renders_rows', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  const panelText = await page.locator('.panel').textContent();
  expect(panelText).toContain('/wip-overview');
  expect(panelText).toContain('/hold-history');
});

test('test_page_status_badge_renders', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  const statusBtns = page.locator('.status-badge, .status-released, .status-dev');
  const count = await statusBtns.count();
  expect(count).toBeGreaterThanOrEqual(2);
});

test('test_status_toggle_released_to_dev_round_trip (AC-2)', async ({ page }) => {
  await setupMocks(page);

  // Track PUT calls
  const putCalls: Array<{ url: string; body: string }> = [];
  page.on('request', (req) => {
    if (req.method() === 'PUT' && req.url().includes('/admin/api/pages')) {
      putCalls.push({ url: req.url(), body: req.postData() ?? '' });
    }
  });

  // After the PUT, return the toggled state
  let callCount = 0;
  await page.route('**/admin/api/pages**', (route) => {
    if (route.request().method() === 'PUT') {
      callCount++;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: {} }),
      });
    } else {
      // GET: first call returns original, subsequent calls return toggled
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(callCount > 0 ? MOCK_PAGES_AFTER_TOGGLE : MOCK_PAGES),
      });
    }
  });

  await gotoAdminPagesPage(page);

  // Click the first Released status badge (wip-overview)
  const firstReleasedBtn = page.locator('button.status-released').first();
  await expect(firstReleasedBtn).toBeVisible({ timeout: 10_000 });
  await firstReleasedBtn.click();

  // Wait for PUT call
  await page.waitForTimeout(1_500);

  expect(putCalls.length).toBeGreaterThanOrEqual(1);
  const putBody = JSON.parse(putCalls[0].body || '{}');
  expect(putBody.status).toBe('dev');
});

test('test_page_header_with_title', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  const headerText = await page.locator('[data-testid="admin-pages-app"] h1').first().textContent();
  expect(headerText).toContain('頁面管理');
});

test('test_api_error_shows_error_panel', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Admin', role: 'admin', is_admin: true } }) }),
  );
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({
        statuses: {},
        is_admin: true,
        admin_links: { logout: '/api/auth/logout', pages: '/admin/pages' },
        features: {},
        diagnostics: {},
      }) }),
  );
  await page.route('**/admin/api/pages**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: 'Server error' }) }),
  );

  await page.goto(`${BASE_URL}/portal-shell`).catch(() => {});
  await page.waitForSelector('[data-testid="admin-pages-app"]', { timeout: 30_000 });
  const errorPanel = page.locator('.error-panel, .error-banner-wrap');
  await expect(errorPanel.first()).toBeVisible({ timeout: 15_000 });
});
