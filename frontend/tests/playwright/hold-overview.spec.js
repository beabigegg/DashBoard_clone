/**
 * E2E spec: Hold Overview page
 *
 * Flow:
 *  1. Login via API shortcut
 *  2. Navigate to /portal-shell.html (SPA) and push router to /hold-overview
 *  3. Wait for the initial loading skeleton to disappear
 *  4. Assert that the summary cards and HoldMatrix table rendered
 *  5. Click a pareto item to drill down → verify navigation to /hold-detail
 *  6. Go back and click a row cell in the lot table to verify it renders
 */

import { test, expect } from '@playwright/test';
import { loginViaApi } from './_auth.js';

// The portal-shell router base is /portal-shell, so the SPA
// hold-overview route resolves to /portal-shell/hold-overview.
const HOLD_OVERVIEW_URL = '/portal-shell/hold-overview';

test.describe('Hold Overview page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    // Navigate into the SPA route
    await page.goto(HOLD_OVERVIEW_URL);
  });

  test('renders summary cards after initial load', async ({ page }) => {
    // Wait for the skeleton loader to be gone and real content to appear
    await page.waitForSelector('.hold-overview-page', { timeout: 30_000 });

    // The SkeletonLoader is shown during initialLoading=true.
    // Wait until it disappears (or is not present).
    await page.waitForFunction(
      () => document.querySelector('.skeleton-loader') === null ||
            document.querySelector('.ui-card') !== null,
      { timeout: 30_000 },
    );

    // Summary cards group should be visible
    const summaryCards = page.locator('.ui-card');
    await expect(summaryCards.first()).toBeVisible({ timeout: 20_000 });
  });

  test('renders the Hold Matrix table', async ({ page }) => {
    await page.waitForSelector('.hold-overview-page', { timeout: 30_000 });

    // Wait until initial loading is done
    await page.waitForFunction(
      () => !document.querySelector('.skeleton-loader'),
      { timeout: 30_000 },
    );

    // The matrix is wrapped in .matrix-container
    const matrix = page.locator('.matrix-container');
    await expect(matrix).toBeVisible({ timeout: 20_000 });
  });

  test('renders the Lot Details data table', async ({ page }) => {
    await page.waitForSelector('.hold-overview-page', { timeout: 30_000 });

    // Wait until the initial skeleton disappears
    await page.waitForFunction(
      () => !document.querySelector('.skeleton-loader'),
      { timeout: 30_000 },
    );

    // The lot table section header
    const lotHeader = page.locator('.ui-card-title', { hasText: 'Hold Lot Details' });
    await expect(lotHeader).toBeVisible({ timeout: 20_000 });
  });

  test('clicking a pareto drilldown item navigates to hold-detail', async ({ page }) => {
    await page.waitForSelector('.hold-overview-page', { timeout: 30_000 });

    await page.waitForFunction(
      () => !document.querySelector('.skeleton-loader'),
      { timeout: 30_000 },
    );

    // ParetoSection renders bar items; find the first clickable bar.
    // The component emits 'drilldown' which calls navigateToRuntimeRoute.
    // The selector targets a bar or label element inside the pareto sections.
    const paretoBar = page.locator('.pareto-section .pareto-bar, .pareto-item, [class*="pareto"] [role="button"], [class*="pareto"] button').first();

    const hasBars = await paretoBar.count();
    if (hasBars === 0) {
      // No pareto items means no hold data — skip drill-down assertion
      test.skip();
      return;
    }

    await paretoBar.click({ timeout: 10_000 });

    // After navigation the URL should contain hold-detail
    await page.waitForURL((url) => url.pathname.includes('hold-detail'), {
      timeout: 15_000,
    });
    expect(page.url()).toContain('hold-detail');
  });
});
