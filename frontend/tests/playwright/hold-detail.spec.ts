/**
 * E2E tests: hold-detail page (Hold Lot Detail)
 *
 * Scenarios covered:
 *   happy path   — page loads with hold reason title and type badge
 *   summary      — 5 summary cards render with values
 *   age distrib  — 4 age cards render; clicking one filters lots
 *   distribution — workcenter and package distribution tables render
 *   lot table    — HoldLotTable renders rows
 *   pagination   — page-prev / page-next buttons appear
 *   resilience   — missing reason param causes redirect / empty state
 *
 * Network strategy:
 *   All API calls mocked. Standalone page at /hold-detail (no portal-shell).
 *   PORTAL_SPA_ENABLED=false by default — no canonical redirect.
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/hold-detail?reason=VISUAL_DEFECT`;

const MOCK_SUMMARY = {
  success: true,
  data: {
    dataUpdateDate: '2026-06-20',
    totalLots: 30,
    totalQty: 600,
    avgAge: 3.5,
    maxAge: 12,
    workcenterCount: 4,
  },
};

const MOCK_DISTRIBUTION = {
  success: true,
  data: {
    byAge: [
      { range: '0-1', lots: 5, qty: 100, percentage: 16.7 },
      { range: '1-3', lots: 10, qty: 200, percentage: 33.3 },
      { range: '3-7', lots: 10, qty: 200, percentage: 33.3 },
      { range: '7+', lots: 5, qty: 100, percentage: 16.7 },
    ],
    byWorkcenter: [
      { name: 'ETCH-01', lots: 15, qty: 300, percentage: 50 },
      { name: 'ETCH-02', lots: 15, qty: 300, percentage: 50 },
    ],
    byPackage: [
      { name: 'PKG-A', lots: 20, qty: 400, percentage: 66.7 },
      { name: 'PKG-B', lots: 10, qty: 200, percentage: 33.3 },
    ],
  },
};

const MOCK_LOTS = {
  success: true,
  data: {
    lots: [
      { LOTID: 'LOT-H001', WORKORDERID: 'WO-001', WIPSTATUS: 'HOLD', PACKAGE: 'PKG-A' },
      { LOTID: 'LOT-H002', WORKORDERID: 'WO-002', WIPSTATUS: 'HOLD', PACKAGE: 'PKG-B' },
    ],
    pagination: { page: 1, perPage: 20, total: 30, totalPages: 2 },
  },
};

async function setupMocks(page: Page): Promise<void> {
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user' } }),
    }),
  );

  await page.route('**/api/wip/hold-detail/summary**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    }),
  );

  await page.route('**/api/wip/hold-detail/distribution**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DISTRIBUTION),
    }),
  );

  await page.route('**/api/wip/hold-detail/lots**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_LOTS),
    }),
  );
}

async function gotoHoldDetailPage(page: Page): Promise<void> {
  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.waitForSelector('[data-testid="hold-detail-app"]', { timeout: 20_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_with_hold_reason_title', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  const titleText = await page.locator('.hold-detail-title').textContent();
  expect(titleText).toContain('VISUAL_DEFECT');
});

test('test_hold_type_badge_shows_quality', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  const badge = page.locator('.hold-type-badge');
  await expect(badge).toBeVisible({ timeout: 10_000 });
  const badgeText = await badge.textContent();
  // VISUAL_DEFECT is a quality hold (not in NON_QUALITY_HOLD_REASON_SET)
  expect(badgeText).toContain('品質異常');
});

test('test_summary_cards_render_five_values', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  await page.waitForSelector('.summary-card-group', { timeout: 15_000 });
  const cards = page.locator('.summary-card');
  await expect(cards).toHaveCount(5);
  const groupText = await page.locator('.summary-card-group').textContent();
  expect(groupText).toContain('30'); // totalLots
  expect(groupText).toContain('600'); // totalQty
});

test('test_age_distribution_renders_four_cards', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  await page.waitForSelector('.age-distribution', { timeout: 15_000 });
  const ageCards = page.locator('.age-card');
  await expect(ageCards).toHaveCount(4);
});

test('test_age_card_click_activates_filter', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  await page.waitForSelector('.age-distribution', { timeout: 15_000 });

  const firstCard = page.locator('.age-card').first();
  await firstCard.click();
  await page.waitForTimeout(500);
  // After click, the card should have .active class
  await expect(firstCard).toHaveClass(/active/);
});

test('test_distribution_tables_render', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  await page.waitForSelector('.distribution-grid', { timeout: 15_000 });
  const distributionText = await page.locator('.distribution-grid').textContent();
  expect(distributionText).toContain('ETCH-01');
  expect(distributionText).toContain('PKG-A');
});

test('test_lot_table_renders_rows', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  await page.waitForSelector('.lot-table', { timeout: 15_000 });
  const rows = page.locator('.lot-table tbody tr');
  await expect(rows).toHaveCount(2);
});

test('test_pagination_buttons_visible', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  // Mock returns totalPages=2, so pagination should show
  await page.waitForSelector('[data-testid="page-prev"]', { timeout: 15_000 });
  await expect(page.locator('[data-testid="page-next"]')).toBeVisible();
});

test('test_back_button_to_hold_overview', async ({ page }) => {
  await setupMocks(page);
  await gotoHoldDetailPage(page);
  const backBtn = page.locator('.hold-detail-back-btn');
  await expect(backBtn).toBeVisible({ timeout: 10_000 });
});

test('test_api_error_shows_error_banner', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user' } }) }),
  );
  await page.route('**/api/wip/hold-detail/**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: { message: 'Server Error' } }) }),
  );

  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.waitForSelector('[data-testid="hold-detail-app"]', { timeout: 20_000 });
  const banner = page.locator('.error-banner-wrap').first();
  await expect(banner).toBeVisible({ timeout: 15_000 });
});
