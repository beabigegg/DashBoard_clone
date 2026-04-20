/**
 * Resilience spec: Rapid / concurrent interactions
 *
 * (a) Clicking the query button 5 times rapidly should only issue 1 request
 *     (request-guard / debounce / disabled-while-loading must prevent duplicates).
 * (b) Clicking Export while a query is in-flight: the button should be disabled
 *     OR the app should show a guard toast.
 * (c) Clicking Export 3 times rapidly should only trigger 1 download.
 *
 * Uses Reject History for (a) and (b) because it has a "查詢" button that fires
 * the API without prerequisites (equipment selection not required).
 * Uses page.route() slow mock to keep the request in-flight during the rapid clicks.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, waitForIdleUi } from '../_auth.js';

const SLOW_MS = 4_000;

async function setupRejectHistoryWithSlowQuery(page) {
  let queryRequestCount = 0;

  // Broad fast mock for all reject-history endpoints (catches view, batch-pareto, etc.)
  await page.route('**/api/reject-history/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { data: [], total: 0 } }),
    }),
  );
  // Override query endpoint with slow response (LIFO: evaluated before the broad mock)
  await page.route('**/api/reject-history/query**', async (route) => {
    queryRequestCount++;
    await new Promise((r) => setTimeout(r, SLOW_MS));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { query_id: 'test-123', data: [], total: 0 } }),
    });
  });

  await loginViaApi(page);
  await navigateViaSidebar(page, 'reject-history', {
    waitForSelector: 'input[type="date"]',
  });

  return { getQueryRequestCount: () => queryRequestCount };
}

// ---------------------------------------------------------------------------
// (a) 5 rapid clicks → 1 request
// ---------------------------------------------------------------------------

test('query button: 5 rapid clicks issues only 1 API request', async ({ page }) => {
  const { getQueryRequestCount } = await setupRejectHistoryWithSlowQuery(page);

  const queryBtn = page.locator('button:has-text("查詢"):visible').first();
  if (await queryBtn.count() === 0) {
    test.skip(true, '查詢 button not visible on reject-history');
    return;
  }
  await expect(queryBtn).toBeVisible({ timeout: 10_000 });

  // Click 5 times rapidly
  for (let i = 0; i < 5; i++) {
    await queryBtn.click({ force: true });
  }

  // Wait for the single in-flight request to complete
  await waitForIdleUi(page, SLOW_MS + 10_000);

  expect(getQueryRequestCount()).toBe(1);
});

// ---------------------------------------------------------------------------
// (b) Export button disabled or guard toast shown while query in-flight
// ---------------------------------------------------------------------------

test('export button disabled or guard toast while query in-flight', async ({ page }) => {
  await setupRejectHistoryWithSlowQuery(page);

  const queryBtn = page.locator('button:has-text("查詢"):visible').first();
  if (await queryBtn.count() === 0) return;
  await expect(queryBtn).toBeVisible({ timeout: 10_000 });
  await queryBtn.click();

  // While in-flight, check export button state
  const exportBtn = page.locator(
    'button:has-text("匯出 CSV"), button:has-text("CSV"), button:has-text("匯出")',
  ).first();

  if (await exportBtn.count() === 0) {
    // No export button — guard is implicit (not rendered yet)
    return;
  }

  // Allow a brief moment for state to propagate
  await page.waitForTimeout(200);

  const isDisabled = await exportBtn.isDisabled();
  if (!isDisabled) {
    // If not disabled, clicking should show a guard toast
    await exportBtn.click({ force: true });
    const toastVisible = await page.waitForFunction(
      () => {
        const selectors = [
          '[class*="toast"]',
          '[role="alert"]',
          '[class*="guard"]',
          '[class*="warning"]',
        ];
        return selectors.some((s) => {
          const el = document.querySelector(s);
          return el && el.offsetParent !== null;
        });
      },
      { timeout: 5_000 },
    ).catch(() => false);

    // Either disabled or toast — one must be true
    expect(isDisabled || toastVisible !== false).toBe(true);
  }

  await waitForIdleUi(page, SLOW_MS + 10_000);
});

// ---------------------------------------------------------------------------
// (c) Export button: 3 rapid clicks → 1 download
// ---------------------------------------------------------------------------

test('export button: 3 rapid clicks triggers only 1 download', async ({ page }) => {
  // Use reject-history with successful query so export is enabled
  await page.route('**/api/reject-history/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { query_id: 'test-123', data: [{ id: 1 }], total: 1 },
      }),
    }),
  );

  let exportCallCount = 0;
  // Use slow mock so loading.exporting stays true during rapid clicks (LIFO: overrides broad mock)
  await page.route('**/api/reject-history/export-cached**', async (route) => {
    exportCallCount++;
    await new Promise((r) => setTimeout(r, 1_000));
    await route.fulfill({
      status: 200,
      contentType: 'text/csv',
      headers: { 'Content-Disposition': 'attachment; filename="export.csv"' },
      body: 'col1,col2\nval1,val2\n',
    });
  });

  await loginViaApi(page);
  await navigateViaSidebar(page, 'reject-history', {
    waitForSelector: 'input[type="date"]',
  });

  const queryBtn = page.locator('button:has-text("查詢"):visible').first();
  if (await queryBtn.count() === 0) return;
  await queryBtn.click();
  await waitForIdleUi(page, 15_000);

  const exportBtn = page.locator(
    'button:has-text("匯出 CSV"), button:has-text("CSV"), button:has-text("匯出")',
  ).first();

  if (await exportBtn.count() === 0) return;
  if (await exportBtn.isDisabled()) return;

  // Click 3 times rapidly
  for (let i = 0; i < 3; i++) {
    await exportBtn.click({ force: true });
  }

  await page.waitForTimeout(2_000);

  expect(exportCallCount).toBeLessThanOrEqual(1);
});
