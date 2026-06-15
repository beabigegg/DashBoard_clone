/**
 * Data-boundary tests: material-consumption page
 * Change: material-part-consumption
 * Tier 1 — run in CI pre-merge
 *
 * Tests:
 *   test_21_parts_over_cap_disables_submit
 *   test_0_row_result_shows_empty_state
 *   test_submit_disabled_without_parts_selected
 *   test_api_query_error_shows_error_banner
 *
 * Note: wildcard/SQL-injection text-input tests were removed because the
 * material-parts input is now a MultiSelect combobox — arbitrary free-text
 * can no longer be submitted via the UI. Backend validation is tested at
 * the API layer (pytest); UI validation is tested via canSubmit guard.
 */

import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/portal-shell/material-consumption`;

// 21 parts — needed for the over-cap test (cap is 20)
const PARTS_21 = Array.from({ length: 21 }, (_, i) => ({ name: `Part${String(i + 1).padStart(3, '0')}` }));

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    parts: PARTS_21,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_PORTAL_NAV = {
  drawers: [
    {
      id: 'drawer',
      name: '查詢工具',
      order: 3,
      admin_only: false,
      pages: [{ route: '/material-consumption', name: '原物料用量查詢', status: 'released', order: 6 }],
    },
  ],
  is_admin: false,
  admin_user: null,
  admin_links: { logout: null, pages: null, dashboard: null, performance: null },
  diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
  portal_spa_enabled: false,
  features: { ai_query_enabled: false },
};

async function setupBasicMocks(page: Page) {
  await page.route('**/api/material-consumption/filter-options', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_FILTER_OPTIONS) });
  });

  await page.route('**/api/auth/me**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser', role: 'user' } }),
    });
  });

  await page.route('**/api/pages**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    });
  });

  // 200ms delay lets the Vue Router initial navigation commit before addRoute fires
  await page.route('**/api/portal/navigation**', async (route) => {
    await new Promise((r) => setTimeout(r, 200));
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PORTAL_NAV) });
  });
}

async function selectParts(page: Page, parts: string[]) {
  await page.waitForSelector('[data-testid="material-parts-select"] .multi-select-trigger:not([disabled])', { timeout: 45_000 });
  await page.locator('[data-testid="material-parts-select"] .multi-select-trigger').click();
  for (const part of parts) {
    await page.locator('.multi-select-search').fill(part);
    await page.locator('.multi-select-option').filter({ hasText: part }).first().click();
    await page.locator('.multi-select-search').fill('');
  }
  await page.locator('.multi-select-dropdown button:has-text("關閉")').click();
}

test('test_21_parts_over_cap_disables_submit', async ({ page }) => {
  await setupBasicMocks(page);
  await page.goto(PAGE_URL);

  // Wait until filter-options has loaded (trigger becomes enabled)
  await page.waitForSelector('[data-testid="material-parts-select"] .multi-select-trigger:not([disabled])', { timeout: 45_000 });
  // Use "全選" to select all 21 parts at once (dropdown is teleported to body)
  await page.locator('[data-testid="material-parts-select"] .multi-select-trigger').click();
  await page.locator('.multi-select-actions button:has-text("全選")').click();
  // Close dropdown
  await page.locator('.multi-select-dropdown button:has-text("關閉")').click();

  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');

  // With 21 parts selected (> 20 cap), canSubmit = false → button disabled
  const submitBtn = page.locator('[data-testid="query-submit-button"]');
  await expect(submitBtn).toBeDisabled({ timeout: 3000 });

  // Over-cap indicator text should be visible
  await expect(page.locator('text=超過上限')).toBeVisible({ timeout: 3000 });
});

test('test_0_row_result_shows_empty_state', async ({ page }) => {
  await setupBasicMocks(page);

  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          query_id: 'empty-query-id',
          kpi: { total_consumed: 0, total_required: 0, efficiency_pct: 0, lot_count: 0, workorder_count: 0 },
          trend: [],
          type_breakdown: [],
        },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    });
  });

  await page.goto(PAGE_URL);
  await selectParts(page, ['Part001']);
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');

  await page.waitForTimeout(2000);

  // Query succeeded with 0 rows: results section shows (kpi-cards) and trend chart shows no-data indicator
  await expect(page.locator('.kpi-cards')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('.chart-empty').first()).toBeVisible({ timeout: 3000 });
});

test('test_submit_disabled_without_parts_selected', async ({ page }) => {
  await setupBasicMocks(page);
  await page.goto(PAGE_URL);
  // Wait for the app to mount and filter-options to load (trigger enabled)
  await page.waitForSelector('[data-testid="material-parts-select"] .multi-select-trigger:not([disabled])', { timeout: 45_000 });

  // Fill dates only — no parts selected
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');

  // canSubmit requires selectedParts.length > 0; button must be disabled
  const submitBtn = page.locator('[data-testid="query-submit-button"]');
  await expect(submitBtn).toBeDisabled({ timeout: 3000 });
});

test('test_api_query_error_shows_error_banner', async ({ page }) => {
  await setupBasicMocks(page);

  // Backend returns 400 — tests that the UI renders ErrorBanner on failure
  await page.route('**/api/material-consumption/query', (route) => {
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'VALIDATION_ERROR', message: '查詢參數無效' },
        meta: {},
      }),
    });
  });

  await page.goto(PAGE_URL);
  await selectParts(page, ['Part001']);
  await page.fill('[data-testid="start-date"]', '2026-01-01');
  await page.fill('[data-testid="end-date"]', '2026-01-31');
  await page.click('[data-testid="query-submit-button"]');

  // Error banner should appear
  const errorBanner = page.locator('.error-banner-wrap, [role="alert"]');
  await expect(errorBanner.first()).toBeVisible({ timeout: 5000 });
});
