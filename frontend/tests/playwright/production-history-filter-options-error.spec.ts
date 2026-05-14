/**
 * E2E resilience spec: Production History — filter-options endpoint failure
 *
 * Stubs /api/production-history/filter-options to 500.  Verifies:
 *   - The first-tier error banner `[data-testid="ph-first-tier-error"]` is
 *     visible with a non-empty message (UI-UX REC-01)
 *   - Wildcard textareas remain interactive (degraded mode — user can still
 *     submit by ID via the wildcard fields)
 *   - No JS uncaught error tears down the SPA
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, mockApiError } from './_auth.js';

test.describe('Production History — filter-options API failure', () => {
  test('error banner visible, wildcards still usable', async ({ page }) => {
    // Mock 500 on the filter-options endpoint.
    await mockApiError(page, '**/api/production-history/filter-options**', 500);

    // Capture any uncaught page errors.
    const pageErrors: Error[] = [];
    page.on('pageerror', (err) => pageErrors.push(err));

    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    // Error banner must appear within 15 s. It is rendered outside the query-
    // mode tab panels, so it is visible regardless of the active tab.
    const errorBanner = page.locator('[data-testid="ph-first-tier-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 15_000 });
    await expect(errorBanner).not.toBeEmpty();

    // The two-tab redesign (prod-history-query-mode-tabs) moved the wildcard
    // textareas into Tab B 「依識別碼查詢」 — switch to it to verify the degraded
    // mode (user can still submit by ID even when filter-options is down).
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });

    // Wildcard textareas must remain enabled (degraded mode).
    for (const id of [
      'ph-first-tier-mfg-orders',
      'ph-first-tier-lot-ids',
      'ph-first-tier-wafer-lots',
    ]) {
      const ta = page.locator(`[data-testid="${id}"]`);
      await expect(ta).toBeVisible();
      await expect(ta).toBeEnabled();
      await ta.fill('TEST-LOT-A');
      await expect(ta).toHaveValue('TEST-LOT-A');
    }

    // No uncaught JS errors — the SPA must degrade gracefully.
    expect(pageErrors, `pageerror events: ${pageErrors.map((e) => e.message).join(';')}`).toEqual([]);
  });
});
