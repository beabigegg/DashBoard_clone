/**
 * E2E resilience spec: Production History — filter-options endpoint failure
 *
 * All tests stub /api/production-history/filter-options to 500 and use
 * navigateMocked() — these are error-scenario tests that always need
 * controlled mock behaviour, so no USE_MOCKS conditional is needed.
 *
 * Scenarios covered:
 *   1. Error banner visible, wildcards still usable (degraded mode, identifier tab)
 *   2. Error banner visible in classification tab
 *   3. Error banner persists after switching tabs and back
 *   4. Each wildcard textarea independently accepts text input
 *   5. Classification mode renders gracefully (multiselects present, no crash)
 *   6. Identifier query submits despite filter-options failure (end-to-end degraded)
 */

import { test, expect, type Page } from '@playwright/test';
import { navigateMocked } from './_api-mode.js';
import { mockApiError } from './_auth.js';

// ---------------------------------------------------------------------------
// Shared navigation helper — always mocked with 500 filter-options
// ---------------------------------------------------------------------------

async function gotoWithFilterOptionsError(
  page: Page,
  extraSetup?: (page: Page) => Promise<void>,
): Promise<void> {
  await navigateMocked(page, 'production-history', {
    waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    extraMocks: async () => {
      // Register the 500 error AFTER catch-all and shell mocks (LIFO — wins).
      await mockApiError(page, '**/api/production-history/filter-options**', 500);
      if (extraSetup) await extraSetup(page);
    },
  });
}

// ---------------------------------------------------------------------------

test.describe('Production History — filter-options API failure', () => {
  // -------------------------------------------------------------------------
  // Test 1: error banner visible, wildcards still usable (identifier tab)
  // -------------------------------------------------------------------------
  test('error banner visible, wildcards still usable', async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on('pageerror', (err) => pageErrors.push(err));

    await gotoWithFilterOptionsError(page);

    // Error banner must appear and carry a non-empty message (UI-UX REC-01).
    const errorBanner = page.locator('[data-testid="ph-first-tier-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 15_000 });
    await expect(errorBanner).not.toBeEmpty();

    // The two-tab redesign places wildcard textareas inside the identifier tab.
    // Click the tab to reveal the panel, then verify degraded mode.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });

    for (const id of ['ph-first-tier-mfg-orders', 'ph-first-tier-lot-ids', 'ph-first-tier-wafer-lots']) {
      const ta = page.locator(`[data-testid="${id}"]`);
      await expect(ta).toBeVisible();
      await expect(ta).toBeEnabled();
      await ta.fill('TEST-LOT-A');
      await expect(ta).toHaveValue('TEST-LOT-A');
    }

    expect(pageErrors, `pageerror: ${pageErrors.map((e) => e.message).join('; ')}`).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // Test 2: error banner visible in classification tab
  // -------------------------------------------------------------------------
  test('error banner visible in classification mode', async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on('pageerror', (err) => pageErrors.push(err));

    await gotoWithFilterOptionsError(page);

    // Switch to the classification tab.
    await page.locator('[data-testid="ph-mode-tab-classification"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-classification"]')).toBeVisible({
      timeout: 10_000,
    });

    // The error banner lives outside the tab panels — must still be visible.
    const errorBanner = page.locator('[data-testid="ph-first-tier-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 10_000 });
    await expect(errorBanner).not.toBeEmpty();

    expect(pageErrors, `pageerror: ${pageErrors.map((e) => e.message).join('; ')}`).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // Test 3: error banner persists after switching tabs and back
  // -------------------------------------------------------------------------
  test('error banner persists after tab round-trip', async ({ page }) => {
    await gotoWithFilterOptionsError(page);

    const errorBanner = page.locator('[data-testid="ph-first-tier-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 15_000 });

    // Switch to classification tab.
    await page.locator('[data-testid="ph-mode-tab-classification"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-classification"]')).toBeVisible({
      timeout: 10_000,
    });

    // Banner must still be visible on the classification panel.
    await expect(errorBanner).toBeVisible();

    // Switch back to identifier tab.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });

    // Banner must persist — it is not cleared by tab switching.
    await expect(errorBanner).toBeVisible();
    await expect(errorBanner).not.toBeEmpty();
  });

  // -------------------------------------------------------------------------
  // Test 4: each wildcard textarea individually accepts independent text input
  // -------------------------------------------------------------------------
  test('each wildcard textarea independently accepts input', async ({ page }) => {
    await gotoWithFilterOptionsError(page);

    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });

    const cases: Array<{ id: string; value: string }> = [
      { id: 'ph-first-tier-mfg-orders', value: 'MFG-ORDER-001\nMFG-ORDER-002' },
      { id: 'ph-first-tier-lot-ids',    value: 'LOT-ALPHA' },
      { id: 'ph-first-tier-wafer-lots', value: 'WL-999' },
    ];

    // Fill each textarea independently and confirm isolation — earlier values
    // must not be altered by subsequent fills.
    for (const { id, value } of cases) {
      const ta = page.locator(`[data-testid="${id}"]`);
      await expect(ta).toBeEnabled();
      await ta.fill(value);
      await expect(ta).toHaveValue(value);
    }

    // Re-check all values to confirm no cross-field interference.
    for (const { id, value } of cases) {
      await expect(page.locator(`[data-testid="${id}"]`)).toHaveValue(value);
    }
  });

  // -------------------------------------------------------------------------
  // Test 5: classification mode renders gracefully (no crash, selects present)
  // -------------------------------------------------------------------------
  test('classification mode renders gracefully without filter-options data', async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on('pageerror', (err) => pageErrors.push(err));

    await gotoWithFilterOptionsError(page);

    await page.locator('[data-testid="ph-mode-tab-classification"]').click();
    const classPanel = page.locator('[data-testid="ph-mode-panel-classification"]');
    await expect(classPanel).toBeVisible({ timeout: 10_000 });

    // Multiselect containers must be present in the DOM even with empty options.
    // They may be disabled or show placeholder text — we only assert presence.
    for (const id of [
      'ph-first-tier-type',
      'ph-first-tier-package',
      'ph-first-tier-bop',
      'ph-first-tier-function',
    ]) {
      await expect(page.locator(`[data-testid="${id}"]`)).toBeAttached({ timeout: 8_000 });
    }

    // The query button must exist (may be disabled due to no selection).
    await expect(page.locator('[data-testid="ph-query-btn"]')).toBeAttached();

    expect(pageErrors, `pageerror: ${pageErrors.map((e) => e.message).join('; ')}`).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // Test 6: identifier query fires despite filter-options failure (degraded mode)
  // -------------------------------------------------------------------------
  test('identifier query submits successfully in degraded mode', async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on('pageerror', (err) => pageErrors.push(err));

    // Also mock the query endpoint so the request can complete inside CI.
    await navigateMocked(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
      extraMocks: async () => {
        // Register 500 for filter-options (LIFO — specific wins over catch-all).
        await mockApiError(page, '**/api/production-history/filter-options**', 500);

        // Stub the query endpoint to return an empty success payload.
        await page.route('**/api/production-history/query**', (r) =>
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: {
                dataset_id: 'mock-degraded',
                rows: [],
                pagination: { total: 0, page: 1, page_size: 50 },
                matrix: { tree: [], month_columns: [] },
              },
              meta: { timestamp: new Date().toISOString(), app_version: 'test' },
            }),
          }),
        );
      },
    });

    // Confirm error banner is present (confirming degraded state).
    const errorBanner = page.locator('[data-testid="ph-first-tier-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 15_000 });

    // Navigate to identifier tab and fill a lot-id wildcard.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });

    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('DEGRADED-LOT-001');

    // Arm the request interceptor before clicking.
    const queryRequestPromise = page.waitForRequest('**/api/production-history/query**', {
      timeout: 12_000,
    });

    await page.locator('[data-testid="ph-query-btn"]').click();

    // The query request must fire — end-to-end degraded mode works.
    const queryRequest = await queryRequestPromise;
    expect(queryRequest.url()).toContain('/api/production-history/query');

    expect(pageErrors, `pageerror: ${pageErrors.map((e) => e.message).join('; ')}`).toEqual([]);
  });
});
