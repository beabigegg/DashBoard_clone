/**
 * E2E tests: admin-pages page (頁面管理)
 *
 * Scenarios covered:
 *   happy path      — page loads with drawer management and pages panels
 *   drawer table    — drawers render in table after API response
 *   pages table     — pages render in table after API response
 *   create drawer   — fill name + click "新增抽屜" triggers POST
 *   page status     — status button renders as Released/Dev badge
 *   resilience      — API error shows error panel
 *
 * Network strategy:
 *   All API mocked. Standalone page at /admin/pages.
 *   Admin auth: /api/auth/me returns is_admin=true.
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
// Navigate to portal-shell home; the shell auto-navigates to the first drawer page
// (/admin/pages) when at route '/'. Navigating directly to /portal-shell/admin/pages
// triggers a NavigationDuplicated error (same path re-replace) that resets routing.
const PAGE_URL = `${BASE_URL}/portal-shell`;

const MOCK_DRAWERS = {
  success: true,
  data: {
    drawers: [
      { id: 'live', name: '即時報表', order: 1, admin_only: false },
      { id: 'history', name: '歷史查詢', order: 2, admin_only: false },
    ],
  },
};

const MOCK_PAGES = {
  success: true,
  data: {
    pages: [
      { route: '/wip-overview', name: 'WIP 即時', status: 'released', drawer_id: 'live', order: 1 },
      { route: '/hold-history', name: 'Hold 歷史', status: 'released', drawer_id: 'history', order: 2 },
      { route: '/downtime-analysis', name: '停機分析', status: 'dev', drawer_id: null, order: null },
    ],
  },
};

const MOCK_CREATE_DRAWER_RESP = {
  success: true,
  data: { id: 'new-drawer', name: '測試抽屜', order: 3, admin_only: false },
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

  // Portal-shell requires navigation config on boot.
  // Include /admin/pages in drawers so the router adds it as a dynamic route,
  // which triggers the shell-fallback → replace() re-navigation into NativeRouteView.
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        drawers: [
          {
            id: 'admin',
            name: '管理',
            order: 99,
            admin_only: true,
            pages: [
              { route: '/admin/pages', name: '頁面管理', status: 'released', order: 1 },
            ],
          },
        ],
        is_admin: true,
        admin_user: { username: 'admin', displayName: 'Admin User' },
        admin_links: { logout: '/api/auth/logout', dashboard: '/admin/dashboard' },
        diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
        portal_spa_enabled: false,
        features: { ai_query_enabled: false },
      }),
    }),
  );

  await page.route('**/admin/api/drawers**', (route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_CREATE_DRAWER_RESP),
      });
    } else {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DRAWERS),
      });
    }
  });

  await page.route('**/admin/api/pages**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PAGES),
    }),
  );
}

async function gotoAdminPagesPage(page: Page): Promise<void> {
  // Navigate to portal-shell home; the shell auto-navigates to the first drawer
  // page (/admin/pages) when the nav config is returned. Navigating directly to
  // /portal-shell/admin/pages causes NavigationDuplicated (same-path re-replace).
  await page.goto(PAGE_URL).catch(() => {});
  await page.waitForSelector('[data-testid="admin-pages-app"]', { timeout: 30_000 });
  await page.waitForSelector('.empty-state:has-text("載入中...")', { state: 'detached', timeout: 15_000 }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_with_panels', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // Both panels should be visible
  const panelTitles = await page.locator('.panel-title').allTextContents();
  expect(panelTitles.some((t) => t.includes('抽屜管理'))).toBe(true);
  expect(panelTitles.some((t) => t.includes('所有頁面'))).toBe(true);
});

test('test_drawer_table_renders_rows', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // Drawer management table shows drawer IDs in the ID column (name is in an <input>)
  await page.waitForSelector('[data-testid="create-drawer-name"]', { timeout: 10_000 });
  const tableText = await page.locator('.panel').first().textContent();
  expect(tableText).toContain('live');
  expect(tableText).toContain('history');
});

test('test_pages_table_renders_rows', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  await page.waitForSelector('[data-testid="create-drawer-name"]', { timeout: 10_000 });
  // Second panel contains pages table
  const panelTexts = await page.locator('.panel').allTextContents();
  const pagesPanel = panelTexts.find((t) => t.includes('/wip-overview'));
  expect(pagesPanel).toBeTruthy();
  expect(pagesPanel).toContain('/hold-history');
});

test('test_create_drawer_form_visible', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  await expect(page.locator('[data-testid="create-drawer-name"]')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid="create-drawer-btn"]')).toBeVisible();
});

test('test_create_drawer_button_triggers_post', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);

  const postRequests: string[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/admin/api/drawers') && req.method() === 'POST') {
      postRequests.push(req.url());
    }
  });

  await page.locator('[data-testid="create-drawer-name"]').fill('測試抽屜');
  await page.locator('[data-testid="create-drawer-btn"]').click();
  await page.waitForTimeout(1_000);
  expect(postRequests.length).toBeGreaterThanOrEqual(1);
});

test('test_page_status_badge_renders', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  await page.waitForSelector('[data-testid="create-drawer-name"]', { timeout: 10_000 });
  // Pages panel has status buttons (released/dev)
  const statusBtns = page.locator('.status-badge, .status-released, .status-dev');
  const count = await statusBtns.count();
  expect(count).toBeGreaterThanOrEqual(2); // At least the released/dev pages
});

test('test_page_header_with_title', async ({ page }) => {
  await setupMocks(page);
  await gotoAdminPagesPage(page);
  // Scope to admin-pages app to avoid grabbing portal-shell nav h1 ("MES 報表入口")
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
        drawers: [{ id: 'admin', name: '管理', order: 99, admin_only: true,
          pages: [{ route: '/admin/pages', name: '頁面管理', status: 'released', order: 1 }] }],
        is_admin: true, admin_links: {}, portal_spa_enabled: false, features: {},
        diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
      }) }),
  );
  await page.route('**/admin/api/drawers**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: 'Server error' }) }),
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
