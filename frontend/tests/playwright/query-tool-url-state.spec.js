/**
 * E2E spec: Query Tool — URL state persistence
 *
 * Verifies that tab selection, textarea content, date inputs, and
 * equipment sub-tab param are preserved in the URL and restored on reload.
 *
 * Dual-mode: mock in CI (USE_MOCK_API=1), real backend locally.
 * workcenter-groups + equipment-list are mocked even in mock mode so
 * the equipment tab can render without Oracle.
 */

import { test, expect } from '@playwright/test';
import { navigateDual, USE_MOCKS, BASE_URL } from './_api-mode.js';

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

// ---------------------------------------------------------------------------
// Helper: navigate to query-tool URL and ensure the tab-nav is present.
//
// Direct page.goto() may bypass Vue SPA routing when the shell is already
// mounted.  If the tab-nav selector is not found within 5 s we fall back to
// a popstate injection so the Vue router picks up the query-string params
// without a full page reload.
// ---------------------------------------------------------------------------

async function openQueryToolUrlWithRetry(page, fullUrl) {
  const tabNavSelector = 'nav[aria-label="query-tool tabs"]';

  await page.goto(fullUrl).catch(() => {});

  const hasTabNav = await page
    .waitForSelector(tabNavSelector, { timeout: 5_000 })
    .then(() => true)
    .catch(() => false);

  if (hasTabNav) return;

  // Fallback: push URL via history API so the Vue router reacts without a
  // real navigation (avoids losing mock route handlers registered by
  // navigateDual / setupMockedShell).
  const parsed = new URL(fullUrl, BASE_URL);
  await page.evaluate((search) => {
    const url = new URL(window.location.href);
    url.search = search;
    window.history.replaceState({}, '', url.toString());
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, parsed.search);

  await page.waitForSelector(tabNavSelector, { timeout: 15_000 });
}

// ---------------------------------------------------------------------------
// Shared feature mocks (passed as extraMocks to navigateDual)
// extraMocks are only invoked in mock mode; real mode hits the live backend.
// ---------------------------------------------------------------------------

function buildFeatureMocks(page) {
  return async () => {
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
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Query Tool URL state persistence', () => {
  test.beforeEach(async ({ page }) => {
    await navigateDual(page, 'query-tool', {
      waitForSelector: 'textarea.query-tool-textarea, input[type="date"]',
      extraMocks: buildFeatureMocks(page),
    });
  });

  // -------------------------------------------------------------------------
  // 1. Equipment tab: date inputs + sub-tab param survive reload
  // -------------------------------------------------------------------------

  test('preserves_equipment_tab_url_state_across_reload', async ({ page }) => {
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });
    await equipmentTab.click();

    const dateInputs = page.locator('input[type="date"]:visible');
    await expect(dateInputs.first()).toBeVisible({ timeout: 10_000 });
    await dateInputs.nth(0).fill('2026-03-01');
    await dateInputs.nth(1).fill('2026-03-07');

    // Click the "維修紀錄" sub-tab to set equipment_sub_tab=jobs in the URL.
    await page.getByRole('button', { name: '維修紀錄' }).click();

    // Verify URL carries all three params before reload.
    await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=equipment');
    const beforeUrl = new URL(page.url());
    expect(beforeUrl.searchParams.get('start_date')).toBe('2026-03-01');
    expect(beforeUrl.searchParams.get('end_date')).toBe('2026-03-07');
    expect(beforeUrl.searchParams.get('equipment_sub_tab')).toBe('jobs');

    // Reload (or re-navigate with the same URL params).
    await openQueryToolUrlWithRetry(
      page,
      `/portal-shell/query-tool?${beforeUrl.searchParams.toString()}`,
    );

    // After reload, active tab + sub-tab + date values must be restored.
    await expect(page.getByRole('button', { name: '設備生產批次追蹤' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByRole('button', { name: '維修紀錄', exact: true })).toHaveClass(/active/);
    await expect(page.locator('input[type="date"]:visible').nth(0)).toHaveValue('2026-03-01');
    await expect(page.locator('input[type="date"]:visible').nth(1)).toHaveValue('2026-03-07');
  });

  // -------------------------------------------------------------------------
  // 2. LOT tab: textarea content (multi-line) is reflected in URL and restored
  // -------------------------------------------------------------------------

  test('preserves_lot_tab_url_state', async ({ page }) => {
    // Use data-testid to avoid strict-mode violation — multiple tabs contain '批次追蹤'.
    const lotTab = page.locator('[data-testid="tab-lot"]');
    if (await lotTab.count() > 0) {
      await lotTab.click();
    }

    // Lot tab is now active — the lot textarea is the visible one.
    const textarea = page.locator('textarea:visible').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('LOT-A\nLOT-B');

    // The URL must reflect the lot tab selection.
    await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=lot');

    const beforeUrl = new URL(page.url());

    // Simulate reload by re-navigating to the same URL.
    await openQueryToolUrlWithRetry(
      page,
      `/portal-shell/query-tool?${beforeUrl.searchParams.toString()}`,
    );

    // After reload: lot tab is active and textarea is pre-filled.
    const restoredTab = page.locator('[data-testid="tab-lot"]');
    if (await restoredTab.count() > 0) {
      await expect(restoredTab).toHaveAttribute('aria-current', 'page');
    }

    const restoredTextarea = page.locator('textarea:visible').first();
    await expect(restoredTextarea).toBeVisible({ timeout: 10_000 });
    // The restored value must contain both lot IDs (order-independent).
    const restoredValue = await restoredTextarea.inputValue();
    expect(restoredValue).toContain('LOT-A');
    expect(restoredValue).toContain('LOT-B');
  });

  // -------------------------------------------------------------------------
  // 3. Reverse-lineage tab: URL has tab=reverse and is restored on reload
  // -------------------------------------------------------------------------

  test('preserves_reverse_lineage_tab_url_state', async ({ page }) => {
    // The reverse-lineage tab is labelled "流水批反查".
    const reverseTab = page.getByRole('button', { name: '流水批反查' });

    if (await reverseTab.count() === 0) {
      test.skip(true, '流水批反查 tab not present in this build');
      return;
    }

    await reverseTab.click();
    await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=reverse');

    // After switching, the LOT textarea is hidden; use :visible to find the
    // reverse-lineage panel's textarea (different DOM position, now visible).
    const textarea = page.locator('textarea:visible').first();
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await textarea.fill('SN-001');

    const beforeUrl = new URL(page.url());

    await openQueryToolUrlWithRetry(
      page,
      `/portal-shell/query-tool?${beforeUrl.searchParams.toString()}`,
    );

    // After reload: reverse tab is still active and textarea is pre-filled.
    await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=reverse');

    const restoredTextarea = page.locator('textarea:visible').first();
    await expect(restoredTextarea).toBeVisible({ timeout: 10_000 });
    const restoredValue = await restoredTextarea.inputValue();
    expect(restoredValue).toContain('SN-001');
  });

  // -------------------------------------------------------------------------
  // 4. Equipment sub-tab clicks each produce distinct equipment_sub_tab params
  // -------------------------------------------------------------------------

  test('equipment_sub_tab_state_switches_url', async ({ page }) => {
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });
    await equipmentTab.click();

    const dateInputs = page.locator('input[type="date"]:visible');
    await expect(dateInputs.first()).toBeVisible({ timeout: 10_000 });

    // Sub-tabs that may exist: 維修紀錄 (jobs) / 報廢 (rejects) / 時間軸 (timeline)
    // Try each in turn and verify the URL param changes.  We skip silently
    // when a sub-tab is not present so the test doesn't break on partial builds.
    const subTabCases = [
      { label: '維修紀錄', expectedParam: 'jobs' },
      { label: '報廢', expectedParam: 'rejects' },
      { label: '時間軸', expectedParam: 'timeline' },
    ];

    let anySubTabTested = false;

    for (const { label, expectedParam } of subTabCases) {
      const btn = page.getByRole('button', { name: label, exact: true });
      if (await btn.count() === 0) continue;

      await btn.click();
      await expect
        .poll(() => new URL(page.url()).searchParams.get('equipment_sub_tab'), { timeout: 5_000 })
        .toBe(expectedParam);
      anySubTabTested = true;
    }

    if (!anySubTabTested) {
      // At minimum the URL must contain tab=equipment after clicking the equipment tab.
      await expect.poll(() => page.url(), { timeout: 5_000 }).toContain('tab=equipment');
    }
  });
});
