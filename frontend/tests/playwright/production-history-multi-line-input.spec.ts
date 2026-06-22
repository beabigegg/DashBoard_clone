/**
 * E2E spec: Production History — multi-line textarea parser idempotence (AC-5)
 *
 * Dual-mode spec:
 *   CI (USE_MOCKS=true):   all APIs mocked via extraMocks; request-body
 *                          assertions run in full.
 *   Local (USE_MOCKS=false): real backend; structural assertions only (button
 *                            re-enables or result visible).
 *
 * Verifies that:
 *   - Paste with mixed separators (CRLF + comma + tab) yields the correct
 *     deduplicated token list in the outgoing query body (mock mode)
 *   - An identifier-mode query with all wildcard textareas empty is blocked
 *     client-side (no request sent) with a validation message
 *   - Filling only one textarea (with the others empty) is sufficient to submit
 *   - A wildcard `*` token reaches the request body unchanged
 *   - The mfg-orders textarea deduplicates its own messy input
 *   - The wafer-lots textarea contributes correctly to the query body
 *
 * Note (prod-history-query-mode-tabs): the wildcard textareas live in
 * Tab B 「依識別碼查詢」 after the two-tab redesign.  Switching to that tab is
 * the only precondition for all identifier-mode tests.
 *
 * The parser idempotence proof at the data layer
 * (parse(parse(x)) == parse(x)) is covered by
 * frontend/tests/validation/useProductionHistory.validation.test.js;
 * this spec asserts user-visible end-to-end behaviour.
 */

import { test, expect, type Page, type Request } from '@playwright/test';
import { USE_MOCKS, navigateDual } from './_api-mode.js';

// ---------------------------------------------------------------------------
// Fixture payload — used by installMocks() when in mock mode
// ---------------------------------------------------------------------------

const FILTER_OPTIONS_PAYLOAD = {
  success: true,
  data: {
    pj_types: ['A'],
    packages: ['PKG-1'],
    bops: ['BOP-A'],
    pj_functions: ['FN-X'],
  },
  meta: {
    updated_at: '2026-05-14T00:00:00Z',
    schema_version: 2,
    timestamp: new Date().toISOString(),
    app_version: 'test',
  },
};

// ---------------------------------------------------------------------------
// Mock installer (only called in mock mode via extraMocks)
// ---------------------------------------------------------------------------

/**
 * Register all feature-level route mocks.
 *
 * Returns `queryRequests` — an array that is populated in-place as query
 * requests arrive during the test.  In real mode this function is never called
 * and the array stays empty; real-mode tests use structural assertions instead.
 */
function buildFeatureMocks(
  page: Page,
): { queryRequests: Request[]; installMocks: () => Promise<void> } {
  const queryRequests: Request[] = [];

  const installMocks = async () => {
    await page.route('**/api/production-history/filter-options**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FILTER_OPTIONS_PAYLOAD),
      }),
    );

    await page.route('**/api/production-history/type-options**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { items: [{ value: 'A', label: 'A' }] },
          meta: {},
        }),
      }),
    );

    await page.route('**/api/production-history/query', async (route) => {
      queryRequests.push(route.request());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            dataset_id: 'mock-ds',
            rows: [],
            pagination: { total: 0, page: 1, page_size: 50 },
            matrix: { tree: [], month_columns: [] },
          },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      });
    });
  };

  return { queryRequests, installMocks };
}

// ---------------------------------------------------------------------------
// Shared navigation helper
// ---------------------------------------------------------------------------

/**
 * Navigate to production-history and switch to the identifier tab.
 *
 * In mock mode (CI): all APIs mocked via extraMocks.
 * In real mode (local): loginViaApi + navigateViaSidebar with live backend.
 *
 * Returns the captured queryRequests array (only populated in mock mode).
 */
async function navigateToIdentifierTab(
  page: Page,
): Promise<{ queryRequests: Request[] }> {
  const { queryRequests, installMocks } = buildFeatureMocks(page);

  await navigateDual(page, 'production-history', {
    waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    extraMocks: installMocks,
  });

  // Switch to Tab B 「依識別碼查詢」.
  await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
  await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
    timeout: 10_000,
  });

  return { queryRequests };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Production History — multi-line input (AC-5)', () => {
  // -------------------------------------------------------------------------
  // Test 1 (baseline): mixed separators deduplicate into request body
  // -------------------------------------------------------------------------
  test('Mixed CRLF + comma + tab separators dedup into request body', async ({ page }) => {
    const { queryRequests } = await navigateToIdentifierTab(page);

    // Build a deliberately messy input: CRLF, commas, tabs, duplicates,
    // leading/trailing whitespace.
    const messy = '  GA250605\r\nGA250606,\tGA250607 \n  GA250605\r\n\r\n,GA250608  ';
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill(messy);

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    if (USE_MOCKS) {
      const reqPromise = page.waitForRequest('**/api/production-history/query', {
        timeout: 10_000,
      });
      await queryBtn.click();
      const req = await reqPromise;

      const body = req.postDataJSON();
      expect(body.lot_ids).toBeTruthy();
      // 4 unique tokens — duplicate GA250605 must be deduplicated.
      expect([...body.lot_ids].sort()).toEqual([
        'GA250605',
        'GA250606',
        'GA250607',
        'GA250608',
      ]);
      expect(queryRequests.length).toBeGreaterThan(0);
    } else {
      // Real mode: just assert the query fires (button re-enables after response).
      await queryBtn.click();
      await expect(queryBtn).toBeEnabled({ timeout: 20_000 });
    }
  });

  // -------------------------------------------------------------------------
  // Test 2 (baseline): empty identifier query is blocked client-side
  // -------------------------------------------------------------------------
  test('Empty identifier query is blocked client-side — no request sent', async ({
    page,
  }) => {
    const { queryRequests } = await navigateToIdentifierTab(page);

    // Leave all three wildcard textareas empty.
    await page.locator('[data-testid="ph-first-tier-mfg-orders"]').fill('');
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('');
    await page.locator('[data-testid="ph-first-tier-wafer-lots"]').fill('');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
    await queryBtn.click();

    // A validation message must surface.  Tab B requires at least one identifier
    // token — the form error class covers both the inline and banner variants.
    await expect(page.locator('.ph-app__form-error')).toBeVisible({ timeout: 5_000 });

    if (USE_MOCKS) {
      // In mock mode we can assert absolutely that no request was sent.
      await page.waitForTimeout(500);
      expect(queryRequests.length).toBe(0);
    }
    // In real mode: the validation message is sufficient proof; we cannot assert
    // on request count without an interceptor.
  });

  // -------------------------------------------------------------------------
  // Test 3: filling only lot-ids (others empty) is a valid submission
  // -------------------------------------------------------------------------
  test('Single textarea with others empty submits successfully', async ({ page }) => {
    await navigateToIdentifierTab(page);

    // Fill only lot-ids; leave mfg-orders and wafer-lots empty.
    await page.locator('[data-testid="ph-first-tier-mfg-orders"]').fill('');
    await page.locator('[data-testid="ph-first-tier-wafer-lots"]').fill('');
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('GA250605001');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    if (USE_MOCKS) {
      const reqPromise = page.waitForRequest('**/api/production-history/query', {
        timeout: 10_000,
      });
      await queryBtn.click();
      const req = await reqPromise;

      const body = req.postDataJSON();
      // Only lot_ids should carry values; mfg_orders and wafer_lot_ids must be
      // absent or empty so the backend does not treat them as wildcard filters.
      expect(body.lot_ids).toEqual(['GA250605001']);
      const mfgOrders = body.mfg_orders ?? [];
      const waferLots = body.wafer_lot_ids ?? [];
      expect(mfgOrders.length).toBe(0);
      expect(waferLots.length).toBe(0);
    } else {
      // Real mode: query must fire and button must re-enable.
      await queryBtn.click();
      await expect(queryBtn).toBeEnabled({ timeout: 20_000 });
    }
  });

  // -------------------------------------------------------------------------
  // Test 4: wildcard asterisk passes through to request body unchanged
  // -------------------------------------------------------------------------
  test('Wildcard asterisk passes through unchanged to request body', async ({ page }) => {
    await navigateToIdentifierTab(page);

    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('GA25*');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    if (USE_MOCKS) {
      const reqPromise = page.waitForRequest('**/api/production-history/query', {
        timeout: 10_000,
      });
      await queryBtn.click();
      const req = await reqPromise;

      const body = req.postDataJSON();
      // Frontend MUST preserve the raw `*` — backend translates to LIKE bind.
      expect(body.lot_ids).toEqual(['GA25*']);
    } else {
      await queryBtn.click();
      await expect(queryBtn).toBeEnabled({ timeout: 20_000 });
    }
  });

  // -------------------------------------------------------------------------
  // Test 5: mfg-orders textarea deduplication works
  // -------------------------------------------------------------------------
  test('mfg-orders textarea deduplication works', async ({ page }) => {
    await navigateToIdentifierTab(page);

    // Messy mfg-orders: newlines, commas, spaces, duplicate MA2025.
    const messyMfg =
      'MA2025\nMB2025,MC2025  MD2025\nMA2025\r\n\r\nME2025';
    await page.locator('[data-testid="ph-first-tier-mfg-orders"]').fill(messyMfg);

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    if (USE_MOCKS) {
      const reqPromise = page.waitForRequest('**/api/production-history/query', {
        timeout: 10_000,
      });
      await queryBtn.click();
      const req = await reqPromise;

      const body = req.postDataJSON();
      expect(body.mfg_orders).toBeTruthy();
      // 5 unique tokens — MA2025 appeared twice and must be deduplicated.
      expect([...body.mfg_orders].sort()).toEqual([
        'MA2025',
        'MB2025',
        'MC2025',
        'MD2025',
        'ME2025',
      ]);
    } else {
      await queryBtn.click();
      await expect(queryBtn).toBeEnabled({ timeout: 20_000 });
    }
  });

  // -------------------------------------------------------------------------
  // Test 6: wafer-lots textarea contributes correctly to query body
  // -------------------------------------------------------------------------
  test('Wafer-lots textarea multi-line input reaches query body', async ({ page }) => {
    await navigateToIdentifierTab(page);

    await page.locator('[data-testid="ph-first-tier-wafer-lots"]').fill(
      'WL-001\nWL-002\nWL-003',
    );

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    if (USE_MOCKS) {
      const reqPromise = page.waitForRequest('**/api/production-history/query', {
        timeout: 10_000,
      });
      await queryBtn.click();
      const req = await reqPromise;

      const body = req.postDataJSON();
      // Frontend sends wafer lots under the key `wafer_lots` (mirrors useFirstTierFilters).
      expect(body.wafer_lots).toBeTruthy();
      expect([...body.wafer_lots].sort()).toEqual(['WL-001', 'WL-002', 'WL-003']);
    } else {
      await queryBtn.click();
      await expect(queryBtn).toBeEnabled({ timeout: 20_000 });
    }
  });
});
