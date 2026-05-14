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
