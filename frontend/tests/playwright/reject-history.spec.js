/**
 * E2E spec: Reject History page
 *
 * Flow:
 *  1. Login via API
 *  2. Navigate to /portal-shell/reject-history
 *  3. Fill date range in the filter panel and trigger query
 *  4. Handle BOTH sync (200) and async (202 + poll) response paths
 *  5. Assert that the data sections render (summary cards, pareto grid, detail table)
 *  6. Attempt CSV export (only if data is present)
 *
 * The backend returns 200 when the result is already cached, 202 + job_id
 * when it spools the job to RQ.  The frontend handles polling automatically,
 * so for Playwright we just need to wait long enough.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi } from './_auth.js';

const REJECT_HISTORY_URL = '/portal-shell/reject-history';

// A narrow date window that is unlikely to time out on a real server.
// Adjust if the dev DB has data only in a specific range.
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
    await page.goto(REJECT_HISTORY_URL);
    await page.waitForSelector('.reject-history-page, main, #app', { timeout: 20_000 });
  });

  test('page loads with filter panel visible', async ({ page }) => {
    // FilterPanel is always mounted; check for a date input
    const startInput = page.locator('input[type="date"], input[placeholder*="開始"], input[name*="start"]').first();
    await expect(startInput).toBeVisible({ timeout: 15_000 });
  });

  test('executes query and renders results (date range mode)', async ({ page }) => {
    const { start, end } = defaultDateRange();

    // Locate date inputs — the FilterPanel uses two date-type inputs
    const dateInputs = page.locator('input[type="date"]');
    const count = await dateInputs.count();

    if (count >= 2) {
      await dateInputs.nth(0).fill(start);
      await dateInputs.nth(1).fill(end);
    } else {
      // Inputs may use text type with specific names
      const startInput = page.locator('[name="startDate"], [name="start_date"], [placeholder*="開始日"]').first();
      const endInput = page.locator('[name="endDate"], [name="end_date"], [placeholder*="結束日"]').first();
      if (await startInput.count()) await startInput.fill(start);
      if (await endInput.count()) await endInput.fill(end);
    }

    // Click the query / submit button
    const queryBtn = page.locator(
      'button[type="submit"], button:has-text("查詢"), button:has-text("Query"), button:has-text("執行")'
    ).first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // The frontend may show a progress bar for async jobs.
    // Wait up to 120 s for the page to finish loading (both sync and async paths).
    await page.waitForFunction(
      () => {
        // Loading overlay gone AND no active job progress bar
        const overlay = document.querySelector('.loading-overlay, [class*="loading-overlay"]');
        const jobBar = document.querySelector('.async-job-status-bar');
        if (overlay || jobBar) return false;
        // At least one result section must be visible
        const hasResults =
          document.querySelector('.ui-card') ||
          document.querySelector('table') ||
          document.querySelector('.empty-state');
        return Boolean(hasResults);
      },
      { timeout: 120_000, polling: 2000 },
    );

    // After query completes, at minimum an empty state or data should be shown
    const resultArea = page.locator('.ui-card, table, .empty-state, [class*="EmptyState"]');
    await expect(resultArea.first()).toBeVisible({ timeout: 10_000 });
  });

  test('async job poll: handles 202 response path', async ({ page }) => {
    // Intercept the query endpoint to check the response status
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

    const queryBtn = page.locator(
      'button[type="submit"], button:has-text("查詢"), button:has-text("Query")'
    ).first();
    if (await queryBtn.count() === 0) return; // no query button found
    await queryBtn.click();

    // Wait for the query API call
    await page.waitForResponse(
      (r) => r.url().includes('/api/reject-history/query'),
      { timeout: 30_000 },
    ).catch(() => null);

    if (responseStatus === 202) {
      // Async path: the frontend should show a progress bar
      const progressBar = page.locator('.async-job-status-bar');
      // It might appear briefly — just verify it eventually goes away
      await page.waitForFunction(
        () => !document.querySelector('.async-job-status-bar'),
        { timeout: 120_000, polling: 3000 },
      );
    }
    // Either path: result area should be visible
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

    const queryBtn = page.locator(
      'button[type="submit"], button:has-text("查詢"), button:has-text("Query")'
    ).first();
    if (await queryBtn.count() === 0) return;
    await queryBtn.click();

    // Wait for results
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay') && !document.querySelector('.async-job-status-bar'),
      { timeout: 120_000, polling: 2000 },
    );

    // Look for export / CSV button
    const exportBtn = page.locator(
      'button:has-text("CSV"), button:has-text("匯出"), button:has-text("Export"), [title*="CSV"], [title*="匯出"]'
    ).first();

    if (await exportBtn.count() === 0) {
      // No export button visible — possibly no data; skip
      return;
    }
    await expect(exportBtn).toBeEnabled({ timeout: 10_000 });

    // Listen for the download event
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 30_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/\.(csv|parquet|zip)$/i);
  });
});
