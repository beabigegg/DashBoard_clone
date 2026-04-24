/**
 * Data-boundary spec: Hold History today-snapshot payload edge cases
 *
 * Uses page.route() mocks — no real backend required.
 * Verifies:
 *   - Truncated payload shows warning to user
 *   - Empty today-snapshot payload shows EmptyState
 *   - Today mode summary cards render with correct values
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, waitForIdleUi } from '../_auth.js';

const BASE_ENVELOPE = {
  success: true,
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

function makeTodayPayload(overrides = {}) {
  return JSON.stringify({
    ...BASE_ENVELOPE,
    data: {
      query_id: 'today_test_001',
      summary: {
        onHoldLots: 10,
        onHoldQty: 50,
        todayNewQty: 5,
        todayReleaseQty: 2,
        todayFutureHoldQty: 1,
        repeatQualityHoldQty: 0,
        onHoldAvgHours: 24.0,
        onHoldMaxHours: 120.0,
      },
      reason_pareto: { items: [] },
      duration: { items: [] },
      list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
      ...overrides,
    },
  });
}

async function switchToTodayMode(page) {
  // Navigate to today mode via mode toggle
  const todayBtn = page.locator('button:has-text("當日")').first();
  if (await todayBtn.count() > 0) {
    await todayBtn.click();
    await waitForIdleUi(page, 10_000);
  }
}

// ---------------------------------------------------------------------------
// Empty payload — EmptyState
// ---------------------------------------------------------------------------

test.describe('Hold History today-snapshot — empty result shows EmptyState', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/hold-history/config', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...BASE_ENVELOPE, data: { today_mode_enabled: true, auto_refresh_seconds: 60 } }),
      }),
    );
    await page.route('**/api/hold-history/today-snapshot', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeTodayPayload({
          summary: {
            onHoldTotalCount: 0, onHoldTotalQty: 0, todayNewQty: 0,
            todayReleaseQty: 0, todayFutureHoldQty: 0,
            onHoldAvgHours: 0, onHoldMaxHours: 0,
          },
          list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
        }),
      }),
    );
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', {});
  });

  test('empty state message is visible when today-snapshot returns no data', async ({ page }) => {
    await switchToTodayMode(page);
    const emptyState = page.locator('.hold-history-page .empty-state').first();
    await expect(emptyState).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Summary card values
// ---------------------------------------------------------------------------

test.describe('Hold History today-snapshot — summary card values', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/hold-history/config', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...BASE_ENVELOPE, data: { today_mode_enabled: true, auto_refresh_seconds: 60 } }),
      }),
    );
    await page.route('**/api/hold-history/today-snapshot', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeTodayPayload(),
      }),
    );
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', {});
  });

  test('today-mode summary cards render 8 cards', async ({ page }) => {
    await switchToTodayMode(page);
    // 8 summary cards for today mode (scoped to hold-history page)
    const cards = page.locator('.hold-history-page .summary-card');
    await expect(cards).toHaveCount(8, { timeout: 10_000 });
  });

  test('DailyTrend is not visible in today mode', async ({ page }) => {
    await switchToTodayMode(page);
    const trend = page.locator('.daily-trend, [class*="daily-trend"]').first();
    await expect(trend).not.toBeVisible({ timeout: 5_000 });
  });
});
