/**
 * E2E spec: Production History — two query-mode tabs (AC-1, AC-2, AC-3, AC-6)
 *
 * Exercises the explicit query-mode tab split:
 *   - Tab A 「依產品分類查詢」: 4 cached MultiSelects + date range; submitting
 *     with an empty TYPE is blocked with a clear validation message.
 *   - Tab B 「依識別碼查詢」: 3 wildcard textareas only, no date row; pasting a
 *     LOT ID and querying succeeds without TYPE or dates, and the outgoing
 *     payload carries NO start_date/end_date.
 *   - 清除篩選 returns the page to its initial empty state.
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
          detail: { rows: [], pagination: { page: 1, per_page: 25, total_rows: 0, total_pages: 0 } },
          matrix: { tree: [], month_columns: [] },
        },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    });
  });

  await page.route('**/api/production-history/options', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { workcenter_groups: [], equipment_ids: [] },
        meta: {},
      }),
    }),
  );

  return { queryRequests };
}

test.describe('Production History — query-mode tabs', () => {
  test('tabs render and switch between 依產品分類查詢 and 依識別碼查詢 (AC-1)', async ({ page }) => {
    await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-classification"]',
    });

    // Tab A active by default: classification panel visible, identifier hidden.
    await expect(page.locator('[data-testid="ph-mode-panel-classification"]')).toBeVisible();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeHidden();
    await expect(page.locator('[data-testid="ph-start-date"]')).toBeVisible();

    // Switch to Tab B: identifier panel visible, NO date row.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible();
    await expect(page.locator('[data-testid="ph-mode-panel-classification"]')).toBeHidden();
    await expect(page.locator('[data-testid="ph-first-tier-lot-ids"]')).toBeVisible();

    // Switch back to Tab A.
    await page.locator('[data-testid="ph-mode-tab-classification"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-classification"]')).toBeVisible();
  });

  test('Tab A blocks query with empty TYPE showing validation message (AC-2)', async ({ page }) => {
    const { queryRequests } = await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-query-btn"]',
    });

    // Tab A is active; dates are pre-filled with the default window, but no
    // TYPE is selected → query must be blocked.
    await page.locator('[data-testid="ph-query-btn"]').click();

    const formError = page.locator('[data-testid="ph-form-error"]');
    await expect(formError).toBeVisible();
    await expect(formError).toContainText('Type');
    expect(queryRequests.length).toBe(0);
  });

  test('Tab B has no date row; paste LOT ID and query succeeds without TYPE/dates (AC-3)', async ({
    page,
  }) => {
    const { queryRequests } = await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();

    // No date inputs rendered in the identifier panel.
    await expect(page.locator('[data-testid="ph-start-date"]')).toBeHidden();
    await expect(page.locator('[data-testid="ph-end-date"]')).toBeHidden();

    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('GA250605001');

    const reqPromise = page.waitForRequest('**/api/production-history/query', { timeout: 10_000 });
    await page.locator('[data-testid="ph-query-btn"]').click();
    const req = await reqPromise;

    const body = req.postDataJSON();
    expect(body.lot_ids).toEqual(['GA250605001']);
    // Identifier-mode payload carries NO dates and NO classification fields.
    expect(body.start_date).toBeUndefined();
    expect(body.end_date).toBeUndefined();
    expect(body.pj_types).toBeUndefined();
    expect(queryRequests.length).toBe(1);
  });

  test('清除篩選 returns page to initial empty state across both tabs (AC-6)', async ({ page }) => {
    await installMocks(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-mode-tab-identifier"]',
    });

    // Run an identifier-mode query so results appear.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await page.locator('[data-testid="ph-first-tier-mfg-orders"]').fill('MA2025*');
    await page.locator('[data-testid="ph-query-btn"]').click();

    // Detail table appears once a dataset is loaded; empty state is gone.
    await expect(page.locator('[data-testid="ph-empty-state"]')).toBeHidden();

    // 清除篩選 resets the textarea + results back to the empty state.
    await page.locator('[data-testid="ph-clear-filters"]').click();
    await expect(page.locator('[data-testid="ph-first-tier-mfg-orders"]')).toHaveValue('');
    await expect(page.locator('[data-testid="ph-empty-state"]')).toBeVisible();
  });
});
