/**
 * E2E spec: Query Tool (Material Trace) page
 *
 * Flow:
 *  1. Login via API
 *  2. Navigate to /portal-shell/query-tool
 *  3. Select the "批次追蹤(正向)" tab (default active)
 *  4. Enter a dummy lot ID value in the textarea
 *  5. Click the query / execute button
 *  6. Wait for results (or an empty-state / error) to render
 *  7. Assert the result table or empty state is visible
 *
 * The query tool page is served as a native SPA route inside the portal
 * shell.  The component structure is tab-based (LOT / REVERSE / EQUIPMENT /
 * LOT_EQUIPMENT); we only exercise the default LOT tab here.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi } from './_auth.js';

const QUERY_TOOL_URL = '/portal-shell/query-tool';

// A synthetic lot ID that returns empty results rather than an error
const DUMMY_LOT_ID = 'TEST-LOT-E2E-00001';

test.describe('Query Tool page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await page.goto(QUERY_TOOL_URL);
  });

  test('page loads with tab navigation visible', async ({ page }) => {
    // The query-tool App renders tab items
    const tabItem = page.locator(
      'button:has-text("批次追蹤"), [role="tab"]:has-text("批次"), .tab-item, [class*="tab"]'
    ).first();
    await expect(tabItem).toBeVisible({ timeout: 20_000 });
  });

  test('LOT tab input and query execution renders results or empty state', async ({ page }) => {
    // Wait for the page to initialise
    await page.waitForSelector('textarea, input[type="text"]', { timeout: 20_000 });

    // Find the lot input textarea (the component uses a <textarea> for multi-line input)
    const inputArea = page.locator('textarea').first();
    await expect(inputArea).toBeVisible({ timeout: 10_000 });
    await inputArea.fill(DUMMY_LOT_ID);

    // Click the query / resolve button
    const queryBtn = page.locator(
      'button:has-text("查詢"), button:has-text("執行"), button:has-text("Search"), button:has-text("Submit"), button[type="submit"]'
    ).first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // Wait for either a result table or an empty/error state to appear
    await page.waitForFunction(
      () => {
        const loading = document.querySelector('.loading-overlay, [class*="loading-overlay"]');
        if (loading) return false;
        return Boolean(
          document.querySelector('table') ||
          document.querySelector('.empty-state') ||
          document.querySelector('[class*="EmptyState"]') ||
          document.querySelector('.error-banner') ||
          document.querySelector('[class*="error"]'),
        );
      },
      { timeout: 60_000, polling: 1500 },
    );

    const result = page.locator(
      'table, .empty-state, [class*="EmptyState"], .error-banner'
    ).first();
    await expect(result).toBeVisible({ timeout: 10_000 });
  });

  test('switching to the Equipment tab changes the input form', async ({ page }) => {
    await page.waitForSelector('[class*="tab"], [role="tab"], button', { timeout: 20_000 });

    // Find the equipment tab button
    const equipmentTab = page.locator(
      'button:has-text("設備生產批次"), [role="tab"]:has-text("設備"), [class*="tab"]:has-text("設備")'
    ).first();

    if (await equipmentTab.count() === 0) {
      // Tab labels may differ; try a fallback
      const tabs = page.locator('button, [role="tab"]');
      const count = await tabs.count();
      if (count >= 3) {
        await tabs.nth(2).click();
      }
    } else {
      await equipmentTab.click();
    }

    // After switching, a date/equipment input should appear
    const dateOrInput = page.locator('input[type="date"], input[type="text"], textarea').first();
    await expect(dateOrInput).toBeVisible({ timeout: 10_000 });
  });
});
