/**
 * Resilience spec: resource-history progress polling survives 503
 *
 * Intercepts GET /api/resource/history/query/progress with HTTP 503 and
 * verifies that:
 *   - No uncaught JS error reaches the browser console
 *   - The polling loop stops (does not zombie-poll forever)
 *   - The page does not white-screen (body text remains non-empty)
 *
 * The primary query POST is mocked to return a batch response (total_chunks=3)
 * so that startPolling() is actually called.
 *
 * Uses page.route() — no real backend required.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, waitForIdleUi } from '../_auth.js';

const QUERY_ID = 'test-progress-503';

async function setupResourceHistoryWithBatchQuery(page) {
  // Mock options endpoint so the filter bar renders without a real DB
  await page.route('**/api/resource/history/options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { workcenter_groups: [], families: [], resources: [] },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    }),
  );

  // Mock the primary query — signal batch mode (total_chunks=3) so polling starts
  await page.route('**/api/resource/history/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          query_id: QUERY_ID,
          total_chunks: 3,
          summary: { kpi: {}, trend: [], heatmap: [], workcenter_comparison: [] },
          detail: { data: [], truncated: false },
        },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    }),
  );

  // Return 503 for every progress poll
  await page.route('**/api/resource/history/query/progress**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫時無法使用' },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    }),
  );
}

test.describe('Resource History — progress polling survives 503', () => {
  test.beforeEach(async ({ page }) => {
    await setupResourceHistoryWithBatchQuery(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'resource-history', {});
  });

  test('no uncaught JS error when progress endpoint returns 503', async ({ page }) => {
    const consoleErrors = [];
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    // Wait for the page to settle; polling will fire and receive 503 responses
    await waitForIdleUi(page, 25_000);

    // No uncaught error should have been thrown
    expect(consoleErrors).toHaveLength(0);
  });

  test('polling stops after 503 (isPolling becomes false)', async ({ page }) => {
    // Count how many progress requests are made — after stopPolling() no more should arrive
    let pollCount = 0;
    await page.route('**/api/resource/history/query/progress**', (route) => {
      pollCount++;
      return route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫時無法使用' },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      });
    });

    await waitForIdleUi(page, 25_000);

    // Wait a further 4 s and record count; it must not keep growing (polling stopped)
    const countAfterIdle = pollCount;
    await page.waitForTimeout(4_000);
    expect(pollCount).toBe(countAfterIdle);
  });

  test('page body remains visible after progress 503', async ({ page }) => {
    await waitForIdleUi(page, 25_000);

    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText.length).toBeGreaterThan(0);
  });
});
