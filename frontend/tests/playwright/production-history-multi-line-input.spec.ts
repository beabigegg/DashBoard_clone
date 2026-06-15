/**
 * E2E spec: Production History — multi-line textarea parser idempotence (AC-5)
 *
 * Verifies that:
 *   - Paste with mixed separators (CRLF + comma + tab) yields the right
 *     deduplicated token list in the outgoing query body
 *   - An identifier-mode query with all wildcard textareas empty is blocked
 *     client-side (no request sent) with a validation message
 *
 * Note (prod-history-query-mode-tabs): the old "empty textarea omits the
 * wildcard field" back-compat case no longer exists by design. After the
 * two-tab split, wildcard fields live only in Tab B 「依識別碼查詢」, and Tab B
 * requires ≥1 identifier token to submit — there is no flow that sends a query
 * with empty wildcard inputs. The empty-input case is therefore re-expressed
 * as a client-side validation block.
 *
 * The parser idempotence proof at the data layer
 * (parse(parse(x)) == parse(x)) is covered by
 * frontend/tests/validation/useProductionHistory.validation.test.js;
 * this spec asserts the user-visible end-to-end behaviour.
 */

import { test, expect, type Page, type Request } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

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

async function installMocks(page: Page): Promise<{ queryRequests: Request[] }> {
  const queryRequests: Request[] = [];

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

  return { queryRequests };
}

// The two-tab redesign (prod-history-query-mode-tabs) moved the wildcard
// textareas into Tab B 「依識別碼查詢」. An identifier-mode query needs neither
// a Type selection nor a date range — switching to Tab B is the only setup.
async function switchToIdentifierTab(page: Page) {
  await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
  await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
    timeout: 10_000,
  });
}

test.describe('Production History — multi-line input (AC-5)', () => {
  test('Mixed CRLF + comma + tab separators dedup into request body', async ({ page }) => {
    await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await switchToIdentifierTab(page);

    // Build a deliberately messy input: CRLF, commas, tabs, duplicates,
    // leading/trailing whitespace.
    const messy = '  GA250605\r\nGA250606,\tGA250607 \n  GA250605\r\n\r\n,GA250608  ';
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill(messy);

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    const reqPromise = page.waitForRequest('**/api/production-history/query', { timeout: 10_000 });
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
  });

  test('Empty identifier query is blocked client-side — no request sent', async ({
    page,
  }) => {
    const { queryRequests } = await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await switchToIdentifierTab(page);

    // Leave all three wildcard textareas empty.
    await page.locator('[data-testid="ph-first-tier-mfg-orders"]').fill('');
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('');
    await page.locator('[data-testid="ph-first-tier-wafer-lots"]').fill('');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
    await queryBtn.click();

    // A validation message must surface and NO query request is sent — Tab B
    // requires at least one identifier token.
    await expect(page.locator('.ph-app__form-error')).toBeVisible({ timeout: 5_000 });
    await page.waitForTimeout(500);
    expect(queryRequests.length).toBe(0);
  });
});
