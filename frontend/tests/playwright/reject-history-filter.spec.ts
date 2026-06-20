/**
 * E2E spec: reject-history filter panel interactions
 *
 * Covers:
 *   - Date mode filter panel visibility
 *   - Container mode switch (date inputs hidden, textarea visible)
 *   - Container input type selection (lot / work_order)
 *   - Checkbox filters present and in correct initial state
 *   - Checkbox state reflected in POST payload
 *   - Workcenter supplementary filter options appear after query
 *   - Date range included in POST payload
 *   - Pagination controls (page-prev / page-next) appear with multi-page data
 *   - datatable-row count matches mocked response
 *   - Empty state / zero-row table on empty response
 *
 * All API calls are mocked. No real backend required.
 * Routes registered FIRST (catch-all) then LAST (specific) per LIFO rule.
 *
 * Note: supplementary filters (workcenter-select, package-select, reason-select)
 * only render after queryId is set (i.e. after a successful primary query).
 * Tests that check those must click submit first.
 */

import { test, expect } from '@playwright/test';
import { navigateViaSidebar } from './_auth.js';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------

const MOCK_QUERY_ID = 'test-reject-filter-001';

function makeSyncResult(overrides: Record<string, unknown> = {}) {
  return {
    success: true,
    data: {
      query_id: MOCK_QUERY_ID,
      summary: {
        MOVEIN_QTY: 1000, REJECT_TOTAL_QTY: 10, DEFECT_QTY: 2,
        REJECT_RATE_PCT: 1.0, DEFECT_RATE_PCT: 0.2, REJECT_SHARE_PCT: 83.3,
        AFFECTED_LOT_COUNT: 3, AFFECTED_WORKORDER_COUNT: 2,
      },
      detail: {
        items: [],
        pagination: { page: 1, perPage: 50, total: 0, totalPages: 1 },
      },
      available_filters: {
        workcenter_groups: ['WC-TEST', 'WC-PROD'],
        packages: ['PKG-A', 'PKG-B'],
        reasons: ['SCRATCH', 'PARTICLE'],
        types: ['A', 'B'],
      },
      analytics_raw: [],
      total_row_count: 0,
      spool_download_url: null,
      ...overrides,
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function makeViewResult(overrides: Record<string, unknown> = {}) {
  return {
    success: true,
    data: {
      detail: {
        items: [],
        pagination: { page: 1, perPage: 50, total: 0, totalPages: 1 },
      },
      analytics_raw: [],
      available_filters: {
        workcenter_groups: ['WC-TEST', 'WC-PROD'],
        packages: ['PKG-A'],
        reasons: ['SCRATCH'],
        types: ['A'],
      },
      total_row_count: 0,
      spool_download_url: null,
      ...overrides,
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

function makeBatchParetoResult() {
  return {
    success: true,
    data: {
      reason: { items: [] },
      workcenter: { items: [] },
      package: { items: [] },
      equipment: { items: [] },
      product: { items: [] },
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };
}

// ---------------------------------------------------------------------------
// Shared route setup
// ---------------------------------------------------------------------------

async function setupBaseRoutes(page: import('@playwright/test').Page) {
  // Catch-all / infrastructure routes registered FIRST (LIFO: lowest priority)
  await page.route('**/api/auth/login**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser' } }),
    }),
  );
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

  // Catch-all for all reject-history endpoints (LIFO: lowest)
  await page.route('**/api/reject-history/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    }),
  );
  await page.route('**/api/job/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { status: 'finished', pct: 100 } }),
    }),
  );

  // Specific routes registered LAST (LIFO: highest priority)
  await page.route('**/api/reject-history/batch-pareto**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeBatchParetoResult()),
    }),
  );
  await page.route('**/api/reject-history/view**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeViewResult()),
    }),
  );
  await page.route('**/api/reject-history/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(makeSyncResult()),
    }),
  );
}

async function navigateToRejectHistory(page: import('@playwright/test').Page) {
  await navigateViaSidebar(page, 'reject-history', {
    waitForSelector: '[data-testid="reject-history-app"]',
  });
}

async function submitQueryAndWait(page: import('@playwright/test').Page) {
  const submitBtn = page.locator('[data-testid="query-submit-btn"]');
  await expect(submitBtn).toBeVisible({ timeout: 10_000 });
  await submitBtn.click();
  // Wait for query overlay and any async job bar to clear
  await page.waitForFunction(
    () => !document.querySelector('.loading-overlay') && !document.querySelector('.async-job-status-bar'),
    { timeout: 30_000, polling: 500 },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('reject-history — filter panel interactions', () => {

  test('test_date_mode_filter_panel', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    // App root present
    await expect(page.locator('[data-testid="reject-history-app"]')).toBeVisible({ timeout: 15_000 });

    // Date mode is default — date inputs visible
    await expect(page.locator('[data-testid="start-date"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="end-date"]')).toBeVisible({ timeout: 10_000 });

    // Submit button visible
    await expect(page.locator('[data-testid="query-submit-btn"]')).toBeVisible({ timeout: 10_000 });

    // Date mode tab is active
    const dateModeBtn = page.locator('[data-testid="query-mode-date"]');
    await expect(dateModeBtn).toBeVisible({ timeout: 10_000 });
    await expect(dateModeBtn).toHaveClass(/active/);
  });

  test('test_container_mode_switch', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    // Click container mode tab
    await page.click('[data-testid="query-mode-container"]');

    // Container textarea should appear
    await expect(page.locator('[data-testid="container-input"]')).toBeVisible({ timeout: 10_000 });

    // Date inputs should NOT be visible in container mode
    await expect(page.locator('[data-testid="start-date"]')).not.toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="end-date"]')).not.toBeVisible({ timeout: 5_000 });

    // Container mode tab should be active
    await expect(page.locator('[data-testid="query-mode-container"]')).toHaveClass(/active/);
  });

  test('test_container_type_workorder', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    await page.click('[data-testid="query-mode-container"]');
    await expect(page.locator('[data-testid="container-type-select"]')).toBeVisible({ timeout: 10_000 });

    // Select work_order option
    await page.selectOption('[data-testid="container-type-select"]', 'work_order');
    const selectValue = await page.locator('[data-testid="container-type-select"]').inputValue();
    expect(selectValue).toBe('work_order');
  });

  test('test_container_type_lot', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    await page.click('[data-testid="query-mode-container"]');
    await expect(page.locator('[data-testid="container-type-select"]')).toBeVisible({ timeout: 10_000 });

    // Default is lot
    const selectValue = await page.locator('[data-testid="container-type-select"]').inputValue();
    expect(selectValue).toBe('lot');

    // Can switch and switch back
    await page.selectOption('[data-testid="container-type-select"]', 'work_order');
    await page.selectOption('[data-testid="container-type-select"]', 'lot');
    expect(await page.locator('[data-testid="container-type-select"]').inputValue()).toBe('lot');
  });

  test('test_checkbox_filters_present', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    // All three checkboxes visible and unchecked by default
    const includeScrap = page.locator('[data-testid="include-excluded-scrap"]');
    const excludeMaterial = page.locator('[data-testid="exclude-material-scrap"]');
    const excludePb = page.locator('[data-testid="exclude-pb-diode"]');

    await expect(includeScrap).toBeVisible({ timeout: 10_000 });
    await expect(excludeMaterial).toBeVisible({ timeout: 10_000 });
    await expect(excludePb).toBeVisible({ timeout: 10_000 });

    // Default state: includeScrap=false, excludeMaterial=true, excludePb=true (both true by app default)
    expect(await includeScrap.isChecked()).toBe(false);
    expect(await excludeMaterial.isChecked()).toBe(true);
    expect(await excludePb.isChecked()).toBe(true);
  });

  test('test_checkbox_state_in_payload', async ({ page }) => {
    await setupBaseRoutes(page);

    let capturedBody: Record<string, unknown> | null = null;
    // Override query route to capture body — registered LAST (LIFO priority)
    await page.route('**/api/reject-history/query**', async (route) => {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSyncResult()),
      });
    });

    await navigateToRejectHistory(page);

    // Check include_excluded_scrap and exclude_pb_diode
    await page.check('[data-testid="include-excluded-scrap"]');
    await page.check('[data-testid="exclude-pb-diode"]');

    // Fill dates to pass validation
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');

    await submitQueryAndWait(page);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody!['include_excluded_scrap']).toBe(true);
    expect(capturedBody!['exclude_material_scrap']).toBe(true); // default is true; test did not uncheck it
    expect(capturedBody!['exclude_pb_diode']).toBe(true);
  });

  test('test_workcenter_filter_options', async ({ page }) => {
    await setupBaseRoutes(page);
    await navigateToRejectHistory(page);

    // Submit a query first so queryId is set and supplementary panel renders
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await submitQueryAndWait(page);

    // Supplementary panel (workcenter-select) should now be visible
    const wcSelect = page.locator('[data-testid="workcenter-select"]');
    await expect(wcSelect).toBeVisible({ timeout: 10_000 });

    // MultiSelect trigger should exist inside the workcenter-select wrapper
    const trigger = wcSelect.locator('[data-testid="multiselect-trigger"]');
    await expect(trigger).toBeVisible({ timeout: 10_000 });

    // Click trigger to open dropdown and verify options appear
    await trigger.click();
    // Dropdown is Teleported to <body> — must use page.locator, not wcSelect.locator
    const dropdown = page.locator('[data-testid="multiselect-dropdown"]');
    await expect(dropdown).toBeVisible({ timeout: 10_000 });

    const options = page.locator('[data-testid="multiselect-option"]');
    await expect(options.first()).toBeVisible({ timeout: 10_000 });
    expect(await options.count()).toBeGreaterThanOrEqual(1);
  });

  test('test_date_range_in_payload', async ({ page }) => {
    await setupBaseRoutes(page);

    let capturedBody: Record<string, unknown> | null = null;
    await page.route('**/api/reject-history/query**', async (route) => {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSyncResult()),
      });
    });

    await navigateToRejectHistory(page);

    await page.fill('[data-testid="start-date"]', '2026-03-01');
    await page.fill('[data-testid="end-date"]', '2026-03-31');
    await submitQueryAndWait(page);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody!['mode']).toBe('date_range');
    expect(capturedBody!['start_date']).toBe('2026-03-01');
    expect(capturedBody!['end_date']).toBe('2026-03-31');
  });

  test('test_pagination_appears', async ({ page }) => {
    await setupBaseRoutes(page);

    const items = Array.from({ length: 50 }, (_, i) => ({
      CONTAINERNAME: `GA26${String(i).padStart(6, '0')}`,
      WORKCENTERNAME: 'WC-TEST',
      PRODUCTLINENAME: 'PKG-A',
      PJ_FUNCTION: 'FN-X',
      PJ_TYPE: 'A',
      PRODUCTNAME: 'PROD-1',
      LOSSREASONNAME: 'SCRATCH',
      EQUIPMENTNAME: 'EQ-01',
      REJECTCOMMENT: '',
      REJECT_TOTAL_QTY: 1,
      DEFECT_QTY: 0,
      TXN_TIME: '2026-01-15 10:00:00',
    }));

    // Override with multi-page result
    await page.route('**/api/reject-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSyncResult({
          detail: {
            items: items.slice(0, 50),
            pagination: { page: 1, perPage: 50, total: 200, totalPages: 4 },
          },
          total_row_count: 200,
        })),
      }),
    );
    await page.route('**/api/reject-history/view**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeViewResult({
          detail: {
            items: items.slice(0, 50),
            pagination: { page: 1, perPage: 50, total: 200, totalPages: 4 },
          },
          total_row_count: 200,
        })),
      }),
    );

    await navigateToRejectHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await submitQueryAndWait(page);

    // PaginationControl (BasePagination) renders page-prev and page-next
    await expect(page.locator('[data-testid="page-next"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="page-prev"]')).toBeVisible({ timeout: 10_000 });
  });

  test('test_table_rows_count_matches', async ({ page }) => {
    await setupBaseRoutes(page);

    const items = [
      {
        CONTAINERNAME: 'GA250601', WORKCENTERNAME: 'WC-TEST', PRODUCTLINENAME: 'PKG-A',
        PJ_FUNCTION: 'FN-X', PJ_TYPE: 'A', PRODUCTNAME: 'PROD-1',
        LOSSREASONNAME: 'SCRATCH', EQUIPMENTNAME: 'EQ-01', REJECTCOMMENT: 'r1',
        REJECT_TOTAL_QTY: 5, DEFECT_QTY: 1, TXN_TIME: '2026-01-01 10:00:00',
      },
      {
        CONTAINERNAME: 'GA250602', WORKCENTERNAME: 'WC-TEST', PRODUCTLINENAME: 'PKG-B',
        PJ_FUNCTION: 'FN-Y', PJ_TYPE: 'B', PRODUCTNAME: 'PROD-2',
        LOSSREASONNAME: 'PARTICLE', EQUIPMENTNAME: 'EQ-02', REJECTCOMMENT: '',
        REJECT_TOTAL_QTY: 3, DEFECT_QTY: 0, TXN_TIME: '2026-01-02 10:00:00',
      },
      {
        CONTAINERNAME: 'GA250603', WORKCENTERNAME: 'WC-PROD', PRODUCTLINENAME: 'PKG-A',
        PJ_FUNCTION: 'FN-X', PJ_TYPE: 'A', PRODUCTNAME: 'PROD-1',
        LOSSREASONNAME: 'SCRATCH', EQUIPMENTNAME: 'EQ-03', REJECTCOMMENT: '',
        REJECT_TOTAL_QTY: 2, DEFECT_QTY: 0, TXN_TIME: '2026-01-03 10:00:00',
      },
    ];

    await page.route('**/api/reject-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSyncResult({
          detail: {
            items,
            pagination: { page: 1, perPage: 50, total: 3, totalPages: 1 },
          },
          total_row_count: 3,
        })),
      }),
    );
    await page.route('**/api/reject-history/view**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeViewResult({
          detail: {
            items,
            pagination: { page: 1, perPage: 50, total: 3, totalPages: 1 },
          },
          total_row_count: 3,
        })),
      }),
    );

    await navigateToRejectHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await submitQueryAndWait(page);

    const rows = page.locator('[data-testid="datatable-row"]');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    expect(await rows.count()).toBe(3);
  });

  test('test_empty_state_zero_results', async ({ page }) => {
    await setupBaseRoutes(page);

    // Query returns empty items
    await page.route('**/api/reject-history/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSyncResult({
          detail: {
            items: [],
            pagination: { page: 1, perPage: 50, total: 0, totalPages: 0 },
          },
          total_row_count: 0,
        })),
      }),
    );
    await page.route('**/api/reject-history/view**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeViewResult({
          detail: {
            items: [],
            pagination: { page: 1, perPage: 50, total: 0, totalPages: 0 },
          },
          total_row_count: 0,
        })),
      }),
    );

    await navigateToRejectHistory(page);
    await page.fill('[data-testid="start-date"]', '2026-01-01');
    await page.fill('[data-testid="end-date"]', '2026-01-31');
    await submitQueryAndWait(page);

    // DataTable renders datatable-empty when items is empty
    await expect(page.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 10_000 });

    // No data rows should exist
    const rows = page.locator('[data-testid="datatable-row"]');
    expect(await rows.count()).toBe(0);
  });

});
