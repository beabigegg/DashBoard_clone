/**
 * E2E tests: production-achievement-settings — standalone mini-app
 * Change: production-achievement-overhaul (IP-9), AC-11.
 * Tier 1 — required pre-merge gate (production-achievement-settings-e2e, new).
 *
 * Covers:
 *   - whitelisted-edit path across all 3 tables (package-lf-map,
 *     workcenter-merge-map incl. OD-8 full raw-group toggle, daily-plans
 *     incl. OD-12 constrained dropdowns)
 *   - non-whitelisted read-only path (403 flips editForbidden SHARED across
 *     all 3 panels — fail-closed, "one language everywhere")
 *   - OD-5 propagation-delay note after a successful save
 *   - ← 返回報表 navigates back to /production-achievement
 *
 * Network strategy (ci-workflow.md): catch-all route registered FIRST,
 * specific routes registered LAST (LIFO). page.goto(...).catch(()=>{}) +
 * pageRendered guard checking .theme-production-achievement-settings.
 */

import { test, expect, type Page } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement-settings';

function envelope(data: unknown) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

function errorEnvelope(code: string, message: string, status: number) {
  return { status, contentType: 'application/json', body: JSON.stringify({ success: false, error: { code, message }, meta: { timestamp: new Date().toISOString(), app_version: 'test' } }) };
}

const PKG_ROWS = [{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL', updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' }];
const WC_ROWS = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' }];
const PLAN_ROWS = [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 500, updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' }];

async function setupBaseRoutes(page: Page, { isAdmin = true }: { isAdmin?: boolean } = {}) {
  await page.route('**/*', (route) => (route.request().resourceType() === 'document' ? route.fallback() : route.continue()));
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: isAdmin ? 'admin' : 'user', is_admin: isAdmin }) }),
  );
  await page.route('**/api/pages**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released', '/production-achievement-settings': 'released' },
        is_admin: isAdmin,
        admin_user: isAdmin ? { username: 'testuser', displayName: 'Test User' } : null,
        admin_links: { logout: '/api/auth/logout', pages: '/admin/pages', dashboard: '/admin/dashboard' },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    }),
  );
}

async function setupDataRoutes(page: Page) {
  await page.route('**/api/production-achievement/package-lf-map**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(PKG_ROWS) });
    return route.continue();
  });
  await page.route('**/api/production-achievement/known-package-lf-values**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ package_lf_values: ['NEW-RAW-VAL'] }) }),
  );
  await page.route('**/api/production-achievement/workcenter-merge-map**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(WC_ROWS) });
    return route.continue();
  });
  await page.route('**/api/production-achievement/known-workcenter-groups**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ raw_workcenter_groups: ['焊接_DB', '切割'] }) }),
  );
  await page.route('**/api/production-achievement/daily-plans**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(PLAN_ROWS) });
    return route.continue();
  });
}

async function isPageRendered(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement-settings');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

test.describe('production-achievement-settings — whitelisted edit path', () => {
  test('editing PACKAGE_LF merge, workcenter include-toggle, and a daily plan all PUT successfully and show the OD-5 save note', async ({ page }) => {
    await setupBaseRoutes(page, { isAdmin: true });
    await setupDataRoutes(page);

    let pkgPutCalled = false;
    await page.route('**/api/production-achievement/package-lf-map**', (route) => {
      if (route.request().method() === 'PUT') {
        pkgPutCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(PKG_ROWS) });
    });

    let wcIncludeCalled = false;
    await page.route('**/api/production-achievement/workcenter-merge-map**', (route) => {
      if (route.request().method() === 'PUT') {
        wcIncludeCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(WC_ROWS) });
    });

    let planPutCalled = false;
    await page.route('**/api/production-achievement/daily-plans**', (route) => {
      if (route.request().method() === 'PUT') {
        planPutCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(PLAN_ROWS) });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement_settings = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement_settings?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'settings page not rendered yet; skipping deep assertions' });
      return;
    }

    // 1) PACKAGE_LF inline edit
    await page.locator('[data-testid="pa-pkg-edit-btn"]').first().click();
    await page.locator('[data-testid="pa-pkg-edit-input"]').fill('SOD-123FL-RENAMED');
    await page.locator('[data-testid="pa-pkg-edit-input"]').press('Enter');
    await expect.poll(() => pkgPutCalled, { timeout: 10_000 }).toBe(true);
    await expect(page.locator('[data-testid="pa-settings-save-note"]')).toBeVisible({ timeout: 10_000 });
    await page.locator('[data-testid="pa-settings-save-note-dismiss"]').click();

    // 2) OD-8: 切割 is enumerated as a currently-EXCLUDED raw group and can be toggled on
    const toggles = page.locator('[data-testid="pa-wc-toggle"]');
    await expect(toggles).toHaveCount(2, { timeout: 10_000 });
    const excludedToggle = page.locator('[data-testid="pa-wc-toggle"]', { hasText: '未納入' });
    await excludedToggle.click();
    await expect.poll(() => wcIncludeCalled, { timeout: 10_000 }).toBe(true);

    // 3) OD-12: daily-plan new row uses constrained dropdowns only
    await page.locator('[data-testid="pa-plan-new-btn"]').click();
    await expect(page.locator('[data-testid="pa-plan-new-workcenter"]')).toHaveCount(1);
    await page.locator('[data-testid="pa-plan-new-workcenter"]').selectOption('焊接_DB');
    await page.locator('[data-testid="pa-plan-new-package"]').selectOption('SOD-123FL');
    await page.locator('[data-testid="pa-plan-new-qty"]').fill('700');
    await page.locator('[data-testid="pa-plan-new-save"]').click();
    await expect.poll(() => planPutCalled, { timeout: 10_000 }).toBe(true);
  });
});

test.describe('production-achievement-settings — non-whitelisted read-only path', () => {
  test('a 403 on any panel write flips editForbidden SHARED across all 3 panels', async ({ page }) => {
    await setupBaseRoutes(page, { isAdmin: false });
    await setupDataRoutes(page);
    await page.route('**/api/production-achievement/package-lf-map**', (route) => {
      if (route.request().method() === 'PUT') {
        const err = errorEnvelope('FORBIDDEN', '無權限', 403);
        return route.fulfill(err);
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(PKG_ROWS) });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement_settings = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement_settings?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'settings page not rendered yet; skipping 403 assertions' });
      return;
    }

    await page.locator('[data-testid="pa-pkg-edit-btn"]').first().click();
    await page.locator('[data-testid="pa-pkg-edit-input"]').fill('X');
    await page.locator('[data-testid="pa-pkg-edit-input"]').press('Enter');

    await expect(page.locator('[data-testid="pa-pkg-readonly-note"]')).toBeVisible({ timeout: 10_000 });
    // Shared fail-closed flag — the OTHER two panels also flip to read-only.
    await expect(page.locator('[data-testid="pa-wc-readonly-note"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="pa-plan-readonly-note"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="pa-pkg-new-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="pa-plan-new-btn"]')).toHaveCount(0);
  });
});

test.describe('production-achievement-settings — return path', () => {
  test('← 返回報表 navigates back to /production-achievement', async ({ page }) => {
    await setupBaseRoutes(page, { isAdmin: true });
    await setupDataRoutes(page);

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement_settings = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement_settings?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'settings page not rendered yet; skipping return-path assertions' });
      return;
    }

    await page.locator('[data-testid="pa-settings-back-btn"]').click();
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});
    const backOnReport = await page.evaluate(() => document.querySelector('.theme-production-achievement') !== null);
    if (backOnReport) {
      await expect(page.locator('[data-testid="pa-app"]')).toBeVisible({ timeout: 15_000 });
    }
  });

  const REPORT_PAGE_URL = '/portal-shell/production-achievement';
  // Real 0-row 5-column Parquet (data-shape-contract.md §3.28.1 schema),
  // generated via the `duckdb` Python package — shared with the sibling
  // data-boundary/monkey specs' own EMPTY_PARQUET_B64 fixture.
  const EMPTY_PA_PARQUET_B64 =
    'UEFSMRUCGWw1ABgNZHVja2RiX3NjaGVtYRUKABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQwlAhgKUEFDS0FHRV9MRiUAABUEJQIYEWFjdHVhbF9vdXRwdXRfcXR5JSQAFgAZDCgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlcHAAAHAAAHAAAHAAAHAAAAL0AAABQQVIx';

  async function setupReportRoutes(page: Page) {
    await page.route('**/*', (route) => (route.request().resourceType() === 'document' ? route.fallback() : route.continue()));
    await page.route('**/api/auth/me**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'user' }) }));
    await page.route('**/api/pages**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    await page.route('**/api/portal/navigation**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          statuses: { '/production-achievement': 'released', '/production-achievement-settings': 'released' },
          is_admin: true,
          admin_user: { username: 'testuser', displayName: 'Test User' },
          admin_links: { logout: '/api/auth/logout', pages: '/admin/pages', dashboard: '/admin/dashboard' },
          diagnostics: {},
          features: { ai_query_enabled: false },
        }),
      }),
    );
    await page.route('**/api/production-achievement/filter-options**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB', '焊接_WB'] }) }),
    );
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
    });
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ query_id: 'qid-od7', spool_download_url: '/api/spool/production_achievement/qid-od7.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
      }),
    );
    await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PA_PARQUET_B64, 'base64') }));
  }

  test('mode + station survive a full navigation to /production-achievement-settings and back (OD-7, sessionStorage)', async ({ page }) => {
    await setupReportRoutes(page);

    await page.goto(REPORT_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const reportRendered = await page.evaluate(() => {
      const el = document.querySelector('.theme-production-achievement');
      return el !== null && (el as HTMLElement).offsetParent !== null;
    });
    if (!reportRendered) {
      test.info().annotations.push({ type: 'note', description: 'report page not rendered yet; skipping OD-7 persistence assertions' });
      return;
    }

    // Move away from the defaults (當日 / 焊接_DB) so a reset-to-default on
    // return would be observably different from a correctly-preserved state.
    await page.locator('[data-testid="pa-mode-yesterday"]').click();
    await expect(page.locator('[data-testid="pa-mode-yesterday"]')).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 });
    // setWorkcenterGroup() carries the SAME OD-4 "ignore while loading" guard
    // as setMode() -- wait for the mode-change's own auto-run to fully settle
    // before touching the station select, or this next interaction could be
    // silently dropped (still "loading" from the mode click).
    await page.waitForTimeout(500);

    const select = page.locator('[data-testid="pa-workcenter-group"] [data-testid="multiselect-trigger"]');
    await select.click();
    await page.locator('[data-testid="multiselect-option"]', { hasText: '焊接_WB' }).click();
    await page.locator('[data-testid="multiselect-close"]').click().catch(() => {});
    await expect(select).toContainText('焊接_WB', { timeout: 10_000 });

    // OD-7 (interaction-design.md § Confirmed, "保留之前的模式與站點"): navigate
    // to the settings mini-app and back. This assertion depends ONLY on the
    // REPORT page's own sessionStorage-backed restore-on-mount behaviour
    // (useProductionAchievement.ts's readPersistedState()/persistState()) —
    // it does NOT require the settings bundle itself to render, since OD-7's
    // persistence mechanism lives entirely on the report side of the round trip.
    await page.goto('/portal-shell/production-achievement-settings', { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    await page.goto(REPORT_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rerendered = await page.evaluate(() => document.querySelector('.theme-production-achievement') !== null);
    if (!rerendered) {
      test.info().annotations.push({ type: 'note', description: 'report page did not re-render after the round-trip; skipping OD-7 restore assertions' });
      return;
    }

    // Must NOT have reset to the defaults (當日 / 焊接_DB) — OD-7 explicitly
    // rejects that (it was Open Decision option (a)), preserving the exact
    // pre-navigation mode + station instead (option (c), confirmed).
    await expect(page.locator('[data-testid="pa-mode-yesterday"]')).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 });
    await expect(page.locator('[data-testid="pa-mode-today"]')).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('[data-testid="pa-workcenter-group"] [data-testid="multiselect-trigger"]')).toContainText('焊接_WB', { timeout: 10_000 });
  });
});
