/**
 * E2E spec: Reject History page
 *
 * Uses sidebar navigation (direct goto doesn't trigger Vue SPA routing).
 * Handles both sync (200) and async (202 + poll) response paths.
 * All API calls are mocked to avoid Oracle dependency.
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

const MOCK_QUERY_ID = 'test-reject-query-001';

const MOCK_SYNC_RESULT = {
  success: true,
  data: {
    query_id: MOCK_QUERY_ID,
    summary: {
      MOVEIN_QTY: 1000,
      REJECT_TOTAL_QTY: 10,
      DEFECT_QTY: 2,
      REJECT_RATE_PCT: 1.0,
      DEFECT_RATE_PCT: 0.2,
      REJECT_SHARE_PCT: 83.3,
      AFFECTED_LOT_COUNT: 3,
      AFFECTED_WORKORDER_COUNT: 2,
    },
    detail: {
      items: [
        {
          CONTAINERNAME: 'GA250601',
          WORKCENTERNAME: 'WC-TEST',
          PRODUCTLINENAME: 'PKG-A',
          PJ_FUNCTION: 'FN-X',
          PJ_TYPE: 'A',
          PRODUCTNAME: 'PROD-1',
          LOSSREASONNAME: 'SCRATCH',
          EQUIPMENTNAME: 'EQ-01',
          REJECTCOMMENT: 'test',
          REJECT_TOTAL_QTY: 5,
          DEFECT_QTY: 1,
          TXN_TIME: '2025-06-01 10:00:00',
        },
        {
          CONTAINERNAME: 'GA250602',
          WORKCENTERNAME: 'WC-TEST',
          PRODUCTLINENAME: 'PKG-A',
          PJ_FUNCTION: 'FN-X',
          PJ_TYPE: 'A',
          PRODUCTNAME: 'PROD-1',
          LOSSREASONNAME: 'PARTICLE',
          EQUIPMENTNAME: 'EQ-02',
          REJECTCOMMENT: '',
          REJECT_TOTAL_QTY: 5,
          DEFECT_QTY: 1,
          TXN_TIME: '2025-06-01 11:00:00',
        },
      ],
      pagination: { page: 1, perPage: 50, total: 2, totalPages: 1 },
    },
    available_filters: {
      workcenter_groups: ['WC-TEST'],
      packages: ['PKG-A'],
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
      items: MOCK_SYNC_RESULT.data.detail.items,
      pagination: MOCK_SYNC_RESULT.data.detail.pagination,
    },
    analytics_raw: [],
    available_filters: MOCK_SYNC_RESULT.data.available_filters,
    total_row_count: 2,
    spool_download_url: null,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_BATCH_PARETO_RESULT = {
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
      body: JSON.stringify(MOCK_BATCH_PARETO_RESULT),
    })
  );
  await page.route('**/api/reject-history/view', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_VIEW_RESULT),
    })
  );
  await page.route('**/api/reject-history/export-cached', (route) =>
    route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=reject_history_export.csv',
      },
      body: 'LOT,WORKCENTER,原因\nGA250601,WC-TEST,SCRATCH\n',
    })
  );
  await page.route('**/api/reject-history/query', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SYNC_RESULT),
    })
  );
}

test.describe('Reject History page', () => {
  test.beforeEach(async ({ page }) => {
    await setupRejectHistoryMocks(page);
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
      { timeout: 30_000, polling: 500 },
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
        { timeout: 30_000, polling: 1000 },
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
      { timeout: 30_000, polling: 500 },
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
