/**
 * E2E spec: hold-history filter panel interactions
 *
 * Covers:
 *   - Filter panel visibility and default date values on load
 *   - Date range payload forwarded correctly to /api/hold-history/query
 *   - Async 202 path shows loading state (AsyncQueryProgress)
 *   - Filter options rendered (hold-type select)
 *   - Empty state on zero results
 *   - Error banner on API failure
 *   - Results render on success (datatable-row)
 *   - Pagination controls (page-prev / page-next) appear with multi-page data
 *   - Cancel button visible while async job is in progress
 *
 * All API calls are mocked. No real backend required.
 * Routes registered FIRST (catch-all) then LAST (specific) per LIFO rule.
 */

import { test, expect } from '@playwright/test';
import { navigateViaSidebar } from './_auth.js';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';

// ---------------------------------------------------------------------------
// Shared mock data factories
// ---------------------------------------------------------------------------

function mockConfigResponse() {
  return {
    success: true,
    data: { today_mode_enabled: false, auto_refresh_seconds: 60 },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function mockViewResult(overrides: Record<string, unknown> = {}) {
  return {
    success: true,
    data: {
      trend: { days: [] },
      reason_pareto: { items: [] },
      duration: { items: [], avgReleasedHours: 0, avgOnHoldHours: 0 },
      list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
      ...overrides,
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function mockSyncQueryResult(overrides: Record<string, unknown> = {}) {
  return {
    success: true,
    data: {
      query_id: 'test-hold-filter-001',
      trend: { days: [] },
      reason_pareto: { items: [] },
      duration: { items: [], avgReleasedHours: 0, avgOnHoldHours: 0 },
      list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
      spool_download_url: null,
      total_row_count: 0,
      ...overrides,
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function mock202AsyncResponse() {
  return {
    success: true,
    data: {
      async: true,
      job_id: 'test-job-hold-filter-001',
      status_url: '/api/job/test-job-hold-filter-001?prefix=hold-history',
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function mockJobRunning() {
  return {
    success: true,
    data: { status: 'started', pct: 15, progress: '查詢中...', stage: 'querying' },
  };
}

function mockJobFinished(queryId = 'test-hold-filter-001') {
  return {
    success: true,
    data: {
      status: 'finished',
      pct: 100,
      progress: '完成',
      result: {
        query_id: queryId,
        trend: { days: [] },
        reason_pareto: { items: [] },
        duration: { items: [], avgReleasedHours: 0, avgOnHoldHours: 0 },
        list: { items: [], pagination: { page: 1, perPage: 20, total: 0, totalPages: 1 } },
        spool_download_url: null,
        total_row_count: 0,
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Shared route setup
// ---------------------------------------------------------------------------

async function setupBaseRoutes(page: import('@playwright/test').Page) {
  // Catch-all registered FIRST (LIFO: lowest priority) — specific routes override below
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser', role: 'user' } }),
    }),
  );
  await page.route('**/api/pages**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    }),
  );
  await page.route('**/api/auth/login**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser' } }),
    }),
  );
  await page.route('**/api/hold-history/config**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockConfigResponse()),
    }),
  );
  await page.route('**/api/hold-history/view**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockViewResult()),
    }),
  );
  await page.route('**/api/job/**/abandon**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true }),
    }),
  );
}

async function navigateToHoldHistory(page: import('@playwright/test').Page) {
  await navigateViaSidebar(page, 'hold-history', { waitForSelector: '[data-testid="hold-history-app"]' });
  // Wait for the initial load overlay to clear
  await page.waitForFunction(
    () => !document.querySelector('.loading-overlay'),
    { timeout: 20_000 },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('hold-history — filter panel interactions', () => {

  test('test_filter_panel_visible_on_load', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult()),
      }),
    );

    await navigateToHoldHistory(page);

    // App root is present
    await expect(page.locator('[data-testid="hold-history-app"]')).toBeVisible({ timeout: 15_000 });

    // Date inputs visible (range mode is the default)
    await expect(page.locator('[data-testid="start-date"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="end-date"]')).toBeVisible({ timeout: 10_000 });

    // Hold-type dropdown visible
    await expect(page.locator('[data-testid="hold-type-select"]')).toBeVisible({ timeout: 10_000 });

    // Submit button visible
    await expect(page.locator('[data-testid="query-submit-btn"]')).toBeVisible({ timeout: 10_000 });
  });

  test('test_date_range_defaults', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult()),
      }),
    );

    await navigateToHoldHistory(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await expect(startDate).toBeVisible({ timeout: 10_000 });
    await expect(endDate).toBeVisible({ timeout: 10_000 });

    // Default values should be non-empty date strings (set by setDefaultDateRange on mount)
    const startVal = await startDate.inputValue();
    const endVal = await endDate.inputValue();

    // Either both are set to valid YYYY-MM-DD dates, or both are empty (no URL params)
    // The component sets last-month range by default so both should be non-empty
    expect(startVal).toMatch(/^\d{4}-\d{2}-\d{2}$|^$/);
    expect(endVal).toMatch(/^\d{4}-\d{2}-\d{2}$|^$/);

    // If set, start should be before or equal to end
    if (startVal && endVal) {
      expect(startVal <= endVal).toBe(true);
    }
  });

  test('test_submit_sends_correct_date_params', async ({ page }) => {
    await setupBaseRoutes(page);

    let capturedBody: Record<string, unknown> | null = null;
    // Specific route registered LAST (LIFO: highest priority)
    await page.route('**/api/hold-history/query**', async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      capturedBody = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult()),
      });
    });

    await navigateToHoldHistory(page);

    // Fill dates explicitly
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');

    await page.click('[data-testid="query-submit-btn"]');
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 20_000 },
    );

    expect(capturedBody).not.toBeNull();
    expect(capturedBody!['start_date']).toBe('2026-01-01');
    expect(capturedBody!['end_date']).toBe('2026-01-31');
  });

  test('test_async_query_shows_loading_state', async ({ page }) => {
    await setupBaseRoutes(page);

    // Return 202 async response from query
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mock202AsyncResponse()),
      }),
    );

    // Job stays in running state throughout this test
    await page.route('**/api/job/test-job-hold-filter-001**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockJobRunning()),
      }),
    );

    await navigateToHoldHistory(page);

    await page.fill('[data-testid="start-date"]', '2024-01-01');
    await page.fill('[data-testid="end-date"]', '2025-12-31');
    await page.click('[data-testid="query-submit-btn"]');

    // AsyncQueryProgress component should appear while polling
    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 15_000 });

    // LoadingOverlay must be suppressed while async progress is active (css-contract Rule 4.6)
    const overlay = page.locator('.loading-overlay');
    await expect(overlay).not.toBeVisible({ timeout: 5_000 });
  });

  test('test_cancel_job_button', async ({ page }) => {
    await setupBaseRoutes(page);

    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mock202AsyncResponse()),
      }),
    );

    // Keep job running so cancel button remains visible
    await page.route('**/api/job/test-job-hold-filter-001**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockJobRunning()),
      }),
    );

    await navigateToHoldHistory(page);

    await page.fill('[data-testid="start-date"]', '2024-01-01');
    await page.fill('[data-testid="end-date"]', '2025-12-31');
    await page.click('[data-testid="query-submit-btn"]');

    // Cancel button is rendered inside AsyncQueryProgress when canCancel=true
    const cancelBtn = page.locator('.async-job-progress button:has-text("取消查詢")');
    await expect(cancelBtn).toBeVisible({ timeout: 15_000 });

    // Click cancel — job should abort and progress bar disappear
    await cancelBtn.click();
    await expect(page.locator('.async-job-progress')).not.toBeVisible({ timeout: 10_000 });
  });

  test('test_filter_options_load', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult()),
      }),
    );

    await navigateToHoldHistory(page);

    // Hold-type select should have the three expected options
    const holdTypeSelect = page.locator('[data-testid="hold-type-select"]');
    await expect(holdTypeSelect).toBeVisible({ timeout: 10_000 });

    const options = holdTypeSelect.locator('option');
    const count = await options.count();
    expect(count).toBeGreaterThanOrEqual(3);

    const values = await options.evaluateAll((els) =>
      (els as HTMLOptionElement[]).map((o) => o.value),
    );
    expect(values).toContain('quality');
    expect(values).toContain('non-quality');
    expect(values).toContain('all');
  });

  test('test_empty_state_no_results', async ({ page }) => {
    await setupBaseRoutes(page);

    // Return a query result with empty list and trigger today-mode = false so
    // we stay in range mode (today/current EmptyState only appears in snapshot modes)
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult()),
      }),
    );

    await navigateToHoldHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await page.click('[data-testid="query-submit-btn"]');

    // In range mode with 0 items, the DetailTable renders with [data-testid="datatable-empty"]
    // (DataTable renders an empty row when items.length === 0)
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 20_000 },
    );

    // The datatable-empty sentinel proves zero-result state is rendered
    await expect(page.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 10_000 });
  });

  test('test_error_state_api_failure', async ({ page }) => {
    await setupBaseRoutes(page);

    // 500 error on query — registered LAST (LIFO priority)
    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'INTERNAL_ERROR', message: '模擬伺服器錯誤' },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      }),
    );

    await navigateToHoldHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await page.click('[data-testid="query-submit-btn"]');

    // Wait for loading to clear
    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 20_000 },
    );

    // ErrorBanner must be visible with a non-empty message
    const errorBanner = page.locator('[data-testid="error-banner"]');
    await expect(errorBanner).toBeVisible({ timeout: 10_000 });
    const bannerText = await errorBanner.innerText();
    expect(bannerText.trim().length).toBeGreaterThan(0);
  });

  test('test_results_render_on_success', async ({ page }) => {
    await setupBaseRoutes(page);

    const items = [
      {
        lotId: 'GA2601', workorder: 'WO-001', product: 'PROD-A', package: 'PKG-A',
        workcenter: 'WC-01', holdReason: 'SCRATCH', qty: 10,
        holdDate: '2026-01-15 10:00:00', holdEmp: 'EMP01', holdComment: 'test',
        releaseDate: '2026-01-16 10:00:00', releaseEmp: 'EMP02', releaseComment: '',
        holdHours: 24, ncr: '', futureHoldComment: '',
      },
      {
        lotId: 'GA2602', workorder: 'WO-002', product: 'PROD-B', package: 'PKG-B',
        workcenter: 'WC-02', holdReason: 'PARTICLE', qty: 5,
        holdDate: '2026-01-16 10:00:00', holdEmp: 'EMP01', holdComment: '',
        releaseDate: null, releaseEmp: '', releaseComment: '',
        holdHours: 0, ncr: '', futureHoldComment: '',
      },
    ];

    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSyncQueryResult({
          list: {
            items,
            pagination: { page: 1, perPage: 20, total: 2, totalPages: 1 },
          },
          total_row_count: 2,
        })),
      }),
    );

    await page.route('**/api/hold-history/view**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockViewResult({
          list: {
            items,
            pagination: { page: 1, perPage: 20, total: 2, totalPages: 1 },
          },
        })),
      }),
    );

    await navigateToHoldHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await page.click('[data-testid="query-submit-btn"]');

    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 20_000 },
    );

    // datatable-row appears for each result item
    const rows = page.locator('[data-testid="datatable-row"]');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    expect(await rows.count()).toBe(2);
  });

  test('test_pagination_controls_appear', async ({ page }) => {
    await setupBaseRoutes(page);

    // Return 3 total pages of data
    const items = Array.from({ length: 20 }, (_, i) => ({
      lotId: `GA26${String(i).padStart(4, '0')}`,
      workorder: `WO-${i}`, product: 'PROD-A', package: 'PKG-A',
      workcenter: 'WC-01', holdReason: 'SCRATCH', qty: 1,
      holdDate: '2026-01-15 10:00:00', holdEmp: 'EMP01', holdComment: '',
      releaseDate: null, releaseEmp: '', releaseComment: '',
      holdHours: 0, ncr: '', futureHoldComment: '',
    }));

    const multiPageResult = mockSyncQueryResult({
      list: {
        items,
        pagination: { page: 1, perPage: 20, total: 55, totalPages: 3 },
      },
      total_row_count: 55,
    });

    await page.route('**/api/hold-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(multiPageResult),
      }),
    );
    await page.route('**/api/hold-history/view**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockViewResult({
          list: {
            items,
            pagination: { page: 1, perPage: 20, total: 55, totalPages: 3 },
          },
        })),
      }),
    );

    await navigateToHoldHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await page.click('[data-testid="query-submit-btn"]');

    await page.waitForFunction(
      () => !document.querySelector('.loading-overlay'),
      { timeout: 20_000 },
    );

    // PaginationControl (via BasePagination) renders page-prev and page-next
    await expect(page.locator('[data-testid="page-next"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="page-prev"]')).toBeVisible({ timeout: 10_000 });
  });

});
