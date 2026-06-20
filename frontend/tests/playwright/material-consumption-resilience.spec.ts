/**
 * Resilience tests: material-consumption page
 * Change: material-part-consumption
 * Tier 1 — run in CI pre-merge
 *
 * Tests:
 *   test_spool_miss_410_triggers_client_requery
 *   test_filter_options_error_shows_inline_error
 *   test_detail_worker_absent_shows_pending_state
 */

import { test, expect, Page } from '@playwright/test';

const AUTH_MOCKS = {
  me: { success: true, data: { username: 'testuser', role: 'user' } },
  pages: { success: true, data: [] },
};

async function selectParts(page: Page, parts: string[]) {
  await page.waitForSelector('[data-testid="material-parts-select"] .multi-select-trigger:not([disabled])', { timeout: 45_000 });
  await page.locator('[data-testid="material-parts-select"] .multi-select-trigger').click();
  for (const part of parts) {
    await page.locator('.multi-select-search').fill(part);
    await page.locator('.multi-select-option').filter({ hasText: part }).first().click();
    await page.locator('.multi-select-search').fill('');
  }
  await page.locator('.multi-select-dropdown button:has-text("關閉")').click();
}

const MOCK_PORTAL_NAV = {
  drawers: [
    {
      id: 'drawer',
      name: '查詢工具',
      order: 3,
      admin_only: false,
      pages: [{ route: '/material-consumption', name: '原物料用量查詢', status: 'released', order: 6 }],
    },
  ],
  is_admin: false,
  admin_user: null,
  admin_links: { logout: null, pages: null, dashboard: null, performance: null },
  diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
  portal_spa_enabled: false,
  features: { ai_query_enabled: false },
};

async function setupAuthMocks(page: Page) {
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AUTH_MOCKS.me) })
  );
  await page.route('**/api/pages**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AUTH_MOCKS.pages) })
  );
  // 200ms delay lets the Vue Router initial navigation commit before addRoute fires
  await page.route('**/api/portal/navigation**', async (route) => {
    await new Promise((r) => setTimeout(r, 200));
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PORTAL_NAV) });
  });
}

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/portal-shell/material-consumption`;

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    parts: [{ name: 'PartA' }],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_QUERY_RESULT = {
  success: true,
  data: {
    query_id: 'resilience-query-id',
    kpi: { total_consumed: 1000, total_required: 1100, efficiency_pct: 90.9, lot_count: 5, workorder_count: 2 },
    trend: [{ period: '2026-W01', material_part: 'PartA', total_consumed: 1000 }],
    type_breakdown: [],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

test('test_spool_miss_410_triggers_client_requery', async ({ page }) => {
  await setupAuthMocks(page);
  await page.route('**/api/material-consumption/filter-options', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_FILTER_OPTIONS) });
  });

  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_QUERY_RESULT) });
  });

  // First view call returns 410 (spool miss / CACHE_EXPIRED)
  let viewCallCount = 0;
  await page.route('**/api/material-consumption/view**', (route) => {
    viewCallCount++;
    if (viewCallCount === 1) {
      route.fulfill({
        status: 410,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'CACHE_EXPIRED', message: '快取已過期，請重新查詢' },
          meta: {},
        }),
      });
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_QUERY_RESULT) });
    }
  });

  await page.goto(PAGE_URL);

  // Run initial query
  await selectParts(page, ['PartA']);
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');
  await page.waitForSelector('.trend-chart-container', { timeout: 10000 });

  // Switch granularity to trigger /view which returns 410
  await page.click('[data-granularity="month"]');
  await page.waitForTimeout(1000);

  // UI should show a re-query prompt or error message
  const errorEl = page.locator('.error-banner-wrap, [role="alert"], [data-testid="requery-prompt"]');
  await expect(errorEl).toBeVisible({ timeout: 5000 });
});

test('test_filter_options_error_shows_inline_error', async ({ page }) => {
  await setupAuthMocks(page);
  // filter-options endpoint returns 500
  await page.route('**/api/material-consumption/filter-options', (route) => {
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'INTERNAL_ERROR', message: '伺服器內部錯誤' },
        meta: {},
      }),
    });
  });

  await page.goto(PAGE_URL);
  await page.waitForTimeout(2000);

  // Inline error (ErrorBanner) should be visible
  const errorBanner = page.locator('.error-banner-wrap, [role="alert"]');
  await expect(errorBanner).toBeVisible({ timeout: 5000 });
});

test('test_detail_worker_absent_shows_pending_state', async ({ page }) => {
  await setupAuthMocks(page);
  await page.route('**/api/material-consumption/filter-options', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_FILTER_OPTIONS) });
  });

  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_QUERY_RESULT) });
  });

  // Detail returns 202 async
  await page.route('**/api/material-consumption/detail', (route) => {
    route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { async: true, job_id: 'job-pending-001' },
        meta: {},
      }),
    });
  });

  // Job status always returns pending (worker absent)
  await page.route('**/api/material-consumption/detail/job/job-pending-001', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { status: 'pending' }, meta: {} }),
    });
  });

  await page.goto(PAGE_URL);

  await selectParts(page, ['PartA']);
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');
  await page.waitForSelector('.trend-chart-container', { timeout: 10000 });

  // Click Detail tab — detail auto-loads on query submit (db870aa0)
  await page.click('[data-testid="tab-detail"]');
  await page.waitForTimeout(1000);

  // UI should show a pending/loading state
  const pendingEl = page.locator(
    '[data-testid="detail-pending-state"], .loading-overlay, [data-testid="loading-spinner"]'
  );
  await expect(pendingEl).toBeVisible({ timeout: 5000 });
});
