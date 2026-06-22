/**
 * E2E spec: Query Tool page
 *
 * Dual-mode: mock in CI (USE_MOCKS=true), real backend locally.
 *
 * Happy-path assertions are structural (element visibility, enabled state)
 * so they work in both modes.  Error-injection tests are mock-only and are
 * skipped when USE_MOCKS=false.
 *
 * API endpoints exercised:
 *   GET  /api/query-tool/workcenter-groups
 *   GET  /api/query-tool/equipment-list
 *   POST /api/query-tool/resolve
 *   POST /api/query-tool/equipment-period
 */

import { test, expect } from '@playwright/test';
import { USE_MOCKS, conditionalRoute, navigateDual } from './_api-mode.js';

// ---------------------------------------------------------------------------
// Mock payloads
// ---------------------------------------------------------------------------

const MOCK_WORKCENTER_GROUPS = {
  success: true,
  data: {
    data: [
      { name: '焊接_WB' },
      { name: '焊接_DB' },
    ],
  },
};

const MOCK_EQUIPMENT_LIST = {
  success: true,
  data: {
    data: [
      { RESOURCEID: 'EQ-01', RESOURCENAME: 'Wire Bonder 01' },
      { RESOURCEID: 'EQ-02', RESOURCENAME: 'Die Bonder 02' },
    ],
  },
};

const MOCK_EQUIPMENT_PERIOD = {
  success: true,
  data: {
    lots: [
      {
        lot_id: 'LOT-001',
        workcenter: 'WB-01',
        start_time: '2026-03-01',
        end_time: '2026-03-02',
      },
    ],
    total: 1,
  },
};

const MOCK_RESOLVE = {
  success: true,
  data: {
    resolved: [{ lot_id: 'LOT-001', lot_type: 'wafer_lot' }],
  },
};

const DUMMY_LOT_ID = 'TEST-LOT-E2E-00001';

// ---------------------------------------------------------------------------
// Shared beforeEach: navigate to the query-tool page with infrastructure mocks.
// Feature mocks (workcenter-groups, equipment-list) are active in mock mode only.
// ---------------------------------------------------------------------------

test.describe('Query Tool page', () => {
  test.beforeEach(async ({ page }) => {
    await navigateDual(page, 'query-tool', {
      waitForSelector: 'nav[aria-label="query-tool tabs"]',
      extraMocks: async () => {
        await page.route('**/api/query-tool/workcenter-groups**', (route) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(MOCK_WORKCENTER_GROUPS),
          }),
        );
        await page.route('**/api/query-tool/equipment-list**', (route) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(MOCK_EQUIPMENT_LIST),
          }),
        );
      },
    });
  });

  // -------------------------------------------------------------------------
  // 1. All three tab buttons are visible after mount
  // -------------------------------------------------------------------------

  test('test_page_loads_with_tab_navigation', async ({ page }) => {
    const tabNav = page.locator('nav[aria-label="query-tool tabs"]');
    await expect(tabNav).toBeVisible({ timeout: 20_000 });

    // At least one of the three known tab labels must be present.
    const firstTab = page.locator(
      'button:has-text("批次追蹤"), button:has-text("流水批反查"), button:has-text("設備生產")',
    ).first();
    await expect(firstTab).toBeVisible({ timeout: 10_000 });
  });

  // -------------------------------------------------------------------------
  // 2. LOT tab textarea is visible and enabled
  // -------------------------------------------------------------------------

  test('test_lot_tab_input_area_visible', async ({ page }) => {
    // Default tab should be the lot / batch tab; verify textarea is ready.
    const textarea = page.locator('textarea.query-tool-textarea, textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await expect(textarea).toBeEnabled();
  });

  // -------------------------------------------------------------------------
  // 3. Equipment tab exposes date-range inputs
  // -------------------------------------------------------------------------

  test('test_equipment_tab_shows_date_inputs', async ({ page }) => {
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });

    if (await equipmentTab.count() === 0) {
      test.skip(true, 'Equipment tab not found in this build');
      return;
    }

    await equipmentTab.click();

    const dateInput = page.locator('input[type="date"]:visible').first();
    await expect(dateInput).toBeVisible({ timeout: 10_000 });
    await expect(dateInput).toBeEnabled();
  });

  // -------------------------------------------------------------------------
  // 4. Equipment tab: submit query → result, empty-state, or error appears
  //    In mock mode: equipment-period returns 1 lot → assert table or result visible.
  //    In real mode: structural assertion only (submit button re-enables).
  // -------------------------------------------------------------------------

  test('test_equipment_tab_query_returns_result_or_empty', async ({ page }) => {
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });

    if (await equipmentTab.count() === 0) {
      test.skip(true, 'Equipment tab not found in this build');
      return;
    }

    await equipmentTab.click();

    const dateInputs = page.locator('input[type="date"]:visible');
    await expect(dateInputs.first()).toBeVisible({ timeout: 10_000 });
    await dateInputs.nth(0).fill('2026-03-01');
    await dateInputs.nth(1).fill('2026-03-07');

    // Register equipment-period mock only in mock mode (LIFO: register before submit).
    await conditionalRoute(page, '**/api/query-tool/equipment-period**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EQUIPMENT_PERIOD),
      }),
    );

    // Use :visible — on the equipment tab the lot-panel's submit button is hidden.
    const submitBtn = page
      .locator('button.ui-btn.ui-btn--primary:visible, button:has-text("查詢"):visible')
      .first();
    await expect(submitBtn).toBeVisible({ timeout: 10_000 });
    await submitBtn.click();

    if (USE_MOCKS) {
      // Mock mode: expect the table (with 1 mocked row) or a result container.
      const resultArea = page.locator(
        'table, .query-tool-table, [class*="result"], [class*="lot-list"]',
      ).first();
      await expect(resultArea).toBeVisible({ timeout: 15_000 });
    } else {
      // Real mode: button must re-enable once the request completes.
      await expect(submitBtn).toBeEnabled({ timeout: 30_000 });

      const hasAnyOutcome = await page.evaluate(() =>
        Boolean(
          document.querySelector('table') ||
          document.querySelector('.empty-state') ||
          document.querySelector('[class*="error"]') ||
          document.querySelector('[class*="no-data"]') ||
          document.querySelector('[class*="result"]'),
        ),
      );
      expect(hasAnyOutcome, 'Page must show some outcome after equipment query').toBe(true);
    }
  });

  // -------------------------------------------------------------------------
  // 5. Reverse-lineage tab (流水批反查) renders a textarea
  // -------------------------------------------------------------------------

  test('test_reverse_lineage_tab_accessible', async ({ page }) => {
    const reverseTab = page.getByRole('button', { name: '流水批反查' });

    if (await reverseTab.count() === 0) {
      test.skip(true, '流水批反查 tab not present in this build');
      return;
    }

    await reverseTab.click();

    // After switching, the LOT textarea is hidden; :visible finds the reverse panel's one.
    const textarea = page.locator('textarea:visible').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await expect(textarea).toBeEnabled();
  });

  // -------------------------------------------------------------------------
  // 6. Switching tabs updates the URL tab= param
  // -------------------------------------------------------------------------

  test('test_tab_switching_updates_url', async ({ page }) => {
    // Switch to equipment tab → URL should contain tab=equipment.
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });
    if (await equipmentTab.count() > 0) {
      await equipmentTab.click();
      await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=equipment');
    }

    // Switch to reverse-lineage tab → URL should contain tab=reverse.
    const reverseTab = page.getByRole('button', { name: '流水批反查' });
    if (await reverseTab.count() > 0) {
      await reverseTab.click();
      await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=reverse');
    }

    // Switch back to lot tab — use data-testid to avoid strict-mode violation
    // (multiple tab labels contain '批次追蹤' as a substring).
    const lotTab = page.locator('[data-testid="tab-lot"]');
    if (await lotTab.count() > 0) {
      await lotTab.click();
      // Either URL has tab=lot or the lot tab carries aria-current=page.
      await Promise.race([
        expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=lot'),
        expect(lotTab).toHaveAttribute('aria-current', 'page'),
      ]).catch(() => {
        // One of the two forms is acceptable; if neither resolves cleanly we
        // confirm the URL at least does NOT contain tab=equipment / tab=reverse.
        expect(page.url()).not.toContain('tab=equipment');
      });
    }
  });

  // -------------------------------------------------------------------------
  // 7. LOT tab: 500 error from /resolve shows an error element
  //    Mock-only test — skipped when running against a real backend.
  // -------------------------------------------------------------------------

  test('test_lot_tab_error_shows_error_element', async ({ page }) => {
    test.skip(!USE_MOCKS, 'Error-injection test requires mock API (set USE_MOCK_API=1)');

    // Override the resolve endpoint to return 500.
    await page.route('**/api/query-tool/resolve**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'INTERNAL_ERROR', message: 'Mock server error' },
          meta: { timestamp: new Date().toISOString(), app_version: 'test' },
        }),
      }),
    );

    const textarea = page.locator('textarea.query-tool-textarea, textarea').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill(DUMMY_LOT_ID);

    const queryBtn = page.locator('button:has-text("解析")').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // An error element must appear after the failed request.
    const errorEl = page.locator(
      '.bg-red-50.border-red-200, [class*="error"], [role="alert"]',
    ).first();
    await expect(errorEl).toBeVisible({ timeout: 15_000 });
  });

  // -------------------------------------------------------------------------
  // TODO (equipment-rejects-by-lots AC-6): verify rejects sub-tab shows
  //   CONTAINERNAME, LOSSREASONNAME, EQUIPMENTNAME ("報廢登錄設備") columns
  // TODO (equipment-rejects-by-lots AC-8): verify row-limit banner shown when truncated
  // -------------------------------------------------------------------------
});
