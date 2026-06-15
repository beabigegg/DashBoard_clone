/**
 * E2E spec: reject-history and material-trace flat-table layout assertions
 *
 * Verifies that DataTable renders as a single flat table with no nested card
 * wrappers inside .card-body in both pages (AC-1, AC-2, AC-6).
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 * All API calls are mocked to avoid Oracle dependency.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

// ---------------------------------------------------------------------------
// Shared reject-history mock data
// ---------------------------------------------------------------------------

const MOCK_QUERY_ID = 'test-flat-table-query-001';

const MOCK_DETAIL_ITEMS = [
  {
    CONTAINERNAME: 'GA250601',
    WORKCENTERNAME: 'WC-TEST',
    PRODUCTLINENAME: 'PKG-A',
    PJ_FUNCTION: 'FN-X',
    PJ_TYPE: 'A',
    PRODUCTNAME: 'PROD-1',
    LOSSREASONNAME: 'SCRATCH',
    EQUIPMENTNAME: 'EQ-01',
    REJECTCOMMENT: 'test comment',
    REJECT_TOTAL_QTY: 5,
    DEFECT_QTY: 1,
    TXN_TIME: '2025-06-01 10:00:00',
  },
  {
    CONTAINERNAME: 'GA250602',
    WORKCENTERNAME: 'WC-PROD',
    PRODUCTLINENAME: 'PKG-B',
    PJ_FUNCTION: 'FN-Y',
    PJ_TYPE: 'B',
    PRODUCTNAME: 'PROD-2',
    LOSSREASONNAME: 'PARTICLE',
    EQUIPMENTNAME: 'EQ-02',
    REJECTCOMMENT: '',
    REJECT_TOTAL_QTY: 3,
    DEFECT_QTY: 0,
    TXN_TIME: '2025-06-01 11:00:00',
  },
];

const MOCK_SYNC_QUERY_RESULT = {
  success: true,
  data: {
    query_id: MOCK_QUERY_ID,
    summary: {
      MOVEIN_QTY: 1000,
      REJECT_TOTAL_QTY: 8,
      DEFECT_QTY: 1,
      REJECT_RATE_PCT: 0.8,
      DEFECT_RATE_PCT: 0.1,
      REJECT_SHARE_PCT: 88.9,
      AFFECTED_LOT_COUNT: 2,
      AFFECTED_WORKORDER_COUNT: 2,
    },
    detail: {
      items: MOCK_DETAIL_ITEMS,
      pagination: { page: 1, perPage: 50, total: 2, totalPages: 1 },
    },
    available_filters: {
      workcenter_groups: ['WC-TEST', 'WC-PROD'],
      packages: ['PKG-A', 'PKG-B'],
      reasons: ['SCRATCH', 'PARTICLE'],
    },
    analytics_raw: [],
    total_row_count: 2,
    spool_download_url: null,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_VIEW_RESULT = {
  success: true,
  data: {
    detail: {
      items: MOCK_DETAIL_ITEMS,
      pagination: { page: 1, perPage: 50, total: 2, totalPages: 1 },
    },
    analytics_raw: [],
    available_filters: MOCK_SYNC_QUERY_RESULT.data.available_filters,
    total_row_count: 2,
    spool_download_url: null,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_BATCH_PARETO = {
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

async function setupRejectHistoryMocks(page) {
  // Catch-all registered FIRST (lowest LIFO priority) — specific routes below take precedence
  await page.route('**/api/reject-history/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    })
  );
  await page.route('**/api/job/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { status: 'finished', pct: 100 } }),
    })
  );
  // Specific routes registered LAST (highest LIFO priority) — override catch-all
  await page.route('**/api/reject-history/batch-pareto', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BATCH_PARETO),
    })
  );
  await page.route('**/api/reject-history/view', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_VIEW_RESULT),
    })
  );
  await page.route('**/api/reject-history/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SYNC_QUERY_RESULT),
    })
  );
}

// ---------------------------------------------------------------------------
// reject-history 明細列表 tests
// ---------------------------------------------------------------------------

test.describe('reject-history 明細列表 — flat-table layout', () => {
  test.beforeEach(async ({ page }) => {
    await setupRejectHistoryMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'reject-history', {
      waitForSelector: '.ui-card',
    });

    // Trigger the query so DetailTable renders (reject-history does not auto-query on mount)
    const queryBtn = page.locator('button:has-text("查詢")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // Wait for initial load to settle — loading overlay gone and DetailTable rendered
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

// ---------------------------------------------------------------------------
// material-trace 查詢結果 tests
// ---------------------------------------------------------------------------

const MOCK_MATERIAL_TRACE_ROWS = [
  {
    CONTAINERNAME: 'GA250601',
    PJ_WORKORDER: 'WO-001',
    WORKCENTER_GROUP: 'WCG-A',
    WORKCENTERNAME: 'WC-TEST',
    MATERIALPARTNAME: 'PART-001',
    MATERIALLOTNAME: 'MAT-LOT-001',
    VENDORLOTNUMBER: 'VL-001',
    QTYREQUIRED: 10,
    QTYCONSUMED: 10,
    EQUIPMENTNAME: 'EQ-01',
    TXNDATE: '2025-06-01',
    PRIMARY_CATEGORY: 'A',
    SECONDARY_CATEGORY: 'B',
  },
];

const MOCK_MATERIAL_TRACE_RESULT = {
  success: true,
  data: {
    rows: MOCK_MATERIAL_TRACE_ROWS,
    pagination: { page: 1, per_page: 20, total: 1, total_pages: 1 },
    meta: { unresolved: [], max_rows: null },
    quality_meta: { status: 'complete' },
    query_hash: 'test-hash-001',
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

async function setupMaterialTraceMocks(page) {
  // Catch-all registered FIRST (lowest LIFO priority) — specific routes below take precedence
  await page.route('**/api/material-trace/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    })
  );
  // Specific routes registered LAST (highest LIFO priority) — override catch-all
  await page.route('**/api/material-trace/filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { workcenter_groups: ['WCG-A', 'WCG-B'] },
        meta: {},
      }),
    })
  );
  await page.route('**/api/material-trace/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_MATERIAL_TRACE_RESULT),
    })
  );
}

test.describe('material-trace 查詢結果 — flat-table layout', () => {
  test.beforeEach(async ({ page }) => {
    await setupMaterialTraceMocks(page);
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
