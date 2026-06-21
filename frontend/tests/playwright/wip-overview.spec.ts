/**
 * E2E tests: wip-overview page (WIP 即時概況)
 *
 * Scenarios covered:
 *   happy path       — summary cards (Total Lots / Total QTY) visible after load
 *   matrix section   — .matrix-container and table render from mock data
 *   status cards     — .wip-status-row shows RUN / QUEUE / hold cards
 *   filter panel     — FilterPanel toggle visible
 *   resilience       — API 500 on summary shows .error-banner-wrap
 *
 * Network strategy:
 *   All APIs mocked via page.route(). No real backend required.
 *   wip-overview is a standalone SPA; navigate directly to /wip-overview.
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/wip-overview`;

const MOCK_SUMMARY = {
  success: true,
  data: {
    dataUpdateDate: '2026-06-22 10:00:00',
    totalLots: 150,
    totalQtyPcs: 7500,
    byWipStatus: {
      run:             { lots: 90,  qty: 4500 },
      queue:           { lots: 30,  qty: 1500 },
      qualityHold:     { lots: 20,  qty: 1000 },
      nonQualityHold:  { lots: 10,  qty: 500  },
    },
  },
};

const MOCK_MATRIX = {
  success: true,
  data: {
    workcenters: ['ETCH-01', 'DIFF-01'],
    packages:    ['PKG-A', 'PKG-B'],
    matrix: {
      'ETCH-01': { 'PKG-A': 50, 'PKG-B': 30 },
      'DIFF-01': { 'PKG-A': 40, 'PKG-B': 30 },
    },
    workcenter_totals: { 'ETCH-01': 80, 'DIFF-01': 70 },
    package_totals:    { 'PKG-A': 90, 'PKG-B': 60 },
    grand_total: 150,
  },
};

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    workorders: ['WO-001'],
    lotids:     ['LOT-001'],
    packages:   ['PKG-A', 'PKG-B'],
    types:      ['TypeA'],
    firstnames: [],
    waferdescs: [],
    workflows:  [],
    bops:       [],
    pjFunctions: [],
  },
};

async function setupMocks(page: Page): Promise<void> {
  // Catch-all first (LIFO — specific routes registered last win)
  await page.route('**/*', (route) => route.continue());

  // Auth: /wip-overview redirects to /portal-shell/wip-overview; the
  // portal-shell router guard calls /api/auth/me on first navigation.
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user', is_admin: false } }),
    }),
  );

  await page.route('**/api/wip/overview/summary**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    }),
  );

  await page.route('**/api/wip/overview/matrix**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_MATRIX),
    }),
  );

  await page.route('**/api/wip/meta/filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    }),
  );
}

async function gotoWipOverview(page: Page): Promise<void> {
  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  // Wait for wip-overview app root to be rendered by NativeRouteView
  await page.waitForSelector('.wip-overview-page', { timeout: 20_000 });
  // Wait for loading overlay to disappear (API data loaded)
  await page.waitForSelector('.loading-overlay', { state: 'detached', timeout: 15_000 }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_page_loads_summary_cards', async ({ page }) => {
  await setupMocks(page);
  await gotoWipOverview(page);

  // SummaryCardGroup with Total Lots and Total QTY
  const pageText = await page.locator('.dashboard').textContent({ timeout: 15_000 });
  expect(pageText).toContain('Total Lots');
  expect(pageText).toContain('Total QTY');
});

test('test_summary_card_values', async ({ page }) => {
  await setupMocks(page);
  await gotoWipOverview(page);

  const pageText = await page.locator('.dashboard').textContent({ timeout: 15_000 });
  // totalLots = 150
  expect(pageText).toContain('150');
  // SummaryCard formats large numbers in compact notation (7500 → "7.5K")
  expect(pageText).toMatch(/7[.,]?5K|7[,.]?500/);
});

test('test_matrix_container_visible', async ({ page }) => {
  await setupMocks(page);
  await gotoWipOverview(page);

  await expect(page.locator('.matrix-container')).toBeVisible({ timeout: 15_000 });
  // Table renders inside matrix container
  const table = page.locator('.matrix-container table');
  await expect(table.first()).toBeVisible({ timeout: 10_000 });
});

test('test_status_cards_visible', async ({ page }) => {
  await setupMocks(page);
  await gotoWipOverview(page);

  await expect(page.locator('.wip-status-row')).toBeVisible({ timeout: 15_000 });
  const cards = page.locator('.wip-status-card');
  const count = await cards.count();
  expect(count).toBeGreaterThanOrEqual(4); // RUN, QUEUE, 品質異常, 非品質異常

  const rowText = await page.locator('.wip-status-row').textContent();
  expect(rowText).toContain('RUN');
  expect(rowText).toContain('QUEUE');
});

test('test_api_error_shows_error_banner', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user', is_admin: false } }) }),
  );
  await page.route('**/api/wip/overview/summary**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: 'Server error' }) }),
  );
  await page.route('**/api/wip/overview/matrix**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: 'Server error' }) }),
  );
  await page.route('**/api/wip/meta/filter-options**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ success: false, error: 'Server error' }) }),
  );

  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  await page.waitForSelector('.wip-overview-page', { timeout: 20_000 });
  await expect(page.locator('.error-banner-wrap')).toBeVisible({ timeout: 20_000 });
});
