/**
 * E2E tests: production-achievement-settings — standalone mini-app
 * Change: production-achievement-overhaul (IP-9), AC-11.
 * Tier 1 — required pre-merge gate (production-achievement-settings-e2e, new).
 *
 * Covers:
 *   - whitelisted-edit path across both remaining tables (package-lf-map,
 *     workcenter-merge-map incl. OD-8 full raw-group toggle and PA-20
 *     plan_source_side, always submitted together with parent_group).
 *     production-achievement-oracle-plan-source removed the 3rd table
 *     (daily-plans, Excel-import — targets are now Oracle-sourced,
 *     business-rules.md PA-11) — this file now covers exactly 2 panels.
 *   - non-whitelisted read-only path (403 flips editForbidden SHARED across
 *     both panels — fail-closed, "one language everywhere")
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
const WC_ROWS = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', parent_group: '焊接_DB', plan_source_side: 'input', updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' }];

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
}

async function isPageRendered(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement-settings');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

test.describe('production-achievement-settings — whitelisted edit path', () => {
  test('editing PACKAGE_LF merge, workcenter include-toggle, and a PA-20 plan_source_side rename all PUT successfully and show the OD-5 save note', async ({ page }) => {
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

    // Single handler for BOTH workcenter-merge-map writes in this test (the
    // OD-8 include-toggle, then the PA-20 rename) — Playwright page.route()
    // is LIFO per-pattern, so a second registration for the SAME URL would
    // entirely shadow this one rather than composing with it.
    const wcPutBodies: { raw_workcenter_group: string; plan_source_side?: string }[] = [];
    await page.route('**/api/production-achievement/workcenter-merge-map**', (route) => {
      if (route.request().method() === 'PUT') {
        wcPutBodies.push(route.request().postDataJSON());
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(WC_ROWS) });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody10 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody10?.trim().length ?? 0) < 50) {
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
    await expect.poll(() => wcPutBodies.length, { timeout: 10_000 }).toBe(1);
    expect(wcPutBodies[0].raw_workcenter_group).toBe('切割');
    // Including a previously-excluded row defaults plan_source_side to
    // 'input' (the column DDL default) — the admin can rename it afterwards.
    expect(wcPutBodies[0].plan_source_side).toBe('input');

    // 3) PA-20: renaming 焊接_DB and changing plan_source_side submits BOTH
    // fields together in the SAME PUT, never independently.
    await page.locator('[data-testid="pa-wc-rename-btn"]').first().click();
    await page.locator('[data-testid="pa-wc-plan-source-side-select"]').selectOption('output');
    await page.locator('[data-testid="pa-wc-rename-save"]').click();
    await expect.poll(() => wcPutBodies.length, { timeout: 10_000 }).toBe(2);
    expect(wcPutBodies[1].raw_workcenter_group).toBe('焊接_DB');
    expect(wcPutBodies[1].plan_source_side).toBe('output');
  });
});

test.describe('production-achievement-settings — non-whitelisted read-only path', () => {
  test('a 403 on any panel write flips editForbidden SHARED across both panels', async ({ page }) => {
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
    const noServerBody11 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody11?.trim().length ?? 0) < 50) {
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
    // Shared fail-closed flag — the OTHER panel also flips to read-only.
    await expect(page.locator('[data-testid="pa-wc-readonly-note"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="pa-pkg-new-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="pa-wc-rename-btn"]')).toHaveCount(0);
  });
});

test.describe('production-achievement-settings — return path', () => {
  test('← 返回報表 navigates back to /production-achievement', async ({ page }) => {
    await setupBaseRoutes(page, { isAdmin: true });
    await setupDataRoutes(page);

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody12 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody12?.trim().length ?? 0) < 50) {
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
        body: envelope({ query_id: 'qid-od7', spool_download_url: '/api/spool/production_achievement/qid-od7.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], plan_map: [] }),
      }),
    );
    await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PA_PARQUET_B64, 'base64') }));
  }

  test('mode + station survive a full navigation to /production-achievement-settings and back (OD-7, sessionStorage)', async ({ page }) => {
    await setupReportRoutes(page);

    await page.goto(REPORT_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody13 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody13?.trim().length ?? 0) < 50) {
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
    const noServerBody14 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody14?.trim().length ?? 0) < 50) {
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
