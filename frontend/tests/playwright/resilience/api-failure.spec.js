/**
 * Resilience spec: API failure injection
 *
 * Injects HTTP 500, 503+Retry-After, and network abort into the primary query
 * endpoints of Query Tool, Reject History, and Hold Overview.  Verifies that:
 *   - the loading overlay is dismissed after failure
 *   - an error toast (or inline error element) becomes visible
 *   - the query button is re-enabled after failure
 *   - no stale data from a previous successful load bleeds through
 *
 * Uses page.route() mock — no real backend required.
 * Error body follows the MES Dashboard envelope (core/response.py).
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, mockApiError, waitForIdleUi } from '../_auth.js';

const ERROR_SELECTORS = [
  '[class*="toast"]',
  '[class*="alert"]',
  '[class*="error-msg"]',
  '[role="alert"]',
  '.error-state',
  '[class*="error"]',
];

async function waitForErrorFeedback(page, timeout = 15_000) {
  await page.waitForFunction(
    (selectors) => selectors.some((sel) => {
      const el = document.querySelector(sel);
      return el && el.offsetParent !== null;
    }),
    ERROR_SELECTORS,
    { timeout },
  );
}

// ---------------------------------------------------------------------------
// Query Tool — HTTP 500
// ---------------------------------------------------------------------------

// Query Tool uses a tabbed interface.  The default tab is LOT-resolve ("解析"),
// not the date-range query ("查詢").  We switch to the Equipment tab which has
// the standard date-based 查詢 button, then inject a 500 error on the query API.

test.describe('Query Tool (equipment tab) — HTTP 500 from query API', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the date-range query endpoint with 500 once in the equipment tab
    await mockApiError(page, '**/api/query-tool/query**', 500);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'query-tool', {
      waitForSelector: 'textarea',
    });
    // Switch to equipment tab so the "查詢" button is visible
    const equipTab = page.locator('button:has-text("設備生產批次追蹤")').first();
    if (await equipTab.count() > 0) {
      await equipTab.click();
      await expect(page.locator('input[type="date"]:visible').first()).toBeVisible({ timeout: 10_000 });
    }
  });

  test('overlay dismissed and error feedback shown after 500', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢"):visible').first();
    if (await queryBtn.count() === 0) {
      test.skip(true, '查詢 button not visible after tab switch');
      return;
    }
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // Overlay must disappear (not stuck in loading)
    await waitForIdleUi(page, 20_000);

    // Error feedback must appear
    await waitForErrorFeedback(page);
  });

  test('query button re-enabled after 500', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢"):visible').first();
    if (await queryBtn.count() === 0) {
      test.skip(true, '查詢 button not visible after tab switch');
      return;
    }
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    await waitForIdleUi(page, 20_000);

    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
    await expect(queryBtn).not.toHaveAttribute('aria-busy', 'true');
  });
});

// ---------------------------------------------------------------------------
// Reject History — HTTP 503 with Retry-After header
// ---------------------------------------------------------------------------

test.describe('Reject History — HTTP 503 with Retry-After', () => {
  test.beforeEach(async ({ page }) => {
    await mockApiError(page, '**/api/reject-history/**', 503, {
      headers: { 'Retry-After': '30' },
      body: {
        success: false,
        error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫時無法使用，請稍後再試' },
        meta: { timestamp: new Date().toISOString(), app_version: 'test', retry_after_seconds: 30 },
      },
    });
    await loginViaApi(page);
    await navigateViaSidebar(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
    });
  });

  test('overlay dismissed and error feedback shown after 503', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    await waitForIdleUi(page, 20_000);
    await waitForErrorFeedback(page);
  });

  test('no stale data rendered after 503', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    await waitForIdleUi(page, 20_000);

    // Table rows should not appear — only the error / empty state
    const tableRows = page.locator('tbody tr');
    const count = await tableRows.count();
    expect(count).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Hold Overview — network abort (timedout)
// ---------------------------------------------------------------------------

test.describe('Hold Overview — network abort (timedout)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/hold-overview/**', (route) => route.abort('timedout'));
    await page.route('**/api/hold/**', (route) => route.abort('timedout'));
    await loginViaApi(page);
    // hold-overview loads data automatically on mount; no query button needed
    await navigateViaSidebar(page, 'hold-overview', {});
  });

  test('overlay dismissed after network abort', async ({ page }) => {
    await waitForIdleUi(page, 25_000);
  });

  test('error feedback visible after network abort', async ({ page }) => {
    await waitForIdleUi(page, 25_000);
    await waitForErrorFeedback(page);
  });
});

// ---------------------------------------------------------------------------
// Hold History today-snapshot — API failure (no white screen)
// ---------------------------------------------------------------------------

test.describe('Hold History today mode — today-snapshot API 503 (no white screen)', () => {
  test.beforeEach(async ({ page }) => {
    // Mock today-snapshot to return 503; primary query returns success
    await page.route('**/api/hold-history/today-snapshot', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫時無法使用' } }),
      }),
    );
    await page.route('**/api/hold-history/config', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { today_mode_enabled: true, auto_refresh_seconds: 60 } }),
      }),
    );
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', {});
  });

  test('page does not white-screen when today-snapshot returns 503', async ({ page }) => {
    // Navigate to today mode
    const todayBtn = page.locator('button:has-text("當日")').first();
    if (await todayBtn.count() > 0) {
      await todayBtn.click();
    }
    await waitForIdleUi(page, 15_000);
    // Page body should still be visible (no white screen)
    await expect(page.locator('.hold-history-page')).toBeVisible({ timeout: 10_000 });
  });

  test('error feedback visible after today-snapshot 503', async ({ page }) => {
    const todayBtn = page.locator('button:has-text("當日")').first();
    if (await todayBtn.count() > 0) {
      await todayBtn.click();
    }
    await waitForIdleUi(page, 15_000);
    await waitForErrorFeedback(page);
  });
});
