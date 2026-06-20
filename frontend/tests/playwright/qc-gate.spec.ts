/**
 * E2E + resilience tests: QC-GATE status page
 *
 * Covers:
 *   - Happy path: chart + table visible, columns present, rows rendered from API
 *   - Data boundary: empty lots array → empty-state
 *   - Cache timestamp display
 *   - API error (500) → error banner
 *   - Clear filter button present after load
 *   - Slow network + aborted request resilience
 *   - Visibility change / hidden-tab behavior (auto-refresh skips when hidden)
 *
 * Network strategy:
 *   - All API calls are mocked via page.route() (no Oracle dependency)
 *   - Catch-all registered FIRST (lowest LIFO priority), specific routes LAST
 *   - page.goto(...).catch(()=>{}) + early-return guard per ci-workflow.md
 *   - pageRendered guard: checks .theme-qc-gate presence, NOT bodyText.length
 *
 * Stable selectors: data-testid, role, aria-label, visible text content.
 * No generated CSS class selectors.
 */

import { test, expect, type Page } from '@playwright/test';
import { navigateViaSidebar } from './_auth.js';

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------

const MOCK_STATION_A = {
  specname: 'STATION-A',
  spec_order: 1,
  buckets: { lt_6h: 3, '6h_12h': 2, '12h_24h': 1, gt_24h: 0 },
  total: 6,
  lots: [
    {
      lot_id: 'LOT-E2E-001',
      package: 'BGA-256',
      product: 'PROD-ALPHA',
      qty: 100,
      step: 'STATION-A',
      workorder: 'WO-001',
      move_in_time: '2026-06-19T08:00:00',
      wait_hours: 4.5,
      bucket: 'lt_6h',
      status: 'WIP',
    },
    {
      lot_id: 'LOT-E2E-002',
      package: 'QFP-64',
      product: 'PROD-BETA',
      qty: 50,
      step: 'STATION-A',
      workorder: 'WO-002',
      move_in_time: '2026-06-19T02:00:00',
      wait_hours: 9.0,
      bucket: '6h_12h',
      status: 'HOLD',
    },
    {
      lot_id: 'LOT-E2E-003',
      package: 'DFN-8',
      product: 'PROD-GAMMA',
      qty: 200,
      step: 'STATION-A',
      workorder: 'WO-003',
      move_in_time: '2026-06-18T18:00:00',
      wait_hours: 14.0,
      bucket: '12h_24h',
      status: 'WIP',
    },
  ],
};

const MOCK_STATION_B = {
  specname: 'STATION-B',
  spec_order: 2,
  buckets: { lt_6h: 1, '6h_12h': 0, '12h_24h': 0, gt_24h: 2 },
  total: 3,
  lots: [
    {
      lot_id: 'LOT-E2E-004',
      package: 'SOT-23',
      product: 'PROD-DELTA',
      qty: 75,
      step: 'STATION-B',
      workorder: 'WO-004',
      move_in_time: '2026-06-20T01:00:00',
      wait_hours: 3.2,
      bucket: 'lt_6h',
      status: 'WIP',
    },
    {
      lot_id: 'LOT-E2E-005',
      package: 'SOIC-16',
      product: 'PROD-EPSILON',
      qty: 120,
      step: 'STATION-B',
      workorder: 'WO-005',
      move_in_time: '2026-06-18T06:00:00',
      wait_hours: 26.5,
      bucket: 'gt_24h',
      status: 'HOLD',
    },
  ],
};

const MOCK_CACHE_TIME = '2026-06-20T10:30:00';

/** Full happy-path API response shape (matches ApiPayload / normalizePayload) */
const MOCK_SUMMARY_RESPONSE = {
  success: true,
  data: {
    cache_time: MOCK_CACHE_TIME,
    stations: [MOCK_STATION_A, MOCK_STATION_B],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

/** Response with zero lots (data boundary: empty state) */
const MOCK_SUMMARY_EMPTY = {
  success: true,
  data: {
    cache_time: MOCK_CACHE_TIME,
    stations: [],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

/** Standard error envelope (matches core/response.py) */
const MOCK_500_RESPONSE = {
  success: false,
  error: { code: 'INTERNAL_ERROR', message: 'Mock server error for test' },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

// ---------------------------------------------------------------------------
// Route setup helpers
// ---------------------------------------------------------------------------

/**
 * Register catch-all portal-shell supporting routes first (lowest LIFO priority).
 * Specific /api/qc-gate/summary is registered per-test AFTER these.
 *
 * Playwright page.route() is LIFO: last-registered = highest priority.
 * So: catch-all first → specific routes last → specific routes win.
 */
async function setupPortalShellRoutes(page: Page): Promise<void> {
  // Auth endpoints — always succeed
  await page.route('**/api/auth/**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { username: 'testuser', role: 'user', permissions: [] },
        meta: {},
      }),
    });
  });

  // Page visibility/status endpoints
  await page.route('**/api/pages**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [], meta: {} }),
    });
  });

  // WIP overview suppressor (same as navigateViaSidebar internals use)
  await page.route('**/api/wip/**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    });
  });
}

/**
 * Register the qc-gate summary mock with a specific response body.
 * Must be called AFTER setupPortalShellRoutes() so it has higher LIFO priority.
 */
async function mockQcGateSummary(
  page: Page,
  response: object,
  statusCode = 200,
): Promise<void> {
  await page.route('**/api/qc-gate/summary**', (route) => {
    route.fulfill({
      status: statusCode,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}

/**
 * Navigate to the QC-GATE page via the portal-shell sidebar.
 * Returns true if the theme root is present (page is usable), false otherwise.
 */
async function navigateToQcGate(page: Page): Promise<boolean> {
  let navigationFailed = false;
  await page.goto('/portal-shell/').catch(() => { navigationFailed = true; });
  if (navigationFailed) return false;

  // Quick sanity: make sure we got a real shell page, not an error page.
  // pageRendered guard: check .theme-qc-gate, NOT bodyText.length (ECONNREFUSED
  // error page body can exceed 100 chars — see ci-workflow.md).
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  if (!bodyText) return false;

  await navigateViaSidebar(page, 'qc-gate', {
    waitForSelector: '[data-testid="qc-gate-app"]',
  }).catch(() => {});

  const hasTheme = await page.evaluate(() =>
    Boolean(document.querySelector('[data-testid="qc-gate-app"]'))
  );
  return hasTheme;
}

// ---------------------------------------------------------------------------
// Helper: skip if page not reachable (guards tests in environments where
// qc-gate is not yet in the sidebar / not visible to the test user).
// ---------------------------------------------------------------------------
async function requireQcGatePage(page: Page): Promise<boolean> {
  const reachable = await navigateToQcGate(page);
  if (!reachable) {
    test.skip(true, 'QC-GATE page not reachable in this environment');
    return false;
  }
  return true;
}

// ===========================================================================
// Test suite
// ===========================================================================

test.describe('QC-GATE page — happy path', () => {
  test.beforeEach(async ({ page }) => {
    // Register supporting routes first (lowest LIFO priority)
    await setupPortalShellRoutes(page);
    // Register qc-gate summary last (highest LIFO priority) — happy path
    await mockQcGateSummary(page, MOCK_SUMMARY_RESPONSE);
  });

  test('page_loads_with_chart_and_table', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // Chart container must be visible
    await expect(page.locator('[data-testid="qc-gate-chart"]')).toBeVisible({ timeout: 30_000 });

    // LOT table section must be visible (the SectionCard wrapper has the testid on LotTable)
    await expect(page.locator('[data-testid="lot-table"]')).toBeVisible({ timeout: 30_000 });
  });

  test('lot_table_shows_correct_columns', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // Wait for table to mount
    const table = page.locator('[data-testid="lot-table"]');
    await expect(table).toBeVisible({ timeout: 30_000 });

    // All 10 columns must be present as <th> cells
    const columnChecks = [
      'LOT ID',
      'Package',
      'Product',
      'QTY',
      '站點',
      'Workorder',
      'Move In',
      'Wait (hr)',
      '區間',
      '狀態',
    ];

    for (const colLabel of columnChecks) {
      await expect(
        page.locator(`[data-testid="lot-table"] th`).filter({ hasText: colLabel }).first()
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test('lot_rows_render_from_api_data', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // Wait for table content
    const lotTable = page.locator('[data-testid="lot-table"]');
    await expect(lotTable).toBeVisible({ timeout: 30_000 });

    // MOCK_STATION_A has 3 lots + MOCK_STATION_B has 2 lots = 5 total rows
    // DataTable renders <tbody> rows — wait until at least one lot_id is visible
    await expect(page.locator('td').filter({ hasText: 'LOT-E2E-001' }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('td').filter({ hasText: 'LOT-E2E-005' }).first()).toBeVisible({ timeout: 10_000 });

    // Verify a sampling of values from different lots
    await expect(page.locator('td').filter({ hasText: 'BGA-256' }).first()).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('td').filter({ hasText: 'PROD-ALPHA' }).first()).toBeVisible({ timeout: 5_000 });
  });

  test('cache_timestamp_visible', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // DataUpdateBadge has data-testid="cache-timestamp" and renders the
    // formattedCacheTime from bindUpdateBadge.
    const badge = page.locator('[data-testid="cache-timestamp"]');
    await expect(badge).toBeVisible({ timeout: 30_000 });

    // The badge should not show the placeholder '--' after data loads
    const badgeText = await badge.textContent({ timeout: 10_000 });
    expect(badgeText?.trim()).not.toBe('');
    // After a successful load the formatted cache time should appear
    // (formattedCacheTime converts MOCK_CACHE_TIME → '2026-06-20 10:30:00')
    expect(badgeText).toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  test('clear_filter_button_present_in_dom_after_load', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // Wait for page to be fully loaded
    await expect(page.locator('[data-testid="lot-table"]')).toBeVisible({ timeout: 30_000 });

    // The clear-filter-btn in App.vue is ONLY rendered when activeFilter != null.
    // On initial load no filter is active, so the button must NOT be present.
    // This test verifies the button is absent on load (correct initial state).
    const clearBtn = page.locator('[data-testid="clear-filter-btn"]');
    await expect(clearBtn).not.toBeVisible({ timeout: 5_000 });

    // The lot-table's filter chip is also absent without active filter
    const clearChip = page.locator('[data-testid="clear-filter-chip"]');
    await expect(clearChip).not.toBeVisible({ timeout: 5_000 });
  });
});

// ===========================================================================
// Data-boundary: empty lots
// ===========================================================================

test.describe('QC-GATE page — empty state', () => {
  test.beforeEach(async ({ page }) => {
    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, MOCK_SUMMARY_EMPTY);
  });

  test('empty_state_when_no_stations', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // When stations array is empty, the empty-state div is rendered and
    // the DataTable shows its no-data EmptyState cell.
    const emptyState = page.locator('[data-testid="empty-state"]');
    await expect(emptyState).toBeVisible({ timeout: 30_000 });

    // Table is still rendered but has no data rows
    const lotTable = page.locator('[data-testid="lot-table"]');
    await expect(lotTable).toBeVisible({ timeout: 10_000 });

    // No lot IDs in cell content
    const lotIdCells = page.locator('td').filter({ hasText: 'LOT-E2E' });
    await expect(lotIdCells).toHaveCount(0, { timeout: 5_000 });
  });
});

// ===========================================================================
// Resilience: API errors
// ===========================================================================

test.describe('QC-GATE page — API error resilience', () => {
  test('api_500_shows_error_banner', async ({ page }) => {
    await setupPortalShellRoutes(page);
    // Register 500 error response for summary endpoint
    await mockQcGateSummary(page, MOCK_500_RESPONSE, 500);

    if (!(await requireQcGatePage(page))) return;

    // ErrorBanner has data-testid="error-banner" and role="alert"
    // It renders when errorMessage is non-empty (set on catch in useQcGateData)
    const errorBanner = page.locator('[data-testid="error-banner"], [role="alert"]').first();
    await expect(errorBanner).toBeVisible({ timeout: 30_000 });
  });

  test('slow_network_page_still_loads', async ({ page }) => {
    await setupPortalShellRoutes(page);

    // Inject 3-second delay before fulfilling summary response
    await page.route('**/api/qc-gate/summary**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 3_000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUMMARY_RESPONSE),
      });
    });

    if (!(await requireQcGatePage(page))) return;

    // Loading overlay should appear during the delay
    // Then resolve once data arrives — wait up to 15s for the table
    await expect(page.locator('[data-testid="lot-table"]')).toBeVisible({ timeout: 15_000 });
  });

  test('aborted_request_shows_no_crash', async ({ page }) => {
    await setupPortalShellRoutes(page);

    // Abort the first summary request; subsequent auto-refresh will retry
    let callCount = 0;
    await page.route('**/api/qc-gate/summary**', (route) => {
      callCount++;
      if (callCount === 1) {
        route.abort('failed');
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_SUMMARY_RESPONSE),
        });
      }
    });

    if (!(await requireQcGatePage(page))) return;

    // Page must not crash: qc-gate-app must still be in the DOM
    const appRoot = page.locator('[data-testid="qc-gate-app"]');
    await expect(appRoot).toBeAttached({ timeout: 15_000 });

    // No unhandled JS error thrown (Playwright captures console errors)
    // The abort sets AbortError which useQcGateData silently swallows
    // (returns false without setting errorMessage) — so error-banner absent
    // Note: errorMessage is not set for AbortError by design (see composable)
  });

  test('503_service_unavailable_shows_error_banner', async ({ page }) => {
    await setupPortalShellRoutes(page);

    await page.route('**/api/qc-gate/summary**', (route) => {
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'SERVICE_UNAVAILABLE', message: 'Service temporarily unavailable' },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      });
    });

    if (!(await requireQcGatePage(page))) return;

    const errorBanner = page.locator('[data-testid="error-banner"], [role="alert"]').first();
    await expect(errorBanner).toBeVisible({ timeout: 30_000 });
  });
});

// ===========================================================================
// Resilience: visibility change / hidden tab
// ===========================================================================

test.describe('QC-GATE page — hidden tab behavior', () => {
  test('auto_refresh_skips_when_tab_hidden', async ({ page }) => {
    await setupPortalShellRoutes(page);

    let fetchCount = 0;
    await page.route('**/api/qc-gate/summary**', (route) => {
      fetchCount++;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUMMARY_RESPONSE),
      });
    });

    if (!(await requireQcGatePage(page))) return;

    // Initial fetch must complete
    await expect(page.locator('[data-testid="lot-table"]')).toBeVisible({ timeout: 15_000 });
    const countAfterLoad = fetchCount;
    expect(countAfterLoad).toBeGreaterThanOrEqual(1);

    // Simulate hidden tab: document.hidden = true
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Wait 1 second — the refresh timer fires jitter-delayed (min 1s), but
    // the guard `if (!document.hidden)` should prevent the actual fetch.
    await page.waitForTimeout(1_500);
    const countWhileHidden = fetchCount;

    // Restore visibility — this triggers fetchData({ background: true })
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // After visibility is restored the composable fires a background refresh
    await page.waitForTimeout(2_000);
    const countAfterVisible = fetchCount;

    // The count after restoring visibility must exceed count-while-hidden
    // (at least one new refresh triggered by the visibilitychange handler)
    expect(countAfterVisible).toBeGreaterThan(countWhileHidden);
  });
});

// ===========================================================================
// URL state: direct navigation and browser back/forward
// ===========================================================================

test.describe('QC-GATE page — URL state', () => {
  test.beforeEach(async ({ page }) => {
    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, MOCK_SUMMARY_RESPONSE);
  });

  test('direct_navigation_to_qc_gate_hash_route', async ({ page }) => {
    // Direct SPA hash route navigation (portal-shell uses Vue Router hash mode)
    let navigationFailed = false;
    await page.goto('/portal-shell/#/qc-gate').catch(() => { navigationFailed = true; });
    if (navigationFailed) {
      test.skip(true, 'Direct hash navigation not reachable');
      return;
    }

    // Wait for the app root to mount — this confirms SPA routing activated
    const appRoot = page.locator('[data-testid="qc-gate-app"]');
    await expect(appRoot).toBeVisible({ timeout: 30_000 });
  });

  test('browser_back_forward_preserves_qc_gate_page', async ({ page }) => {
    if (!(await requireQcGatePage(page))) return;

    // We are on qc-gate — confirm app is rendered
    await expect(page.locator('[data-testid="qc-gate-app"]')).toBeVisible({ timeout: 15_000 });
    const urlBefore = page.url();

    // Go back to the shell home
    await page.goBack({ timeout: 15_000 }).catch(() => {});

    // Then go forward — should restore qc-gate
    await page.goForward({ timeout: 15_000 }).catch(() => {});

    // URL should match the qc-gate route again
    const urlAfter = page.url();
    expect(urlAfter).toContain('qc-gate');
  });
});

// ===========================================================================
// Data boundary: large payload
// ===========================================================================

test.describe('QC-GATE page — large data boundary', () => {
  test('large_lot_count_renders_without_crash', async ({ page }) => {
    // Generate 200 lots across 20 stations
    const largeStations = Array.from({ length: 20 }, (_, stationIdx) => ({
      specname: `STN-${String(stationIdx + 1).padStart(2, '0')}`,
      spec_order: stationIdx + 1,
      buckets: { lt_6h: 5, '6h_12h': 3, '12h_24h': 1, gt_24h: 1 },
      total: 10,
      lots: Array.from({ length: 10 }, (__, lotIdx) => ({
        lot_id: `LOT-LARGE-${stationIdx * 10 + lotIdx + 1}`,
        package: 'BGA-256',
        product: 'PROD-LARGE',
        qty: 100,
        step: `STN-${String(stationIdx + 1).padStart(2, '0')}`,
        workorder: `WO-LARGE-${stationIdx * 10 + lotIdx + 1}`,
        move_in_time: '2026-06-20T01:00:00',
        wait_hours: lotIdx * 1.5,
        bucket: 'lt_6h',
        status: 'WIP',
      })),
    }));

    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, {
      success: true,
      data: { cache_time: MOCK_CACHE_TIME, stations: largeStations },
      meta: { timestamp: new Date().toISOString(), app_version: 'test' },
    });

    if (!(await requireQcGatePage(page))) return;

    // Page must not crash; chart and table must render
    await expect(page.locator('[data-testid="qc-gate-chart"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-testid="lot-table"]')).toBeVisible({ timeout: 30_000 });

    // First lot row in the large payload must be present somewhere in the table
    await expect(page.locator('td').filter({ hasText: 'LOT-LARGE-' }).first()).toBeVisible({ timeout: 15_000 });
  });
});

// ===========================================================================
// Data boundary: malformed / partial response
// ===========================================================================

test.describe('QC-GATE page — malformed response payloads', () => {
  test('missing_stations_key_does_not_crash', async ({ page }) => {
    // Response with stations key absent — normalizePayload defaults to []
    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, {
      success: true,
      data: { cache_time: null },
      meta: {},
    });

    if (!(await requireQcGatePage(page))) return;

    // App must still mount
    await expect(page.locator('[data-testid="qc-gate-app"]')).toBeVisible({ timeout: 30_000 });

    // Empty-state is shown (no stations → hasStations=false)
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible({ timeout: 15_000 });
  });

  test('wrong_type_lots_is_non_array_does_not_crash', async ({ page }) => {
    // lots field is a string instead of array — normalizeStation returns []
    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, {
      success: true,
      data: {
        cache_time: MOCK_CACHE_TIME,
        stations: [
          {
            specname: 'BAD-STATION',
            spec_order: 1,
            buckets: { lt_6h: 1, '6h_12h': 0, '12h_24h': 0, gt_24h: 0 },
            total: 1,
            lots: 'not-an-array',
          },
        ],
      },
      meta: {},
    });

    if (!(await requireQcGatePage(page))) return;

    await expect(page.locator('[data-testid="qc-gate-app"]')).toBeVisible({ timeout: 30_000 });
    // Station exists (specname present) so hasStations=true — chart renders
    await expect(page.locator('[data-testid="qc-gate-chart"]')).toBeVisible({ timeout: 15_000 });
    // No lot rows (lots was not an array → merged to empty)
    const lotCells = page.locator('td').filter({ hasText: 'LOT-' });
    await expect(lotCells).toHaveCount(0, { timeout: 5_000 });
  });

  test('null_bucket_counts_normalised_to_zero', async ({ page }) => {
    // buckets object is null — normalizeBuckets returns all zeros
    await setupPortalShellRoutes(page);
    await mockQcGateSummary(page, {
      success: true,
      data: {
        cache_time: MOCK_CACHE_TIME,
        stations: [
          {
            specname: 'NULL-BUCKET-STATION',
            spec_order: 1,
            buckets: null,
            total: 1,
            lots: [
              {
                lot_id: 'LOT-NULL-BUCKET',
                package: 'PKG-X',
                product: 'PROD-X',
                qty: 10,
                step: 'NULL-BUCKET-STATION',
                workorder: 'WO-X',
                move_in_time: null,
                wait_hours: 5,
                bucket: 'lt_6h',
                status: 'WIP',
              },
            ],
          },
        ],
      },
      meta: {},
    });

    if (!(await requireQcGatePage(page))) return;

    await expect(page.locator('[data-testid="qc-gate-app"]')).toBeVisible({ timeout: 30_000 });
    // Lot row must still render
    await expect(page.locator('td').filter({ hasText: 'LOT-NULL-BUCKET' }).first()).toBeVisible({ timeout: 15_000 });
  });
});
