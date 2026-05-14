/**
 * E2E spec: reject-history and material-trace flat-table layout assertions
 *
 * Verifies that DataTable renders as a single flat table with no nested card
 * wrappers inside .card-body in both pages (AC-1, AC-2, AC-6).
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

test.describe('reject-history 明細列表 — flat-table layout', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'reject-history', {
      waitForSelector: '.ui-card',
    });

    // Wait for initial load to settle
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay:not([style*="display: none"])'),
      { timeout: 30_000 },
    );
  });

  test('card structure: 明細列表 card has exactly one .ui-card outer wrapper — not nested', async ({ page }) => {
    // The 明細列表 card should exist
    const detailCard = page.locator('.ui-card').filter({ hasText: '明細列表' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // There must be exactly one .ui-card wrapping the detail table
    // (not two nested ones — which would indicate a "table within table" layout)
    const detailCardCount = await detailCard.count();
    expect(detailCardCount).toBe(1);
  });

  test('column presence: expected columns are visible in the 明細列表 detail table', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: '明細列表' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // Check key column headers are present in the detail table
    const table = detailCard.first().locator('table').first();
    await expect(table).toBeVisible({ timeout: 15_000 });

    const headerRow = table.locator('thead tr').first();
    await expect(headerRow).toBeVisible({ timeout: 10_000 });

    const headerText = await headerRow.innerText();
    expect(headerText).toContain('LOT');
    expect(headerText).toContain('WORKCENTER');
    expect(headerText).toContain('原因');
  });

  test('flat DOM structure: .card-body does NOT contain a nested .ui-card inside 明細列表', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: '明細列表' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // The card-body must not have a nested .ui-card — that would be "table within table"
    const cardBody = detailCard.first().locator('.card-body, .ui-card-body').first();
    await expect(cardBody).toBeVisible({ timeout: 10_000 });

    const nestedCard = cardBody.locator('.ui-card');
    const nestedCount = await nestedCard.count();
    expect(nestedCount).toBe(0);
  });

  test('pagination/info element present when reject-history results exist', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: '明細列表' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // Check pagination/info indicator is present (even if pagination arrows are hidden for single page)
    const tableInfoOrPagination = detailCard.first().locator(
      '.table-info, .pagination-control, [class*="pagination"], .data-table-footer',
    );

    // At least one of these pagination/info elements should exist
    const count = await tableInfoOrPagination.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});

test.describe('material-trace 查詢結果 — flat-table layout', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'material-trace', {
      waitForSelector: '.ui-card',
    });

    // Wait for initial load to settle
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay:not([style*="display: none"])'),
      { timeout: 30_000 },
    );
  });

  test('flat DOM structure: Result Card .card-body does NOT contain a nested .ui-card', async ({ page }) => {
    // Submit a minimal query to surface the Result Card
    // Fill a LOT-style value in the textarea input
    const textarea = page.locator('textarea.filter-textarea').first();
    await expect(textarea).toBeVisible({ timeout: 15_000 });
    await textarea.fill('TEST-LOT-*');

    const queryBtn = page.locator('button.ui-btn--primary').first();
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
    await queryBtn.click();

    // Wait for the Result Card to appear (it is v-if="hasResults || loading || paginationLoading")
    const resultCard = page.locator('.ui-card').filter({ hasText: '查詢結果' });
    await expect(resultCard.first()).toBeVisible({ timeout: 30_000 });

    // Wait for loading to finish
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay:not([style*="display: none"])'),
      { timeout: 30_000 },
    );

    // The card-body must not have a nested .ui-card — that would be "table within table"
    const cardBody = resultCard.first().locator('.card-body, .ui-card-body').first();
    await expect(cardBody).toBeVisible({ timeout: 10_000 });

    const nestedCard = cardBody.locator('.ui-card');
    const nestedCount = await nestedCard.count();
    expect(nestedCount).toBe(0);
  });
});
