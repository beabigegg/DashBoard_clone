/**
 * E2E spec: WIP-Overview matrix drilldown — dual-mode (CI mock + real backend)
 *
 * Covers:
 *   happy-path
 *     AC-1  cell click → wip-detail URL with workcenter + package
 *     AC-2  row-name click → wip-detail URL with workcenter only (no package)
 *     AC-3  cell click sets .active class on the clicked cell (mock-only: timing-safe)
 *     AC-4  wip-detail page mounts after drilldown (improved: structural assertion)
 *     T-R   matrix renders cells and column headers from API data
 *     T-G   grand-total cell present in .total-row
 *     T-S   status cards (RUN / QUEUE) are visible with correct labels
 *   failure injection
 *     T-E   empty matrix response → placeholder visible, no crash
 *
 * Selector notes (grounded in MatrixTable.vue source):
 *   - Data cells:  table.matrix-table tbody td.clickable  (no data-* attributes)
 *   - Row names:   table.matrix-table tbody td.clickable.row-name
 *   - Col headers: table.matrix-table thead th  (text = package name)
 *   - Total row:   table.matrix-table tbody tr.total-row  td.total-col
 *   - Empty:       div.placeholder  (inside MatrixTable when workcenters.length===0)
 *   - Status cards: .wip-status-card   labels: "RUN", "QUEUE"
 *   - wip-detail:  [data-testid="wip-detail-app"]  / .theme-wip-detail
 *
 * LIFO route rule: catch-all registered FIRST inside setupMockedShell;
 * specific WIP mocks in extraMocks() are registered AFTER and therefore WIN.
 */

import { test, expect } from '@playwright/test';
import { USE_MOCKS, navigateDual, navigateMocked, BASE_URL } from './_api-mode.js';
import { loginViaApi } from './_auth.js';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_SUMMARY = {
  success: true,
  data: {
    dataUpdateDate: '2026-06-01 10:00:00',
    totalLots: 150,
    totalQtyPcs: 7500,
    byWipStatus: {
      run:            { lots: 90,  qtyPcs: 4500 },
      queue:          { lots: 30,  qtyPcs: 1500 },
      qualityHold:    { lots: 20,  qtyPcs: 1000 },
      nonQualityHold: { lots: 10,  qtyPcs:  500 },
    },
  },
};

const MOCK_MATRIX = {
  success: true,
  data: {
    workcenters: ['ETCH-01', 'DIFF-01'],
    packages:    ['PKG-A',   'PKG-B'],
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
    workorders: [],
    lotids:     [],
    packages:   ['PKG-A', 'PKG-B'],
    types:      ['TypeA'],
  },
};

const MOCK_EMPTY_MATRIX = {
  success: true,
  data: {
    workcenters: [],
    packages:    [],
    matrix:      {},
    workcenter_totals: {},
    package_totals:    {},
    grand_total: 0,
  },
};

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

/**
 * Register the three WIP API mocks.
 * Must be called as `extraMocks` inside navigateDual / navigateMocked so that
 * these registrations happen AFTER setupMockedShell's stub for "**\/api\/wip\/**",
 * ensuring the LIFO ordering makes these specific routes win.
 */
async function registerWipMocks(page, matrixPayload = MOCK_MATRIX) {
  await page.route('**/api/wip/meta/filter-options**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    }),
  );
  await page.route('**/api/wip/overview/summary**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    }),
  );
  await page.route('**/api/wip/overview/matrix**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(matrixPayload),
    }),
  );
}

/**
 * Navigate to wip-overview:
 *   - Mock mode: full mocking with rich WIP API data
 *   - Real mode: real login + real backend
 */
async function gotoWipOverview(page, matrixPayload = MOCK_MATRIX) {
  if (USE_MOCKS) {
    await navigateMocked(page, 'wip-overview', {
      waitForSelector: '.matrix-container',
      extraMocks: () => registerWipMocks(page, matrixPayload),
    });
    return;
  }

  // Real mode: wip-overview IS the page under test, so it must receive REAL WIP
  // data.  navigateViaSidebar() suppresses **/api/wip/** with an empty stub to
  // clear the loading overlay when navigating AWAY from wip-overview — but that
  // same stub would starve the matrix here.  Navigate manually without it.
  await loginViaApi(page);
  await page.goto(`${BASE_URL}/portal-shell/`).catch(() => {});

  const toggle = page.locator('button.sidebar-toggle');
  await toggle.waitFor({ timeout: 10_000 }).catch(() => {});
  if ((await toggle.getAttribute('aria-expanded').catch(() => null)) !== 'true') {
    await toggle.click().catch(() => {});
  }
  await page.waitForSelector('a[href*="wip-overview"]', { timeout: 10_000 });
  await page.click('a[href*="wip-overview"]');
  if ((await toggle.getAttribute('aria-expanded').catch(() => null)) === 'true') {
    await toggle.click().catch(() => {});
  }
  await page
    .locator('.sidebar-overlay')
    .waitFor({ state: 'detached', timeout: 3_000 })
    .catch(() => {});

  // Real Oracle WIP query is slower than the mock; wait generously for the
  // matrix container and its first data cell to populate.
  await page.waitForSelector('.matrix-container', { timeout: 30_000 }).catch(() => {});
  await page
    .locator('table.matrix-table tbody td.clickable')
    .first()
    .waitFor({ state: 'visible', timeout: 30_000 })
    .catch(() => {});
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('WIP-Overview matrix drilldown', () => {
  // -------------------------------------------------------------------------
  // T-R: matrix renders
  // -------------------------------------------------------------------------
  test('matrix renders cells and column headers (T-R)', async ({ page }) => {
    await gotoWipOverview(page);

    if (USE_MOCKS) {
      // In mock mode the data is deterministic — assert exact workcenter labels
      await expect(page.locator('table.matrix-table tbody td.row-name').first())
        .toHaveText('ETCH-01', { timeout: 10_000 });

      await expect(page.locator('table.matrix-table thead th').filter({ hasText: 'PKG-A' }))
        .toBeVisible({ timeout: 10_000 });
    } else {
      // Real mode: structural check — at least one data cell exists
      await expect(page.locator('table.matrix-table tbody td.clickable').first())
        .toBeVisible({ timeout: 15_000 });
    }
  });

  // -------------------------------------------------------------------------
  // AC-1: cell click → wip-detail URL with workcenter + package
  // -------------------------------------------------------------------------
  test('cell click navigates to wip-detail with workcenter and package (AC-1)', async ({ page }) => {
    await gotoWipOverview(page);

    let workcenterExpected = null;
    let packageExpected = null;

    if (USE_MOCKS) {
      // In mock mode: first data row = ETCH-01; columns are [row-name, PKG-A, PKG-B, Total].
      // td.clickable.row-name is index 0; td.clickable cells (non-row-name) start at index 1
      // within that row.  Use nth(0) on non-row-name clickable cells of first data row.
      const firstDataRow = page.locator('table.matrix-table tbody tr').first();
      const firstCell = firstDataRow.locator('td.clickable:not(.row-name)').first();

      await expect(firstCell).toBeVisible({ timeout: 10_000 });

      // Derive expected values from the column header position
      const colHeaders = page.locator('table.matrix-table thead th');
      // Header layout: [Workcenter, PKG-A, PKG-B, Total] → index 1 = PKG-A
      packageExpected  = await colHeaders.nth(1).innerText();
      workcenterExpected = await firstDataRow.locator('td.row-name').innerText();

      await firstCell.click({ timeout: 10_000 });
    } else {
      // Real mode: click first available non-row-name clickable cell
      const firstDataRow = page.locator('table.matrix-table tbody tr').first();
      const firstCell    = firstDataRow.locator('td.clickable:not(.row-name)').first();

      if (await firstCell.count() === 0) {
        test.skip(true, 'No matrix data cells available in real mode');
        return;
      }
      await firstCell.click({ timeout: 10_000 });
    }

    await page.waitForURL((url) => url.pathname.includes('wip-detail'), { timeout: 15_000 });

    const url = new URL(page.url());
    expect(url.searchParams.has('workcenter')).toBe(true);
    expect(url.searchParams.has('package')).toBe(true);

    if (USE_MOCKS) {
      expect(url.searchParams.get('workcenter')).toBe(workcenterExpected.trim());
      expect(url.searchParams.get('package')).toBe(packageExpected.trim());
    }
  });

  // -------------------------------------------------------------------------
  // AC-2: row-name click → wip-detail URL with workcenter, no package
  // -------------------------------------------------------------------------
  test('row-name click navigates to wip-detail with workcenter only (AC-2)', async ({ page }) => {
    await gotoWipOverview(page);

    const rowName = page.locator('table.matrix-table tbody td.clickable.row-name').first();

    if (!USE_MOCKS && await rowName.count() === 0) {
      test.skip(true, 'No row-name cells available in real mode');
      return;
    }

    let workcenterExpected = null;
    if (USE_MOCKS) {
      workcenterExpected = await rowName.innerText();
    }

    await expect(rowName).toBeVisible({ timeout: 10_000 });
    await rowName.click({ timeout: 10_000 });

    await page.waitForURL((url) => url.pathname.includes('wip-detail'), { timeout: 15_000 });

    const url = new URL(page.url());
    expect(url.searchParams.has('workcenter')).toBe(true);
    // Row-name click must NOT set a package filter
    expect(url.searchParams.get('package')).toBeNull();

    if (USE_MOCKS) {
      expect(url.searchParams.get('workcenter')).toBe(workcenterExpected.trim());
    }
  });

  // -------------------------------------------------------------------------
  // AC-3: cell click sets .active class (mock-only — timing-sensitive)
  // -------------------------------------------------------------------------
  test('cell click sets .active class on the clicked cell (AC-3)', async ({ page }) => {
    // `.active` is applied via Vue reactive binding (parent's `activeFilter` prop →
    // re-render), NOT synchronously in the click handler.  Capture it with a
    // MutationObserver that persists even after the element leaves the DOM.
    if (!USE_MOCKS) {
      test.skip(true, 'Active-class timing assertion requires mock mode');
      return;
    }

    await navigateMocked(page, 'wip-overview', {
      waitForSelector: '.matrix-container',
      extraMocks: () => registerWipMocks(page),
    });

    const firstCell = page.locator('table.matrix-table tbody tr td.clickable:not(.row-name)').first();
    await expect(firstCell).toBeVisible({ timeout: 10_000 });

    // Install MutationObserver BEFORE clicking so it is ready when Vue flushes
    // its reactive DOM update (which happens asynchronously after the click).
    await page.evaluate(() => {
      window.__ac3ActiveSeen = false;
      const cell = document.querySelector(
        'table.matrix-table tbody tr td.clickable:not(.row-name)',
      );
      if (!cell) return;
      new MutationObserver(() => {
        if (cell.classList.contains('active')) {
          window.__ac3ActiveSeen = true;
        }
      }).observe(cell, { attributes: true, attributeFilter: ['class'] });
    });

    // Playwright click fires real browser input events → triggers Vue's handler →
    // emits 'drilldown' → parent sets activeFilter → Vue flushes DOM in microtask.
    await firstCell.click();

    // Give Vue time to flush reactive updates (at least one render cycle).
    await page.waitForTimeout(150);

    // The flag persists even after the element has been removed from the DOM by
    // the subsequent router navigation.
    const hadActiveClass = await page.evaluate(() => Boolean(window.__ac3ActiveSeen));
    expect(hadActiveClass, 'Cell must have .active class set by Vue reactive binding on click').toBe(true);
  });

  // -------------------------------------------------------------------------
  // AC-4: wip-detail page mounts after drilldown (structural)
  // -------------------------------------------------------------------------
  test('wip-detail page mounts after cell drilldown (AC-4)', async ({ page }) => {
    await gotoWipOverview(page);

    const firstDataRow = page.locator('table.matrix-table tbody tr').first();
    const firstCell    = firstDataRow.locator('td.clickable:not(.row-name)').first();

    if (!USE_MOCKS && await firstCell.count() === 0) {
      test.skip(true, 'No matrix data cells available in real mode');
      return;
    }

    await expect(firstCell).toBeVisible({ timeout: 10_000 });
    await firstCell.click({ timeout: 10_000 });

    await page.waitForURL((url) => url.pathname.includes('wip-detail'), { timeout: 15_000 });

    // Assert that the wip-detail SPA root mounted (data-testid set in App.vue)
    await expect(page.locator('[data-testid="wip-detail-app"]'))
      .toBeVisible({ timeout: 20_000 });
  });

  // -------------------------------------------------------------------------
  // T-G: grand-total cell in total row
  // -------------------------------------------------------------------------
  test('grand-total cell is present in the total row (T-G)', async ({ page }) => {
    await gotoWipOverview(page);

    const totalRow  = page.locator('table.matrix-table tbody tr.total-row');
    const totalCell = totalRow.locator('td.total-col');

    await expect(totalRow).toBeVisible({ timeout: 10_000 });
    await expect(totalCell).toBeVisible({ timeout: 10_000 });

    if (USE_MOCKS) {
      // grand_total = 150; toLocaleString('zh-TW') renders as "150"
      await expect(totalCell).toHaveText('150', { timeout: 5_000 });
    } else {
      // Real mode: structural — cell must be non-empty
      const text = (await totalCell.innerText()).trim();
      expect(text.length).toBeGreaterThan(0);
    }
  });

  // -------------------------------------------------------------------------
  // T-S: status cards visible with RUN / QUEUE labels
  // -------------------------------------------------------------------------
  test('status cards are visible with RUN and QUEUE labels (T-S)', async ({ page }) => {
    await gotoWipOverview(page);

    const cards = page.locator('.wip-status-card');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });

    // At least the RUN and QUEUE cards must be present
    await expect(page.locator('.wip-status-card.run')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.wip-status-card.queue')).toBeVisible({ timeout: 10_000 });

    // Verify label text rendered inside the card header
    await expect(
      page.locator('.wip-status-card.run').locator('.status-header'),
    ).toContainText('RUN', { timeout: 5_000 });

    await expect(
      page.locator('.wip-status-card.queue').locator('.status-header'),
    ).toContainText('QUEUE', { timeout: 5_000 });
  });

  // -------------------------------------------------------------------------
  // T-E: empty matrix → placeholder visible, no crash (failure injection)
  // -------------------------------------------------------------------------
  test('empty matrix response shows placeholder without crash (T-E)', async ({ page }) => {
    // Always use full mocking for failure-injection scenarios
    await navigateMocked(page, 'wip-overview', {
      waitForSelector: '.matrix-container',
      extraMocks: () => registerWipMocks(page, MOCK_EMPTY_MATRIX),
    });

    // MatrixTable renders <div class="placeholder">No data available</div>
    // when workcenters.length === 0
    await expect(page.locator('.placeholder').filter({ hasText: 'No data available' }))
      .toBeVisible({ timeout: 10_000 });

    // Verify the page did not crash (matrix-container still present)
    await expect(page.locator('.matrix-container')).toBeVisible({ timeout: 5_000 });

    // No table rows should exist (no data cells to click)
    expect(await page.locator('table.matrix-table tbody td.clickable').count()).toBe(0);
  });
});
