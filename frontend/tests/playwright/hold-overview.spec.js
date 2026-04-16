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

  test('renders the Lot Details data table', async ({ page }) => {
    const tables = page.locator('table');
    const count = await tables.count();
    expect(count).toBeGreaterThanOrEqual(1);
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
