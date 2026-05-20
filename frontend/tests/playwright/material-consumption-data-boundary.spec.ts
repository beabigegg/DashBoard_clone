/**
 * Data-boundary tests: material-consumption page
 * Change: material-part-consumption
 * Tier 1 — run in CI pre-merge
 *
 * Tests:
 *   test_21_parts_rejected_with_validation_error
 *   test_0_row_result_shows_empty_state
 *   test_wildcard_bare_star_rejected
 *   test_sql_injection_attempt_returns_400
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

async function setupBasicMocks(page: Page) {
  await page.route('**/api/material-consumption/filter-options', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_FILTER_OPTIONS) });
  });
}

test('test_21_parts_rejected_with_validation_error', async ({ page }) => {
  await setupBasicMocks(page);
  await page.goto(PAGE_URL);

  // Enter 21 material parts (one per line)
  const parts = Array.from({ length: 21 }, (_, i) => `Part${String(i + 1).padStart(3, '0')}`);
  await page.fill('[data-testid="material-parts-input"]', parts.join('\n'));
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');

  // Submit button should either be disabled or show validation error
  const submitBtn = page.locator('[data-testid="query-submit-button"]');

  // Check if button is disabled due to validation
  const isDisabled = await submitBtn.isDisabled();
  if (isDisabled) {
    // Button disabled by client-side validation — test passes
    expect(isDisabled).toBe(true);
  } else {
    // Click submit and expect a validation error message
    await submitBtn.click();
    await page.waitForTimeout(500);

    // Should show validation error (inline or in error banner)
    const errorEl = page.locator(
      '.error-banner-wrap, [role="alert"], [data-testid="validation-error"], text=超過, text=20'
    );
    await expect(errorEl).toBeVisible({ timeout: 3000 });
  }
});

test('test_0_row_result_shows_empty_state', async ({ page }) => {
  await setupBasicMocks(page);

  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          query_id: 'empty-query-id',
          kpi: { total_consumed: 0, total_required: 0, efficiency_pct: 0, lot_count: 0, workorder_count: 0 },
          trend: [],
          type_breakdown: [],
        },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    });
  });

  await page.goto(PAGE_URL);
  await page.fill('[data-testid="material-parts-input"]', 'NONEXISTENT-PART-XYZ');
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');

  await page.waitForTimeout(2000);

  // Empty state element should be shown
  const emptyEl = page.locator(
    '.empty-state, [class*="empty-state"], [class*="no-data"], text=沒有資料, text=查無資料, text=無資料, [data-testid="empty-state"]'
  );
  await expect(emptyEl.first()).toBeVisible({ timeout: 5000 });
});

test('test_wildcard_bare_star_rejected', async ({ page }) => {
  await setupBasicMocks(page);

  // Route that should NOT be called (bare * should be rejected client-side or return 400)
  let queryCalled = false;
  await page.route('**/api/material-consumption/query', (route) => {
    queryCalled = true;
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'VALIDATION_ERROR', message: '不允許單獨使用萬用字元 *' },
        meta: {},
      }),
    });
  });

  await page.goto(PAGE_URL);

  // Enter bare wildcard
  await page.fill('[data-testid="material-parts-input"]', '*');
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');

  const submitBtn = page.locator('[data-testid="query-submit-button"]');
  const isDisabled = await submitBtn.isDisabled();

  if (!isDisabled) {
    await submitBtn.click();
    await page.waitForTimeout(1000);

    // Either button stays disabled or error is shown
    const errorEl = page.locator(
      '.error-banner-wrap, [role="alert"], [data-testid="validation-error"], text=萬用字元, text=wildcard, text=*'
    );
    await expect(errorEl.first()).toBeVisible({ timeout: 5000 });
  } else {
    // Client-side validation prevents submission — pass
    expect(isDisabled).toBe(true);
  }
});

test('test_sql_injection_attempt_returns_400', async ({ page }) => {
  await setupBasicMocks(page);

  // Mock backend returns 400 for SQL injection attempt
  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'VALIDATION_ERROR', message: '輸入包含非法字元' },
        meta: {},
      }),
    });
  });

  await page.goto(PAGE_URL);

  // Enter SQL injection attempt
  await page.fill('[data-testid="material-parts-input"]', "Part'; DROP TABLE users; --");
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');

  const submitBtn = page.locator('[data-testid="query-submit-button"]');
  const isDisabled = await submitBtn.isDisabled();

  if (!isDisabled) {
    await submitBtn.click();
    await page.waitForTimeout(1000);

    // Error banner should appear with validation error
    const errorBanner = page.locator('.error-banner-wrap, [role="alert"]');
    await expect(errorBanner.first()).toBeVisible({ timeout: 5000 });
  } else {
    // Client-side validation blocked it
    expect(isDisabled).toBe(true);
  }
});
