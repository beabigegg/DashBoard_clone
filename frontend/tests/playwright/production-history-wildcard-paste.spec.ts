/**
 * E2E spec: Production History — wildcard textarea UX (AC-4, AC-5)
 *
 * Exercises the three wildcard textareas (mfg_orders / lot_ids / wafer_lots):
 *   - Paste multi-line input with mixed separators → dedup tokens reach the
 *     /api/production-history/query request body
 *   - Type `MA*` wildcard → request body carries the raw `*` glob (backend
 *     handles `*` → LIKE conversion per PHF-02)
 *   - Type SQL meta chars (`'`, `;`, `--`) → frontend or backend rejects with
 *     400 + validation feedback; the request never reaches Oracle
 *
 * All selectors use data-testid anchors from the frontend-engineer hand-off.
 */

import { test, expect, type Page, type Request } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

const FILTER_OPTIONS_PAYLOAD = {
  success: true,
  data: {
    pj_types: ['A', 'B'],
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

async function installMocks(
  page: Page,
  opts: { queryStatus?: number; queryBody?: object } = {},
): Promise<{ queryRequests: Request[] }> {
  const queryRequests: Request[] = [];

  await page.route('**/api/production-history/filter-options**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FILTER_OPTIONS_PAYLOAD),
    });
  });

  await page.route('**/api/production-history/query', async (route) => {
    queryRequests.push(route.request());
    if (opts.queryStatus && opts.queryStatus >= 400) {
      await route.fulfill({
        status: opts.queryStatus,
        contentType: 'application/json',
        body: JSON.stringify(
          opts.queryBody ?? {
            success: false,
            error: {
              code: 'VALIDATION_ERROR',
              message: 'wildcard contains forbidden meta character',
            },
            meta: { timestamp: new Date().toISOString(), app_version: 'test' },
          },
        ),
      });
      return;
    }
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

  // Stub other init APIs to avoid backend dependency.
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

  return { queryRequests };
}

// The two-tab redesign (prod-history-query-mode-tabs) moved the wildcard
// textareas into Tab B 「依識別碼查詢」. Wildcard queries no longer require a
// Type selection or a date range (D6-style mode split) — switching to Tab B is
// the only precondition.
async function switchToIdentifierTab(page: Page) {
  await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
  await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
    timeout: 10_000,
  });
}

test.describe('Production History — wildcard textarea UX', () => {
  test('Multi-line paste dedupes tokens into request body (AC-5)', async ({ page }) => {
    const { queryRequests } = await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await switchToIdentifierTab(page);

    const textarea = page.locator('[data-testid="ph-first-tier-mfg-orders"]');
    // Mixed separators: newlines, commas, multiple spaces, AND a duplicate.
    await textarea.fill('MA2025\nMB2025,MC2025  MD2025\nMA2025');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    const reqPromise = page.waitForRequest('**/api/production-history/query', { timeout: 10_000 });
    await queryBtn.click();
    const req = await reqPromise;

    const body = req.postDataJSON();
    expect(body.mfg_orders).toBeTruthy();
    // 4 unique tokens after dedup (MA2025 appeared twice).
    expect([...body.mfg_orders].sort()).toEqual(['MA2025', 'MB2025', 'MC2025', 'MD2025']);
    expect(queryRequests.length).toBeGreaterThan(0);
  });

  test('Wildcard `MA*` reaches request body unchanged (AC-4)', async ({ page }) => {
    await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await switchToIdentifierTab(page);

    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('MA*');

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    const reqPromise = page.waitForRequest('**/api/production-history/query', { timeout: 10_000 });
    await queryBtn.click();
    const req = await reqPromise;

    const body = req.postDataJSON();
    // Frontend MUST preserve the raw `*` — backend translates to LIKE bind.
    expect(body.lot_ids).toEqual(['MA*']);
  });

  test('SQL meta char triggers 400 + UI shows error (AC-4)', async ({ page }) => {
    await installMocks(page, {
      queryStatus: 400,
      queryBody: {
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: '萬用字元包含不允許的符號',
          field: 'lot_ids',
        },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      },
    });
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await switchToIdentifierTab(page);
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill("MA' OR 1=1--");

    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
    await queryBtn.click();

    // Any of: error banner, role=alert, error class — must surface.
    await page.waitForFunction(
      () => {
        const sels = [
          '[role="alert"]',
          '[class*="error-banner"]',
          '[class*="ph-app__form-error"]',
          '[class*="error"]',
        ];
        return sels.some((sel) => {
          const el = document.querySelector(sel);
          return el && (el as HTMLElement).offsetParent !== null;
        });
      },
      { timeout: 15_000 },
    );
  });
});
