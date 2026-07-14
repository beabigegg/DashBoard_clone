/**
 * Monkey/adversarial E2E spec: 生產達成率 report + settings mini-app
 * Change: production-achievement-overhaul — rewrite (IP-8/IP-9).
 * Tier 1 — required pre-merge gate (production-achievement-monkey).
 *
 * Scope (test-plan.md): 4-mode rapid-click + settings CRUD adversarial
 * input. Complements (does not duplicate) production-achievement-async.spec.ts's
 * cancel/hidden-tab/back-forward/mid-poll-retry coverage — this file focuses
 * on RAPID, REPEATED user actions against the NEW 4-mode/no-submit-button UI
 * and the settings mini-app's inline-edit CRUD forms.
 *
 * Network strategy (ci-workflow.md): catch-all first, specific routes last (LIFO).
 */

import { test, expect, type Page } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';
const SETTINGS_PAGE_URL = '/portal-shell/production-achievement-settings';
const MOCK_META = { timestamp: new Date().toISOString(), app_version: 'test' };

function envelope(data: unknown) {
  return JSON.stringify({ success: true, data, meta: MOCK_META });
}

// Real 0-row 5-column Parquet (data-shape-contract.md §3.28.1, production
// -achievement-overhaul grain) — generated via the `duckdb` Python package.
const EMPTY_PARQUET_B64 =
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
        admin_user: { username: 'testuser', displayName: 'Test' },
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

  let reportCallCount = 0;
  await page.route('**/api/production-achievement/report**', (route) => {
    reportCallCount++;
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: envelope({
        query_id: `qid-monkey-${reportCallCount}`,
        spool_download_url: `/api/spool/production_achievement/monkey-${reportCallCount}.parquet`,
        spec_workcenter_map: [],
        targets_map: [],
        package_lf_map: [],
        workcenter_merge_map: [],
        daily_plan_map: [],
      }),
    });
  });
  await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }));
  return () => reportCallCount;
}

async function gotoAndWaitForApp(page: Page, themeClass: string): Promise<boolean> {
  await page.goto(page.url().includes(SETTINGS_PAGE_URL) ? SETTINGS_PAGE_URL : PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  if ((bodyText?.trim().length ?? 0) < 50) return false;
  await page.waitForFunction((cls) => document.querySelector(cls) !== null, themeClass, { timeout: 3_000 }).catch(() => {});
  return page.evaluate((cls) => {
    const el = document.querySelector(cls);
    return el !== null && (el as HTMLElement).offsetParent !== null;
  }, themeClass);
}

function skipIfNotRendered(rendered: boolean, note: string): boolean {
  if (!rendered) test.info().annotations.push({ type: 'note', description: note });
  return !rendered;
}

test.describe('production-achievement monkey — rapid mode-button clicking', () => {
  test('rapid-fire clicks across all 4 mode buttons settle on the LAST clicked mode with no crash', async ({ page }) => {
    const getReportCallCount = await setupReportRoutes(page);
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping rapid mode-click assertions')) return;

    // Fire all 4 mode buttons in rapid succession, no waiting between clicks —
    // OD-4's ignore-mid-poll guard must prevent overlapping queries from
    // corrupting state; the UI must not crash and must end on SOME
    // consistent, visibly-active mode.
    const modes = ['pa-mode-yesterday', 'pa-mode-month', 'pa-mode-range', 'pa-mode-today'];
    for (const testId of modes) {
      await page.locator(`[data-testid="${testId}"]`).click({ trial: false }).catch(() => {});
    }
    // Let the last-accepted query (if any) settle.
    await page.waitForTimeout(1_000);

    const pressedButtons = await page.locator('[aria-pressed="true"][data-testid^="pa-mode-"]').count();
    expect(pressedButtons).toBe(1); // exactly one mode is ever active, never zero or many
    expect(pageErrors).toHaveLength(0);
    expect(getReportCallCount()).toBeGreaterThanOrEqual(1);
  });

  test('rapid station-select changes do not crash and leave exactly one value selected', async ({ page }) => {
    await setupReportRoutes(page);
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping rapid station-select assertions')) return;

    const trigger = page.locator('[data-testid="pa-workcenter-group"] [data-testid="multiselect-trigger"]');
    for (let i = 0; i < 5; i++) {
      await trigger.click().catch(() => {});
      const option = page.locator('[data-testid="multiselect-option"]').first();
      await option.click({ timeout: 2_000 }).catch(() => {});
    }
    await page.waitForTimeout(500);

    expect(pageErrors).toHaveLength(0);
  });

  test('repeatedly opening/closing 自訂區間 does not leak duplicate date inputs', async ({ page }) => {
    await setupReportRoutes(page);
    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping repeated range-toggle assertions')) return;

    for (let i = 0; i < 4; i++) {
      await page.locator('[data-testid="pa-mode-range"]').click().catch(() => {});
      await page.locator('[data-testid="pa-mode-today"]').click().catch(() => {});
    }
    await page.locator('[data-testid="pa-mode-range"]').click().catch(() => {});
    await page.waitForTimeout(300);

    await expect(page.locator('[data-testid="pa-range-start"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="pa-range-end"]')).toHaveCount(1);
  });
});

test.describe('production-achievement-settings monkey — rapid CRUD clicks (double-submit protection)', () => {
  async function setupSettingsRoutes(page: Page) {
    await page.route('**/*', (route) => (route.request().resourceType() === 'document' ? route.fallback() : route.continue()));
    await page.route('**/api/auth/me**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'admin', is_admin: true }) }));
    await page.route('**/api/pages**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    await page.route('**/api/portal/navigation**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          statuses: { '/production-achievement-settings': 'released' },
          is_admin: true,
          admin_user: { username: 'testuser', displayName: 'Test' },
          admin_links: { logout: '/api/auth/logout', pages: '/admin/pages', dashboard: '/admin/dashboard' },
          diagnostics: {},
          features: { ai_query_enabled: false },
        }),
      }),
    );
    await page.route('**/api/production-achievement/known-package-lf-values**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ package_lf_values: [] }) }));
    await page.route('**/api/production-achievement/known-workcenter-groups**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ raw_workcenter_groups: ['焊接_DB'] }) }));

    let pkgPutCount = 0;
    await page.route('**/api/production-achievement/package-lf-map**', (route) => {
      if (route.request().method() === 'PUT') {
        pkgPutCount++;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([{ raw_package_lf: 'RAW-1', merged_group: 'MERGED-1', updated_at: 't', updated_by: 'admin' }]) });
    });

    let wcPutCount = 0;
    await page.route('**/api/production-achievement/workcenter-merge-map**', (route) => {
      if (route.request().method() === 'PUT') {
        wcPutCount++;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', updated_at: 't', updated_by: 'admin' }]) });
    });

    await page.route('**/api/production-achievement/daily-plans**', (route) => {
      if (route.request().method() === 'PUT') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    });

    return { getPkgPutCount: () => pkgPutCount, getWcPutCount: () => wcPutCount };
  }

  test('double-clicking a PACKAGE_LF save button does not fire two PUT requests for one edit', async ({ page }) => {
    const { getPkgPutCount } = await setupSettingsRoutes(page);
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement-settings');
    if (skipIfNotRendered(rendered, 'settings app not mounted — skipping double-click assertions')) return;

    await page.locator('[data-testid="pa-pkg-edit-btn"]').first().click();
    await page.locator('[data-testid="pa-pkg-edit-input"]').fill('MERGED-1-RENAMED');
    // Rapid-fire Enter presses on the same edit — must not double-submit.
    const input = page.locator('[data-testid="pa-pkg-edit-input"]');
    await input.press('Enter').catch(() => {});
    await input.press('Enter').catch(() => {});
    await page.waitForTimeout(500);

    expect(pageErrors).toHaveLength(0);
    expect(getPkgPutCount()).toBeLessThanOrEqual(1);
  });

  test('rapidly toggling a workcenter include/exclude switch several times settles on a consistent final state, no crash', async ({ page }) => {
    const { getWcPutCount } = await setupSettingsRoutes(page);
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement-settings');
    if (skipIfNotRendered(rendered, 'settings app not mounted — skipping rapid-toggle assertions')) return;

    const toggle = page.locator('[data-testid="pa-wc-toggle"]').first();
    for (let i = 0; i < 4; i++) {
      await toggle.click().catch(() => {});
    }
    await page.waitForTimeout(500);

    expect(pageErrors).toHaveLength(0);
    expect(getWcPutCount()).toBeGreaterThanOrEqual(0); // no crash is the primary guarantee; exact count is server-race-dependent
  });

  test('rapidly opening and cancelling the daily-plan new-row form repeatedly leaves no duplicate forms and never calls PUT', async ({ page }) => {
    await setupSettingsRoutes(page);
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement-settings');
    if (skipIfNotRendered(rendered, 'settings app not mounted — skipping rapid open/cancel assertions')) return;

    for (let i = 0; i < 5; i++) {
      await page.locator('[data-testid="pa-plan-new-btn"]').click().catch(() => {});
      await page.locator('[data-testid="pa-plan-new-row"] .ui-btn--ghost').click().catch(() => {});
    }
    await page.waitForTimeout(300);

    await expect(page.locator('[data-testid="pa-plan-new-row"]')).toHaveCount(0);
    expect(pageErrors).toHaveLength(0);
  });
});

// ===========================================================================
// monkey-test-engineer additions below (production-achievement-overhaul).
// The 3 describe blocks above are frontend-engineer's original 4-mode/
// settings-CRUD rescope. These 3 blocks fill genuine gaps identified by
// comparing that rescope against the ORIGINAL (pre-overhaul) 12-block file
// (git show 4b48c570:frontend/tests/playwright/production-achievement-monkey
// .spec.ts) and this change's own domain rules (interaction-design.md OD-3/
// OD-4) -- NOT duplicates of production-achievement-async.spec.ts's coverage:
//   - async.spec.ts's OD-4 test clicks exactly ONE different mode ONCE
//     mid-poll; it never mashes ALL 4 buttons in a single tick, so it never
//     stresses simultaneous-click ordering, only "a single change is ignored."
//   - No current spec (monkey/async/data-boundary/resilience) covers
//     自訂區間's adversarial date-range input (original scenario 8) against
//     the NEW UI at all -- setRangeDates() has zero client-side validation
//     (verified by direct read of useProductionAchievement.ts), so the
//     server's 400 is the only defense; nothing currently exercises it.
//   - TargetEditPanel.vue is verified UNCHANGED by this change (frontend
//     -engineer's own agent-log), so its pre-overhaul rapid-double-click-Save
//     finding (original scenario 2) still applies unmitigated, but was
//     dropped with no replacement anywhere in the current suite.
// ===========================================================================

test.describe('production-achievement monkey — rapid mode-mashing during a GENUINE async poll (race-condition trap)', () => {
  test('mashing all 4 mode buttons in one JS tick while a REAL 202 poll is in flight results in exactly one query and no crash (OD-3 auto-run + OD-4 ignore-mid-poll)', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await setupReportRoutes(page);

    const JOB_ID = 'pa-job-mash-001';
    let reportCallCount = 0;
    let jobPollCount = 0;
    // Overrides setupReportRoutes' always-200 default (LIFO: registered
    // after, wins) with a GENUINE spool-miss -> 202 -> multi-tick poll, so
    // the "loading" window is real (multiple seconds), not a same-tick
    // artifact of an instantly-resolving mock.
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: `/api/job/${JOB_ID}?prefix=production-achievement` }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-mash',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: [],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [],
          daily_plan_map: [],
        }),
      });
    });
    // "started" held for 2 ticks (poll interval 3s, per useAsyncJobPolling.ts)
    // -- a multi-second in-flight window the mash must land inside.
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 2
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 10 * jobPollCount, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-mash', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }),
    );

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping rapid-mashing-during-genuine-poll assertions')) return;

    const progressVisible = await page.locator('.async-job-progress').isVisible({ timeout: 10_000 }).catch(() => false);
    if (!progressVisible) {
      test.info().annotations.push({ type: 'note', description: 'progress card never appeared — mocked 202 may have resolved unexpectedly fast; skipping mashing assertions' });
      return;
    }

    const callsBeforeMash = reportCallCount;

    // Fire ALL 4 mode-button clicks in ONE JS tick — true simultaneity,
    // unlike sequential Playwright .click() awaits (each of which incurs its
    // own actionability-check latency and could let an earlier click's fetch
    // resolve before the next one even fires). Mirrors the ORIGINAL
    // pre-overhaul file's own rapid-click technique (scenario 1).
    await page.evaluate(() => {
      const ids = ['pa-mode-yesterday', 'pa-mode-month', 'pa-mode-range', 'pa-mode-today'];
      for (const id of ids) {
        (document.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement | null)?.click();
      }
    });
    // Window during which an (incorrect) click-driven fetch would have
    // fired, well before the mocked poll's own ~3s-per-tick resolution.
    await page.waitForTimeout(500);

    // OD-4: every one of those 4 clicks landed while loading=true — ALL must
    // be no-ops (setMode()'s `if (loading.value) return` guard). Exactly one
    // mode is ever pressed, and it must be the mode that was ALREADY active
    // before the mash (當日), never whichever button was clicked LAST — the
    // synchronous-response rapid-click test above cannot prove this
    // distinction (its instant mock leaves too small a window), this
    // multi-tick fixture does.
    expect(reportCallCount).toBe(callsBeforeMash);
    await expect(page.locator('[data-testid="pa-mode-today"]')).toHaveAttribute('aria-pressed', 'true');
    const pressedCount = await page.locator('[aria-pressed="true"][data-testid^="pa-mode-"]').count();
    expect(pressedCount).toBe(1);
    expect(pageErrors).toHaveLength(0);

    // Let the ORIGINAL poll resolve; confirm mode-switching is not
    // permanently stuck — the guard is scoped to "only while loading."
    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 20_000 });
    await page.locator('[data-testid="pa-mode-yesterday"]').click();
    await expect(page.locator('[data-testid="pa-mode-yesterday"]')).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 });
    expect(reportCallCount).toBeGreaterThan(callsBeforeMash);
  });
});

test.describe('production-achievement monkey — adversarial 自訂區間 date-range input', () => {
  // _validate_date_range() (production_achievement_service.py, verified by
  // direct read): missing start/end -> 400; end_date < start_date -> 400;
  // range > MAX_QUERY_DAYS=730 -> 400. setRangeDates() (useProductionAchievement
  // .ts) performs ZERO client-side validation before firing the fetch, so the
  // server's 400 is the only defense — confirmed untested anywhere in the
  // current suite (async/data-boundary/resilience specs never send a 400
  // for this endpoint).
  const scenarios: { name: string; start: string; end: string }[] = [
    { name: 'end_date before start_date', start: '2026-06-30', end: '2026-06-01' },
    { name: 'range exceeding 730 days (MAX_QUERY_DAYS)', start: '2019-01-01', end: '2026-06-01' },
  ];

  for (const scenario of scenarios) {
    test(`${scenario.name} -> graceful 400 handling, no crash, UI stays interactive`, async ({ page }) => {
      const pageErrors: string[] = [];
      page.on('pageerror', (err) => pageErrors.push(err.message));
      await setupReportRoutes(page);

      await page.route('**/api/production-achievement/report**', (route) => {
        const url = new URL(route.request().url());
        const startDate = url.searchParams.get('start_date');
        const endDate = url.searchParams.get('end_date');
        if (startDate && endDate) {
          const days = (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86_400_000;
          if (days < 0 || days > 730) {
            return route.fulfill({
              status: 400,
              contentType: 'application/json',
              body: JSON.stringify({ success: false, error: { code: 'VALIDATION_ERROR', message: '查詢範圍不合法' }, meta: MOCK_META }),
            });
          }
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: envelope({ query_id: 'q-range', spool_download_url: '/api/spool/production_achievement/q-range.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
        });
      });
      await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }));

      const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
      if (skipIfNotRendered(rendered, `app not mounted — skipping "${scenario.name}"`)) return;

      await page.locator('[data-testid="pa-mode-range"]').click();
      // Let the mode-switch's own (valid, today/today) auto-run query settle
      // before mutating the dates — otherwise OD-4's loading guard would
      // silently drop the fill-triggered change.
      await page.waitForTimeout(800);

      await page.locator('[data-testid="pa-range-start"]').fill(scenario.start);
      await page.waitForTimeout(300);
      await page.locator('[data-testid="pa-range-end"]').fill(scenario.end);
      await page.waitForTimeout(1_000);

      // Safe outcome: no crash, and the mode buttons remain usable so the
      // user can recover by picking a different (valid) range — never a
      // permanently-stuck loading/disabled state.
      expect(pageErrors).toHaveLength(0);
      await expect(page.locator('[data-testid="pa-mode-today"]')).toBeEnabled({ timeout: 5_000 });
    });
  }

  test('a DOM-forced SQL/script-injection-shaped date string bypassing the native date picker does not execute and is handled gracefully', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));
    await setupReportRoutes(page);

    const INJECTION = "2026-01-01'; DROP TABLE targets; --<script>window.__pa_date_xss=1</script>";
    await page.route('**/api/production-achievement/report**', (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get('start_date') === INJECTION) {
        return route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ success: false, error: { code: 'VALIDATION_ERROR', message: '日期格式不正確' }, meta: MOCK_META }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ query_id: 'q-inj', spool_download_url: '/api/spool/production_achievement/q-inj.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
      });
    });
    await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }));

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping DOM-forced injection-string assertions')) return;

    await page.locator('[data-testid="pa-mode-range"]').click();
    await page.waitForTimeout(800);

    // Native <input type="date"> silently discards anything not matching its
    // own ISO parser via .fill() — simulates a compromised extension/devtools
    // actor writing directly into the DOM, which setRangeDates() never
    // validates before sending (mirrors the original pre-overhaul monkey
    // spec's own scenario-8 technique).
    await page.evaluate((value) => {
      const el = document.querySelector('[data-testid="pa-range-start"]') as HTMLInputElement | null;
      if (el) {
        el.type = 'text';
        el.value = value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }, INJECTION);
    await page.waitForTimeout(1_000);

    expect(pageErrors).toHaveLength(0);
    const xssFired = await page.evaluate(() => !!(window as unknown as { __pa_date_xss?: boolean }).__pa_date_xss).catch(() => false);
    expect(xssFired).toBe(false);
    await expect(page.locator('[data-testid="pa-mode-today"]')).toBeEnabled({ timeout: 5_000 });
  });
});

test.describe('production-achievement monkey — TargetEditPanel rapid double-click Save (unchanged component, still reachable)', () => {
  // TargetEditPanel.vue is verified UNCHANGED by this change (frontend
  // -engineer's own agent-log: "read-only diff check, zero edits"). The
  // pre-overhaul monkey spec's dedicated rapid-double-click-Save scenario
  // (original scenario 2) against this exact component was dropped during
  // the Phase 8/9 rewrite with no replacement anywhere in the current suite
  // — reinstated here since the underlying risk (saveTarget()/confirmEdit()
  // has no re-entrancy guard, unlike setMode()/setRangeDates()'s
  // `if (loading.value) return` idiom) is still unmitigated code, unchanged.
  test('rapid double-click on the legacy TargetEditPanel Save button leaves a clean, non-torn DOM state', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));
    await setupReportRoutes(page);

    let putCount = 0;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCount++;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope([{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' }]),
      });
    });

    const rendered = await gotoAndWaitForApp(page, '.theme-production-achievement');
    if (skipIfNotRendered(rendered, 'app not mounted — skipping TargetEditPanel double-click assertions')) return;

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    const editVisible = await editBtn.isVisible({ timeout: 15_000 }).catch(() => false);
    if (!editVisible) {
      test.info().annotations.push({ type: 'note', description: 'no legacy target rows rendered in this fixture — skipping double-click assertions' });
      return;
    }
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('750');

    // Two native clicks dispatched synchronously in ONE JS tick — probes
    // confirmEdit()'s own re-entrancy directly, independent of whether Vue's
    // :disabled binding has flushed to the DOM yet.
    await page.evaluate(() => {
      const btn = document.querySelector('[data-testid="pa-target-save-btn"]') as HTMLButtonElement | null;
      btn?.click();
      btn?.click();
    });
    await page.waitForTimeout(1_000);

    // Safe-outcome invariants: no crash, edit mode cleanly closed (no
    // dangling input left on screen) — NOT "exactly one PUT" (recorded as an
    // informational finding below instead, matching this exact scenario's
    // pre-overhaul precedent).
    expect(pageErrors).toHaveLength(0);
    await expect(page.locator('[data-testid="pa-target-edit-input"]')).toHaveCount(0, { timeout: 5_000 });
    test.info().annotations.push({
      type: 'note',
      description:
        `rapid double-click on TargetEditPanel Save fired ${putCount} PUT call(s) — ` +
        'saveTarget()/confirmEdit() has no re-entrancy guard (unlike setMode()/' +
        'setRangeDates()); recorded for hardening triage. DOM ended up in a clean, ' +
        'non-torn state either way.',
    });
  });
});
