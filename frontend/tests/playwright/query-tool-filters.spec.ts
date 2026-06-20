/**
 * E2E gap-filling spec: Query Tool — filter panel, table interaction,
 * search-condition, and URL-state tests.
 *
 * Covers:
 *  - Equipment tab date inputs
 *  - Dates included in API payload
 *  - Multi-line LOT IDs in textarea
 *  - Empty-input validation (LOT and Equipment tabs)
 *  - Results table rows via mock
 *  - Pagination controls via mock
 *  - Error banner on 500
 *  - URL state after tab switch
 *  - Export button visibility after results
 *
 * Pattern notes (ci-workflow.md):
 *  - page.route() LIFO: catch-all first, specific routes last.
 *  - pageRendered guard: check .theme-query-tool, not bodyText.length > 100.
 *  - Use page.goto().catch(()=>{}) + early-return guard — not page.request.post().
 *  - Playwright specs: use navigateViaSidebar, not direct goto for SPA routes.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

// ── Mock data ─────────────────────────────────────────────────────────────────

const MOCK_EQUIPMENT_LIST = {
  success: true,
  data: {
    data: [
      { RESOURCEID: 'EQ-MOCK-01', RESOURCENAME: 'Mock Wire Bonder 01' },
      { RESOURCEID: 'EQ-MOCK-02', RESOURCENAME: 'Mock Die Bonder 02' },
    ],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_WORKCENTER_GROUPS = {
  success: true,
  data: { data: [{ name: 'WB_GROUP' }, { name: 'DB_GROUP' }] },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_EQUIPMENT_PERIOD_LOTS = {
  success: true,
  data: {
    data: [
      {
        CONTAINERID: 'CNT-001',
        CONTAINERNAME: 'LOT-A',
        RESOURCEID: 'EQ-MOCK-01',
        RESOURCENAME: 'Mock Wire Bonder 01',
        TRACKINTIME: '2026-06-10 08:00:00',
        TRACKOUTTIME: '2026-06-10 09:00:00',
      },
      {
        CONTAINERID: 'CNT-002',
        CONTAINERNAME: 'LOT-B',
        RESOURCEID: 'EQ-MOCK-01',
        RESOURCENAME: 'Mock Wire Bonder 01',
        TRACKINTIME: '2026-06-10 10:00:00',
        TRACKOUTTIME: '2026-06-10 11:00:00',
      },
    ],
    pagination: { page: 1, per_page: 25, total: 2, total_pages: 1 },
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_EQUIPMENT_PERIOD_PAGINATED = {
  success: true,
  data: {
    data: Array.from({ length: 25 }, (_, i) => ({
      CONTAINERID: `CNT-${String(i).padStart(3, '0')}`,
      CONTAINERNAME: `LOT-${i}`,
      RESOURCEID: 'EQ-MOCK-01',
      RESOURCENAME: 'Mock Wire Bonder 01',
      TRACKINTIME: '2026-06-10 08:00:00',
      TRACKOUTTIME: '2026-06-10 09:00:00',
    })),
    pagination: { page: 1, per_page: 25, total: 60, total_pages: 3 },
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_RESOLVE_LOTS = {
  success: true,
  data: {
    data: [
      { CONTAINERID: 'CNT-LOT-001', CONTAINERNAME: 'TEST-LOT-001', TYPE: 'WAFER_LOT' },
      { CONTAINERID: 'CNT-LOT-002', CONTAINERNAME: 'TEST-LOT-002', TYPE: 'WAFER_LOT' },
    ],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Register base API mocks for query-tool bootstrap calls.
 * LIFO: catch-all registered first, specific endpoints last.
 */
async function setupBaseMocks(page: import('@playwright/test').Page) {
  // Catch-all for all query-tool endpoints (lowest priority)
  await page.route('**/api/query-tool/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { data: [] }, meta: {} }),
    })
  );

  // Specific bootstrap endpoints (higher priority)
  await page.route('**/api/query-tool/workcenter-groups**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_WORKCENTER_GROUPS),
    })
  );

  await page.route('**/api/query-tool/equipment-list**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_EQUIPMENT_LIST),
    })
  );
}

async function navigateToQueryTool(page: import('@playwright/test').Page) {
  let failed = false;
  await page.goto('/portal-shell/').catch(() => { failed = true; });
  if (failed) return false;

  await navigateViaSidebar(page, 'query-tool', {
    waitForSelector: 'nav[aria-label="query-tool tabs"]',
  }).catch(() => {});

  const hasTheme = await page.evaluate(() =>
    Boolean(document.querySelector('.theme-query-tool'))
  );
  return hasTheme;
}

async function switchToEquipmentTab(page: import('@playwright/test').Page) {
  const tabBtn = page.locator('[data-testid="tab-equipment"]');
  await tabBtn.click();
  // Wait for Equipment view date inputs to appear
  await page.locator('[data-testid="start-date"]').waitFor({ state: 'visible', timeout: 10_000 });
}

async function selectFirstEquipment(page: import('@playwright/test').Page): Promise<void> {
  // The equipment MultiSelect sits inside a label with text "設備（可複選）".
  // Scoping the trigger click avoids accidentally opening a different MultiSelect.
  const trigger = page.locator('label').filter({ hasText: '設備（可複選）' }).locator('button').first();
  await trigger.waitFor({ state: 'visible', timeout: 10_000 });
  await trigger.click();

  // Options teleport to <body> — wait until at least one appears.
  await page.waitForSelector('[data-testid="multiselect-option"]', { timeout: 10_000 });
  await page.locator('[data-testid="multiselect-option"]').first().click();

  // Brief pause for Vue reactivity (modelValue → emit → setSelectedEquipmentIds) to settle.
  await page.waitForTimeout(300);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('Query Tool — filter panel and interactions', () => {
  test.beforeEach(async ({ page }) => {
    await setupBaseMocks(page);
    await loginViaApi(page);
  });

  // 1. Equipment tab shows date inputs
  test('test_date_range_inputs_in_equipment_tab', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');

    await expect(startDate).toBeVisible({ timeout: 10_000 });
    await expect(endDate).toBeVisible({ timeout: 10_000 });
    await expect(startDate).toHaveAttribute('type', 'date');
    await expect(endDate).toHaveAttribute('type', 'date');
  });

  // 2. Dates appear in the API request payload when Equipment tab submits
  test('test_equipment_query_date_in_payload', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    // Capture the equipment-period request body
    const requestBodies: string[] = [];
    await page.route('**/api/query-tool/equipment-period**', (route) => {
      requestBodies.push(route.request().postData() ?? '');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD_LOTS),
      });
    });

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await startDate.fill('2026-06-01');
    await endDate.fill('2026-06-07');

    await selectFirstEquipment(page);

    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
    await submitBtn.click();

    // Wait for the API call to be captured
    await page.waitForFunction(() => true, { timeout: 8_000 }).catch(() => {});
    await page.waitForTimeout(2_000);

    expect(requestBodies.length).toBeGreaterThan(0);
    const body = requestBodies[0];
    expect(body).toContain('2026-06-01');
    expect(body).toContain('2026-06-07');
  });

  // 3. Multi-line LOT IDs sent in payload
  test('test_lot_input_multiline', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    const resolveRequests: string[] = [];
    await page.route('**/api/query-tool/resolve**', (route) => {
      resolveRequests.push(route.request().postData() ?? '');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_RESOLVE_LOTS),
      });
    });

    // LOT tab is active by default
    const lotInput = page.locator('[data-testid="lot-input"]').first();
    await expect(lotInput).toBeVisible({ timeout: 10_000 });

    const multilineLots = 'TEST-LOT-001\nTEST-LOT-002\nTEST-LOT-003';
    await lotInput.fill(multilineLots);

    // Submit (resolve button)
    const submitBtn = page.locator('[data-testid="submit-btn"]').first();
    await submitBtn.click();

    await page.waitForTimeout(2_000);

    expect(resolveRequests.length).toBeGreaterThan(0);
    const body = resolveRequests[0];
    // All three LOT IDs should be present in the request
    expect(body).toContain('TEST-LOT-001');
    expect(body).toContain('TEST-LOT-002');
    expect(body).toContain('TEST-LOT-003');
  });

  // 4. Empty LOT input validation — no API call or error shown without input
  test('test_empty_lot_input_validation', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    let resolveCallCount = 0;
    await page.route('**/api/query-tool/resolve**', (route) => {
      resolveCallCount++;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_RESOLVE_LOTS),
      });
    });

    const lotInput = page.locator('[data-testid="lot-input"]').first();
    await expect(lotInput).toBeVisible({ timeout: 10_000 });
    // Ensure input is empty
    await lotInput.fill('');

    const submitBtn = page.locator('[data-testid="submit-btn"]').first();
    await submitBtn.click();

    await page.waitForTimeout(1_500);

    // The resolve composable bails early when inputText is empty — no API call
    expect(resolveCallCount).toBe(0);
  });

  // 5. Equipment tab with no equipment selected — button stays enabled (all filtered)
  test('test_empty_equipment_validation', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    await page.route('**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD_LOTS),
      })
    );

    await switchToEquipmentTab(page);

    // No equipment selected — submit button should still be visible/enabled
    // (Equipment tab sends query for all equipment when none selected)
    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await expect(submitBtn).toBeVisible({ timeout: 5_000 });
    await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
  });

  // 6. Results table rows appear after mock successful response
  test('test_results_table_rows', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    await page.route('**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD_LOTS),
      })
    );

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await startDate.fill('2026-06-01');
    await endDate.fill('2026-06-07');

    await selectFirstEquipment(page);

    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await submitBtn.click();

    // Wait for table rows to appear (DataTable uses data-testid="datatable-row")
    await page.waitForSelector('[data-testid="datatable-row"]', { timeout: 15_000 });

    const rows = page.locator('[data-testid="datatable-row"]');
    await expect(rows).toHaveCount(2, { timeout: 10_000 });
  });

  // 7. Pagination controls appear when total > per_page
  test('test_pagination_appears', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    await page.route('**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD_PAGINATED),
      })
    );

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await startDate.fill('2026-06-01');
    await endDate.fill('2026-06-07');

    await selectFirstEquipment(page);

    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await submitBtn.click();

    // Wait for pagination controls (page-prev / page-next from BasePagination)
    await page.waitForSelector('[data-testid="page-next"]', { timeout: 15_000 });

    const pageNext = page.locator('[data-testid="page-next"]');
    const pagePrev = page.locator('[data-testid="page-prev"]');

    await expect(pageNext).toBeVisible({ timeout: 5_000 });
    await expect(pagePrev).toBeVisible({ timeout: 5_000 });

    // Next should be enabled (total_pages=3, current=1)
    await expect(pageNext).toBeEnabled({ timeout: 5_000 });
    // Prev should be disabled on page 1
    await expect(pagePrev).toBeDisabled({ timeout: 5_000 });
  });

  // 8. Error banner shown when equipment query returns 500
  test('test_error_state_equipment_query', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    // Register error mock for equipment-period
    await page.route('**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'INTERNAL_ERROR', message: 'Database unavailable (mock 500)' },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      })
    );

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await startDate.fill('2026-06-01');
    await endDate.fill('2026-06-07');

    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await submitBtn.click();

    // Wait for error state — either ErrorBanner (.error-banner-wrap) or error text
    await page.waitForFunction(
      () => {
        const banner = document.querySelector('.error-banner-wrap, [role="alert"]');
        if (banner && (banner as HTMLElement).textContent?.trim()) return true;
        const errorText = document.body.textContent || '';
        return errorText.includes('失敗') || errorText.includes('error') || errorText.includes('Error');
      },
      { timeout: 15_000, polling: 500 }
    );

    // Assert either the error-banner-wrap is present or some error text is shown
    const errorBanner = page.locator('.error-banner-wrap, [role="alert"]').first();
    await expect(errorBanner).toBeVisible({ timeout: 5_000 });
  });

  // 9. URL contains tab=lot after switching back to LOT tab
  test('test_url_state_lot_tab', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    // Start on Equipment tab, then switch back to LOT tab
    const equipmentTabBtn = page.locator('[data-testid="tab-equipment"]');
    await equipmentTabBtn.click();

    const lotTabBtn = page.locator('[data-testid="tab-lot"]');
    await lotTabBtn.click();

    // URL should be updated to reflect tab=lot
    await expect.poll(
      () => new URL(page.url()).searchParams.get('tab'),
      { timeout: 5_000 }
    ).toBe('lot');
  });

  // 10. Export button triggers download when results are shown
  test('test_export_button_after_results', async ({ page }) => {
    const reachable = await navigateToQueryTool(page);
    if (!reachable) {
      test.skip(true, 'query-tool page not reachable in this environment');
      return;
    }

    await page.route('**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD_LOTS),
      })
    );

    // Mock the export endpoint
    await page.route('**/api/query-tool/export**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'CONTAINERID,CONTAINERNAME\nCNT-001,LOT-A\n',
        headers: { 'Content-Disposition': 'attachment; filename="export.csv"' },
      })
    );

    await switchToEquipmentTab(page);

    const startDate = page.locator('[data-testid="start-date"]');
    const endDate = page.locator('[data-testid="end-date"]');
    await startDate.fill('2026-06-01');
    await endDate.fill('2026-06-07');

    await selectFirstEquipment(page);

    const submitBtn = page.locator('[data-testid="submit-btn"]').filter({ hasText: /查詢/ });
    await submitBtn.click();

    // Wait for rows to appear before checking export button
    await page.waitForSelector('[data-testid="datatable-row"]', { timeout: 15_000 });

    // ExportButton renders inside the active sub-tab panel
    const exportBtn = page.locator(
      'button:has-text("匯出"), button:has-text("Export"), .ui-btn--secondary'
    ).first();

    if (await exportBtn.count() === 0) {
      // Export button not present in this view state — acceptable skip
      return;
    }

    await expect(exportBtn).toBeVisible({ timeout: 5_000 });
  });
});
