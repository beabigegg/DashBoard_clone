/**
 * E2E test: "/" home dashboard landing page
 *
 * Scenarios covered:
 *   - After login, the user lands on bare "/" (not auto-redirected to
 *     /wip-overview or any other feature page)
 *   - The dashboard-home app actually renders (WIP / Hold / Equipment
 *     sections visible), not the old ShellHomeView placeholder
 *
 * This is the one piece of genuinely new behavioral coverage this feature
 * needs — no other spec asserted anything about bare "/" content before
 * this change (it always redirected away before anything could be asserted).
 *
 * Network strategy: all API calls mocked. See _auth.js's loginViaUI/waitForIdleUi.
 */

import { test, expect, type Page } from '@playwright/test';
import { loginViaUI, waitForIdleUi } from './_auth.js';

// ---------------------------------------------------------------------------
// Mock fixtures
// ---------------------------------------------------------------------------

const MOCK_WIP_SUMMARY = {
  success: true,
  data: {
    totalLots: 9632,
    totalQtyPcs: 919765783,
    byWipStatus: {
      run: { lots: 964, qtyPcs: 89936562 },
      queue: { lots: 8541, qtyPcs: 823373811 },
      hold: { lots: 127, qtyPcs: 6455410 },
      qualityHold: { lots: 67, qtyPcs: 2319717 },
      nonQualityHold: { lots: 60, qtyPcs: 4135693 },
    },
    dataUpdateDate: '2026-07-21',
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_WIP_HOLD = {
  success: true,
  data: {
    items: [
      { reason: 'YieldLimit', holdType: 'quality', lots: 27, qty: 1016586 },
      { reason: '需綁屍數(PD)', holdType: 'non-quality', lots: 21, qty: 1409041 },
    ],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_EQUIPMENT_SUMMARY = {
  success: true,
  data: {
    total_count: 973,
    by_status: { PRD: 583, SBY: 136, UDT: 25, SDT: 61, EGT: 2, NST: 166, OTHER: 0 },
    ou_pct: 72.2,
    availability_pct: 74.1,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_EQUIPMENT_LIST = {
  success: true,
  data: [
    { RESOURCEID: 'R-001', WORKCENTER_GROUP: '點測', WORKCENTER_GROUP_SEQ: 1, EQUIPMENTASSETSSTATUS: 'PRD' },
    { RESOURCEID: 'R-002', WORKCENTER_GROUP: '切割', WORKCENTER_GROUP_SEQ: 2, EQUIPMENTASSETSSTATUS: 'PRD' },
  ],
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

async function mockDashboardApis(page: Page): Promise<void> {
  await page.route('**/api/wip/overview/summary**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_WIP_SUMMARY) })
  );
  await page.route('**/api/wip/overview/hold**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_WIP_HOLD) })
  );
  await page.route('**/api/resource/status/summary**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EQUIPMENT_SUMMARY) })
  );
  await page.route('**/api/resource/status?**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_EQUIPMENT_LIST) })
  );
  await page.route('**/health**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'healthy',
        cache: { updated_at: new Date().toISOString() },
        equipment_status_cache: { updated_at: new Date().toISOString() },
      }),
    })
  );
}

test('landing on "/" after login renders the dashboard-home app, not a redirect to another page', async ({ page }) => {
  await mockDashboardApis(page);
  await loginViaUI(page);

  await expect(page).toHaveURL(/\/portal-shell\/?(\?.*)?$/);

  await expect(page.locator('[data-testid="dashboard-home-app"]')).toBeVisible({ timeout: 15_000 });
  await waitForIdleUi(page).catch(() => {});

  await expect(page.locator('[data-testid="dashboard-wip-section"]')).toBeVisible();
  await expect(page.locator('[data-testid="dashboard-hold-section"]')).toBeVisible();
  await expect(page.locator('[data-testid="dashboard-equipment-section"]')).toBeVisible();
});

test('dashboard-home WIP section shows totals from /api/wip/overview/summary', async ({ page }) => {
  await mockDashboardApis(page);
  await loginViaUI(page);

  const wipSection = page.locator('[data-testid="dashboard-wip-section"]');
  await expect(wipSection).toBeVisible({ timeout: 15_000 });
  await expect(wipSection).toContainText('TOTAL LOTS');
});

test('direct navigation to "/" without login redirects to the login page', async ({ page }) => {
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ success: false }) })
  );

  await page.goto('/portal-shell/');
  await page.waitForURL((url) => url.pathname.includes('/login'), { timeout: 15_000 });
  expect(page.url()).toContain('/login');
});
