/**
 * E2E spec: Hold Overview page
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

test.describe('Hold Overview page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-overview', {
      waitForSelector: '.ui-card, table',
    });
  });

  test('renders summary cards after initial load', async ({ page }) => {
    const summaryCards = page.locator('.ui-card');
    await expect(summaryCards.first()).toBeVisible({ timeout: 20_000 });
  });

  test('renders the Hold Matrix table', async ({ page }) => {
    const tables = page.locator('table');
    await expect(tables.first()).toBeVisible({ timeout: 20_000 });
  });

  test('renders the Lot Details data table as a flat table (no nested .ui-card inside .card-body)', async ({ page }) => {
    // Locate the Hold Lot Details card
    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    await expect(lotsCard.first()).toBeVisible({ timeout: 20_000 });

    // The card-body must contain a <table> directly — not via a nested .ui-card wrapper
    const cardBody = lotsCard.first().locator('.card-body, .ui-card-body').first();
    await expect(cardBody).toBeVisible({ timeout: 10_000 });

    // Assert no nested .ui-card inside .card-body (that would be "table within table")
    const nestedCard = cardBody.locator('.ui-card');
    const nestedCount = await nestedCard.count();
    expect(nestedCount).toBe(0);

    // Assert a <table> is present inside the card (directly or via DataTable)
    const tableInCard = lotsCard.first().locator('table');
    await expect(tableInCard.first()).toBeVisible({ timeout: 20_000 });
  });

  test('clicking a pareto drilldown item navigates to hold-detail', async ({ page }) => {
    await page.waitForTimeout(3_000);

    const paretoBar = page.locator(
      '.pareto-section .pareto-bar, .pareto-item, [class*="pareto"] [role="button"], [class*="pareto"] button'
    ).first();

    if (await paretoBar.count() === 0) {
      test.skip(true, 'No pareto items (no hold data)');
      return;
    }

    await paretoBar.click({ timeout: 10_000 });

    await page.waitForURL((url) => url.pathname.includes('hold-detail'), {
      timeout: 15_000,
    });
    expect(page.url()).toContain('hold-detail');
  });
});

// ---------------------------------------------------------------------------
// CSV Export tests (AC-1, AC-2, AC-8)
//
// Pattern: use real server for login + sidebar navigation (same as the
// existing describe block above), then intercept only the specific export
// request per test to avoid breaking the portal-shell sidebar rendering.
// ---------------------------------------------------------------------------

test.describe('Hold Overview — CSV export button', () => {
  const EXPORT_LOTS = [
    {
      lotId: 'LOT-E2E-001', workorder: 'WO-E2E-001', qty: 10, product: 'PROD-A',
      package: 'PKG-A', workcenter: 'WC-01', holdReason: 'QUALITY',
      spec: 'S1', age: 2, holdBy: 'eng1', dept: 'QC',
      holdComment: 'comment1', futureHoldComment: 'future1',
    },
    {
      lotId: 'LOT-E2E-002', workorder: 'WO-E2E-002', qty: 5, product: 'PROD-B',
      package: 'PKG-B', workcenter: 'WC-02', holdReason: 'NON-QUALITY',
      spec: 'S2', age: 4, holdBy: 'eng2', dept: 'ENG',
      holdComment: 'comment2', futureHoldComment: null,
    },
  ];

  function makeExportPayload(lots) {
    return JSON.stringify({
      success: true,
      meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      data: {
        lots,
        pagination: { page: 1, perPage: lots.length || 1, total: lots.length, totalPages: 1 },
      },
    });
  }

  test.beforeEach(async ({ page }) => {
    // Use real server for login + sidebar navigation — identical to the
    // existing "Hold Overview page" describe block above.
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-overview', {
      waitForSelector: '.ui-card, table',
    });
  });

  test('export button appears in Hold Lot Details card header', async ({ page }) => {
    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    await expect(lotsCard.first()).toBeVisible({ timeout: 20_000 });

    const exportBtn = lotsCard.locator('button:has-text("匯出 CSV")');
    await expect(exportBtn.first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking export button triggers download with correct filename pattern', async ({ page }) => {
    // Intercept the export POST so we don't need real hold data to complete
    // the download.  Register LAST (LIFO) so it takes priority over any
    // default routes established during navigation.
    await page.route('**/api/hold-overview/lots', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeExportPayload(EXPORT_LOTS),
      });
    });

    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    const exportBtn = lotsCard.locator('button:has-text("匯出 CSV")').first();
    await expect(exportBtn).toBeVisible({ timeout: 20_000 });

    const [download] = await Promise.all([
      // Widen from 15s to 25s so the download event is not missed under
      // full-suite resource contention (this test is download-timing sensitive).
      page.waitForEvent('download', { timeout: 25_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/^hold-overview-\d{4}-\d{2}-\d{2}\.csv$/);
  });

  test('export button shows loading state during in-flight request', async ({ page }) => {
    // Use a slow mock to keep the export request in-flight long enough to
    // assert the loading state.
    await page.route('**/api/hold-overview/lots', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3_000));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeExportPayload(EXPORT_LOTS),
      });
    });

    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    const exportBtn = lotsCard.locator('button').filter({ hasText: /匯出/ }).first();
    await expect(exportBtn).toBeVisible({ timeout: 20_000 });

    // Click and immediately assert the loading state before the response arrives
    await exportBtn.click();

    await expect(exportBtn).toBeDisabled({ timeout: 2_000 });
    await expect(exportBtn).toHaveClass(/is-loading/, { timeout: 2_000 });
    await expect(exportBtn).toContainText('匯出中...', { timeout: 2_000 });
  });
});
