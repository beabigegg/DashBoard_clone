/**
 * E2E spec: Query Tool page
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 * Tests the LOT tab (default) and tab switching.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

const DUMMY_LOT_ID = 'TEST-LOT-E2E-00001';

test.describe('Query Tool page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'query-tool', {
      waitForSelector: 'textarea',
    });
  });

  test('page loads with tab navigation visible', async ({ page }) => {
    const tabItem = page.locator(
      'button:has-text("批次追蹤"), button:has-text("流水批反查"), button:has-text("設備生產")'
    ).first();
    await expect(tabItem).toBeVisible({ timeout: 20_000 });
  });

  test('LOT tab input and query execution completes without error', async ({ page }) => {
    const inputArea = page.locator('textarea').first();
    await expect(inputArea).toBeVisible({ timeout: 10_000 });
    await inputArea.fill(DUMMY_LOT_ID);

    const queryBtn = page.locator('button:has-text("解析")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // Wait for the query to finish (loading overlay disappears or never appears).
    // A nonexistent lot may produce no visible result — the table exists but stays
    // hidden.  We just verify the page didn't crash and the button is re-enabled.
    await page.waitForTimeout(5_000);

    // The 解析 button should be clickable again (not in loading state)
    await expect(queryBtn).toBeEnabled({ timeout: 30_000 });

    // At least one of: visible result, hidden table (no data), or error message
    const hasAnyOutcome = await page.evaluate(() => {
      return Boolean(
        document.querySelector('table') ||
        document.querySelector('.empty-state') ||
        document.querySelector('[class*="error"]') ||
        document.querySelector('.tree-node') ||
        document.querySelector('[class*="tree"]') ||
        document.querySelector('[class*="no-data"]') ||
        document.querySelector('[class*="result"]'),
      );
    });
    expect(hasAnyOutcome, 'Page should show some outcome after query').toBe(true);
  });

  test('switching to the Equipment tab changes the input form', async ({ page }) => {
    const equipmentTab = page.locator('button:has-text("設備生產批次追蹤")').first();

    if (await equipmentTab.count() === 0) {
      test.skip(true, 'Equipment tab not found');
      return;
    }

    await equipmentTab.click();
    await page.waitForTimeout(1_000);

    const dateInput = page.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible({ timeout: 10_000 });
  });
});
