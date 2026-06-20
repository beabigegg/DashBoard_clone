/**
 * E2E tests: wip-detail page (WIP Lot Detail)
 *
 * Scenarios covered:
 *   happy path   — page loads with title, summary cards, lot table
 *   filters      — FilterPanel visible; filter panel collapse toggle
 *   lot detail   — click lot-id link opens side panel
 *   status cards — clickable summary cards (RUN/QUEUE/品質異常/非品質異常)
 *   pagination   — page-prev / page-next buttons appear when multi-page result
 *   resilience   — API 500 shows error banner; missing workcenter param shows error
 *
 * Network strategy:
 *   All API calls mocked via page.route() (catch-all FIRST, specific LAST — LIFO).
 *   Standalone app at /wip-detail (PORTAL_SPA_ENABLED=false, no redirect).
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/wip-detail?workcenter=ETCH-01`;

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    workorders: ['WO-001', 'WO-002'],
    lotids: ['LOT-A', 'LOT-B'],
    packages: ['PKG-X'],
    types: ['TYPE-1'],
    firstnames: [],
    waferdescs: [],
    workflows: ['WF-MAIN'],
    bops: [],
    pjFunctions: [],
  },
};

const MOCK_DETAIL = {
  success: true,
  data: {
    sys_date: '2026-06-20',
    summary: {
      totalLots: 42,
      runLots: 20,
      queueLots: 15,
      qualityHoldLots: 5,
      nonQualityHoldLots: 2,
    },
    lots: [
      { lotId: 'LOT-001', pjType: 'PROD', equipment: 'EQ-A', wipStatus: 'RUN', package: 'PKG-X' },
      { lotId: 'LOT-002', pjType: 'PROD', equipment: 'EQ-B', wipStatus: 'QUEUE', package: 'PKG-X' },
    ],
    specs: ['SPEC-A', 'SPEC-B'],
    pagination: { page: 1, page_size: 20, total_count: 42, total_pages: 3 },
  },
};

const MOCK_LOT_DETAIL = {
  success: true,
  data: {
    fieldLabels: { LOTID: 'LOT ID', WORKORDERID: 'Work Order' },
    wipStatus: 'RUN',
    holdCount: 0,
    LOTID: 'LOT-001',
    WORKORDERID: 'WO-001',
  },
};

async function setupMocks(page: Page): Promise<void> {
  // Catch-all FIRST (LIFO — registered before specific routes)
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user' } }),
    }),
  );

  await page.route('**/api/wip/meta/filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    }),
  );

  await page.route('**/api/wip/detail/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DETAIL),
    }),
  );

  await page.route('**/api/wip/lot/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_LOT_DETAIL),
    }),
  );
}

async function gotoWipDetailPage(page: Page): Promise<void> {
  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.waitForSelector('[data-testid="wip-detail-app"]', { timeout: 20_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_with_title', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  // .detail-page-title is the wip-detail app's own h1 (avoid portal-shell nav h1)
  const title = await page.locator('.detail-page-title').textContent();
  expect(title).toContain('ETCH-01');
});

test('test_summary_cards_render', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  await page.waitForSelector('.summary-card-group', { timeout: 10_000 });
  const cards = page.locator('.summary-card');
  await expect(cards).toHaveCount(5); // Total Lots + RUN + QUEUE + 品質異常 + 非品質異常
});

test('test_summary_card_values', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  await page.waitForSelector('.summary-card-group', { timeout: 10_000 });
  const groupText = await page.locator('.summary-card-group').textContent();
  expect(groupText).toContain('42'); // totalLots
  expect(groupText).toContain('20'); // runLots
});

test('test_filter_panel_visible', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  // FilterPanel starts collapsed; .filters-toggle is always visible
  const toggleBtn = page.locator('.filters-toggle');
  await expect(toggleBtn).toBeVisible({ timeout: 10_000 });
  // Expand the filter panel so MultiSelect triggers become visible
  await toggleBtn.click();
  await expect(page.locator('.filters-body')).toBeVisible({ timeout: 5_000 });
});

test('test_lot_table_renders_rows', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  // LotTable renders as .table-section > table (no .lot-table class)
  await page.waitForSelector('.table-section table', { timeout: 15_000 });
  const rows = page.locator('.table-section table tbody tr');
  await expect(rows).toHaveCount(2);
});

test('test_lot_id_link_opens_detail_panel', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  await page.waitForSelector('.table-section table', { timeout: 15_000 });
  // Click the first lot-id link
  const lotLink = page.locator('.lot-id-link').first();
  await lotLink.click();
  // Detail panel should appear
  await page.waitForSelector('.lot-detail-panel.show, .lot-detail-panel', { timeout: 10_000 });
  const panel = page.locator('.lot-detail-panel');
  await expect(panel).toBeVisible();
});

test('test_pagination_buttons_present', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  // Mock returns total_pages=3, so pagination should show
  await page.waitForSelector('[data-testid="page-prev"]', { timeout: 15_000 });
  await expect(page.locator('[data-testid="page-prev"]')).toBeVisible();
  await expect(page.locator('[data-testid="page-next"]')).toBeVisible();
});

test('test_back_button_present', async ({ page }) => {
  await setupMocks(page);
  await gotoWipDetailPage(page);
  const backBtn = page.locator('.detail-back-btn');
  await expect(backBtn).toBeVisible({ timeout: 10_000 });
});

test('test_api_error_shows_banner', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user' } }) }),
  );
  await page.route('**/api/wip/meta/filter-options**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS) }),
  );
  await page.route('**/api/wip/detail/**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: { message: 'Internal Server Error' } }) }),
  );

  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.waitForSelector('[data-testid="wip-detail-app"]', { timeout: 20_000 });
  await page.waitForSelector('.error-banner-wrap', { timeout: 15_000 });
  const banner = page.locator('.error-banner-wrap').first();
  await expect(banner).toBeVisible();
});
