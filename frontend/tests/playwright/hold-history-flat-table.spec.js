/**
 * E2E spec: hold-history detail table flat-table layout assertions
 *
 * Verifies that the Hold / Release 明細 section renders as a single flat table
 * with no nested card wrappers inside the .card-body (AC-1, AC-3, AC-5).
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

test.describe('hold-history detail table — flat-table layout', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', {
      waitForSelector: '.ui-card',
    });

    // Wait for initial load to settle
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay:not([style*="display: none"])'),
      { timeout: 30_000 },
    );
  });

  test('card structure: detail section has exactly one .card.ui-card outer wrapper — not nested', async ({ page }) => {
    // The Hold / Release 明細 card should exist
    const detailCard = page.locator('.ui-card').filter({ hasText: 'Hold / Release 明細' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // There must be exactly one .card.ui-card wrapping the detail table
    // (not two nested ones — which would indicate a "table within table" layout)
    const detailCardCount = await detailCard.count();
    expect(detailCardCount).toBe(1);
  });

  test('column presence: expected columns are visible in the detail table', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: 'Hold / Release 明細' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // Check key column headers are present in the detail table
    const table = detailCard.first().locator('table').first();
    await expect(table).toBeVisible({ timeout: 15_000 });

    const headerRow = table.locator('thead tr').first();
    await expect(headerRow).toBeVisible({ timeout: 10_000 });

    const headerText = await headerRow.innerText();
    expect(headerText).toContain('Lot ID');
    expect(headerText).toContain('WorkOrder');
    expect(headerText).toContain('Hold Reason');
  });

  test('flat DOM structure: .card-body does NOT contain a nested .ui-card inside it', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: 'Hold / Release 明細' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // The card-body must not have a nested .ui-card — that would be "table within table"
    const cardBody = detailCard.first().locator('.card-body, .ui-card-body').first();
    await expect(cardBody).toBeVisible({ timeout: 10_000 });

    const nestedCard = cardBody.locator('.ui-card');
    const nestedCount = await nestedCard.count();
    expect(nestedCount).toBe(0);
  });

  test('pagination visible when results exist', async ({ page }) => {
    const detailCard = page.locator('.ui-card').filter({ hasText: 'Hold / Release 明細' });
    await expect(detailCard.first()).toBeVisible({ timeout: 20_000 });

    // Check total count indicator is present (even if pagination arrows are hidden for single page)
    const tableInfoOrPagination = detailCard.first().locator(
      '.table-info, .pagination-control, [class*="pagination"], .data-table-footer'
    );

    // At least one of these pagination/info elements should exist
    const count = await tableInfoOrPagination.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
