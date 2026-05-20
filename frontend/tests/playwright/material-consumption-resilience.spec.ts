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

const BASE_URL = 'http://localhost:5173';
const PAGE_URL = `${BASE_URL}/portal-shell/material-consumption`;

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    workcenter_groups: ['WCG-1'],
    primary_categories: ['CAT-A'],
    pj_types: ['TypeX'],
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
  await page.fill('[data-testid="material-parts-input"]', 'PartA');
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

  await page.fill('[data-testid="material-parts-input"]', 'PartA');
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');
  await page.waitForSelector('.trend-chart-container', { timeout: 10000 });

  // Click Detail tab and submit
  await page.click('[data-testid="tab-detail"]');
  await page.click('[data-testid="detail-submit-button"]');
  await page.waitForTimeout(1000);

  // UI should show a pending/loading state
  const pendingEl = page.locator(
    '[data-testid="detail-pending-state"], .loading-overlay, [data-testid="loading-spinner"]'
  );
  await expect(pendingEl).toBeVisible({ timeout: 5000 });
});
