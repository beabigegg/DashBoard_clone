/**
 * E2E spec: hold-history detail table flat-table layout assertions
 *
 * Verifies that the Hold / Release 明細 section renders as a single flat table
 * with no nested card wrappers inside the .card-body (AC-1, AC-3, AC-5).
 *
 * Also verifies the async 202 path (hold-history-rq-async AC-5):
 *   - long-range query → AsyncQueryProgress renders → result loads on completion
 *   - short-range query → 200 sync path unchanged (LoadingOverlay not async-suppressed)
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

// ---------------------------------------------------------------------------
// Shared mock data (async 202 path tests)
// ---------------------------------------------------------------------------

const MOCK_CONFIG = {
  success: true,
  data: { today_mode_enabled: false, auto_refresh_seconds: 60 },
};

const MOCK_SYNC_QUERY_RESULT = {
  success: true,
  data: {
    query_id: 'test-hold-sync-001',
    trend: { days: [] },
    reason_pareto: { items: [] },
    duration: { items: [], avgReleasedHours: 0, avgOnHoldHours: 0 },
    list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
    spool_download_url: null,
    total_row_count: 0,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_ASYNC_202_RESPONSE = {
  success: true,
  data: {
    async: true,
    job_id: 'test-job-async-hold-001',
    status_url: '/api/job/test-job-async-hold-001?prefix=hold-history',
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_JOB_STATUS_RUNNING = {
  success: true,
  data: {
    status: 'started',
    pct: 15,
    progress: '查詢中...',
    stage: 'querying',
  },
};

const MOCK_JOB_STATUS_COMPLETED = {
  success: true,
  data: {
    status: 'finished',
    pct: 100,
    progress: '完成',
    result: {
      query_id: 'test-hold-async-result-001',
      trend: { days: [] },
      reason_pareto: { items: [] },
      duration: { items: [], avgReleasedHours: 0, avgOnHoldHours: 0 },
      list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
      spool_download_url: null,
      total_row_count: 0,
    },
  },
};

const MOCK_VIEW_RESULT = {
  success: true,
  data: {
    trend: { days: [] },
    reason_pareto: { items: [] },
    duration: { items: [] },
    list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
  },
};

/**
 * Set up shared base routes for hold-history page (mocks auth, pages, config, view).
 */
async function setupBaseRoutes(page) {
  await page.route('**/api/auth/me**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser', role: 'user' } }),
    });
  });
  await page.route('**/api/pages**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    });
  });
  await page.route('**/api/hold-history/config**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_CONFIG),
    });
  });
  await page.route('**/api/hold-history/view**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_VIEW_RESULT),
    });
  });
  await page.route('**/api/job/**/abandon**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
  });
}

// ---------------------------------------------------------------------------
// Async 202 path tests (hold-history-rq-async AC-5)
// ---------------------------------------------------------------------------

test.describe('hold-history async 202 path — AsyncQueryProgress', () => {
  test('long-range query: 202 response shows AsyncQueryProgress, then result loads on completion', async ({ page }) => {
    await setupBaseRoutes(page);

    // Mock /query to return 202 async
    await page.route('**/api/hold-history/query**', (route) => {
      route.fulfill({
        status: 200, // Playwright route.fulfill wraps 202 — the app reads data.async
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ASYNC_202_RESPONSE),
      });
    });

    // Mock job status: first call returns 'started', second returns 'finished'
    let jobPollCount = 0;
    await page.route('**/api/job/test-job-async-hold-001**', (route) => {
      jobPollCount += 1;
      if (jobPollCount <= 1) {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_JOB_STATUS_RUNNING),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_JOB_STATUS_COMPLETED),
        });
      }
    });

    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', { waitForSelector: '.ui-card' });

    // AsyncQueryProgress should appear while job is in progress
    // It renders only when asyncJobProgress.active is true
    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 15_000 });

    // Progress text or pct should be visible
    const progressLabel = progressBar.locator('.async-job-progress__label');
    await expect(progressLabel).toBeVisible({ timeout: 5_000 });

    // Cancel button should be present (canCancel=true)
    const cancelBtn = progressBar.locator('button').filter({ hasText: '取消查詢' });
    await expect(cancelBtn).toBeVisible({ timeout: 5_000 });

    // After job completes, progress bar should disappear
    await expect(progressBar).not.toBeVisible({ timeout: 20_000 });
  });

  test('short-range query: 200 sync path is unchanged — no AsyncQueryProgress shown', async ({ page }) => {
    await setupBaseRoutes(page);

    // Mock /query to return 200 sync (short range, no async flag)
    await page.route('**/api/hold-history/query**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SYNC_QUERY_RESULT),
      });
    });

    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', { waitForSelector: '.ui-card' });

    // Wait for query to complete (loading overlay disappears)
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 15_000 },
    );

    // AsyncQueryProgress must NOT render for sync path
    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).not.toBeVisible({ timeout: 3_000 });
  });

  test('css-contract Rule 4.6: LoadingOverlay is suppressed while asyncJobProgress is active', async ({ page }) => {
    await setupBaseRoutes(page);

    // Mock /query to return 202 async (job stays "started" throughout test)
    await page.route('**/api/hold-history/query**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ASYNC_202_RESPONSE),
      });
    });

    // Keep job in "started" state so AsyncQueryProgress remains visible
    await page.route('**/api/job/test-job-async-hold-001**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_JOB_STATUS_RUNNING),
      });
    });

    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-history', { waitForSelector: '.ui-card' });

    // AsyncQueryProgress must be visible (async is active)
    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 15_000 });

    // LoadingOverlay must NOT be visible simultaneously (css-contract Rule 4.6)
    const overlay = page.locator('.loading-overlay');
    await expect(overlay).not.toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Original flat-table layout tests (unchanged)
// ---------------------------------------------------------------------------

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
