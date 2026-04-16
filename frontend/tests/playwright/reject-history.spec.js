/**
 * E2E spec: Reject History page
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 * Handles both sync (200) and async (202 + poll) response paths.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

function defaultDateRange() {
  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - 7);
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

test.describe('Reject History page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
    });
  });

  test('page loads with filter panel visible', async ({ page }) => {
    const startInput = page.locator('input[type="date"]').first();
    await expect(startInput).toBeVisible({ timeout: 15_000 });
  });

  test('executes query and renders results (date range mode)', async ({ page }) => {
    const { start, end } = defaultDateRange();

    const dateInputs = page.locator('input[type="date"]');
    if (await dateInputs.count() >= 2) {
      await dateInputs.nth(0).fill(start);
      await dateInputs.nth(1).fill(end);
    }

    const queryBtn = page.locator('button:has-text("查詢")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    await page.waitForFunction(
      () => {
        const overlay = document.querySelector('.loading-overlay, [class*="loading-overlay"]');
        const jobBar = document.querySelector('.async-job-status-bar');
        if (overlay || jobBar) return false;
        return Boolean(
          document.querySelector('.ui-card') ||
          document.querySelector('table') ||
          document.querySelector('.empty-state'),
        );
      },
      { timeout: 120_000, polling: 2000 },
    );

    const resultArea = page.locator('.ui-card, table, .empty-state');
    await expect(resultArea.first()).toBeVisible({ timeout: 10_000 });
  });

  test('async job poll: handles 202 response path', async ({ page }) => {
    let responseStatus = null;
    page.on('response', (response) => {
      if (response.url().includes('/api/reject-history/query')) {
        responseStatus = response.status();
      }
    });

    const { start, end } = defaultDateRange();
    const dateInputs = page.locator('input[type="date"]');
    if (await dateInputs.count() >= 2) {
      await dateInputs.nth(0).fill(start);
      await dateInputs.nth(1).fill(end);
    }

    const queryBtn = page.locator('button:has-text("查詢")').first();
    if (await queryBtn.count() === 0) {
      test.skip(true, 'No query button found');
      return;
    }
    await queryBtn.click();

    await page.waitForResponse(
      (r) => r.url().includes('/api/reject-history'),
      { timeout: 30_000 },
    ).catch(() => null);

    if (responseStatus === 202) {
      await page.waitForFunction(
        () => !document.querySelector('.async-job-status-bar'),
        { timeout: 120_000, polling: 3000 },
      );
    }

    await expect(page.locator('.ui-card, table, .empty-state').first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test('CSV export button triggers file download when data exists', async ({ page }) => {
    const { start, end } = defaultDateRange();
    const dateInputs = page.locator('input[type="date"]');
    if (await dateInputs.count() >= 2) {
      await dateInputs.nth(0).fill(start);
      await dateInputs.nth(1).fill(end);
    }

    const queryBtn = page.locator('button:has-text("查詢")').first();
    if (await queryBtn.count() === 0) return;
    await queryBtn.click();

    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay') && !document.querySelector('.async-job-status-bar'),
      { timeout: 120_000, polling: 2000 },
    );

    const exportBtn = page.locator(
      'button:has-text("匯出 CSV"), button:has-text("CSV"), button:has-text("匯出")'
    ).first();

    if (await exportBtn.count() === 0) return;
    await expect(exportBtn).toBeEnabled({ timeout: 10_000 });

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 30_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/\.(csv|parquet|zip)$/i);
  });
});
