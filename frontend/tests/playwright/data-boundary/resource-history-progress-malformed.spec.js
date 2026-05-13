/**
 * Data-boundary spec: malformed progress response must not crash polling
 *
 * Intercepts GET /api/resource/history/query/progress and returns a payload
 * that violates the Section 2.6 schema (missing `percent`, `total_chunks`,
 * `completed_chunks`; `status` is an unknown enum value).
 *
 * Verifies:
 *   - No uncaught JS error is thrown by the polling loop
 *   - Polling stops gracefully (does not loop indefinitely)
 *   - Page body remains non-empty (no white screen)
 *
 * Uses page.route() — no real backend required.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, waitForIdleUi } from '../_auth.js';

const QUERY_ID = 'test-malformed-progress';

// Malformed payload: missing required fields, unknown status enum value
const MALFORMED_PROGRESS = JSON.stringify({
  success: true,
  data: {
    // percent, total_chunks, completed_chunks intentionally omitted
    query_id: QUERY_ID,
    status: 'unknown_enum_value',
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
});

async function setupResourceHistoryWithMalformedProgress(page) {
  // Mock options endpoint so the filter bar renders
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

  // Primary query — signal batch mode so startPolling() is called
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

  // Progress endpoint always returns the malformed payload
  await page.route('**/api/resource/history/query/progress**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: MALFORMED_PROGRESS,
    }),
  );
}

test.describe('Resource History — malformed progress response boundary', () => {
  test.beforeEach(async ({ page }) => {
    await setupResourceHistoryWithMalformedProgress(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'resource-history', {});
  });

  test('no uncaught JS error when progress response is malformed', async ({ page }) => {
    const consoleErrors = [];
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    await waitForIdleUi(page, 25_000);

    expect(consoleErrors).toHaveLength(0);
  });

  test('polling stops gracefully after malformed response', async ({ page }) => {
    // Count progress requests; after graceful stop the count must not grow
    let pollCount = 0;
    await page.route('**/api/resource/history/query/progress**', (route) => {
      pollCount++;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: MALFORMED_PROGRESS,
      });
    });

    await waitForIdleUi(page, 25_000);

    const countAfterIdle = pollCount;
    await page.waitForTimeout(4_000);
    // Poll count must not have grown — polling has stopped
    expect(pollCount).toBe(countAfterIdle);
  });

  test('page body remains visible after malformed progress response', async ({ page }) => {
    await waitForIdleUi(page, 25_000);

    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText.length).toBeGreaterThan(0);
  });
});
