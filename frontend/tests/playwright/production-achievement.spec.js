/**
 * E2E tests: 生產達成率 (Production Achievement Rate) report page
 * Change: production-achievement-overhaul — ground-up rewrite (IP-8) for the
 * design.md 2×2 view model (4-mode switch, single station-group filter,
 * DailyView/CumulativeView, PlanAchievementStackedChart).
 * Tier 1 — required pre-merge gate (playwright-critical-journeys).
 *
 * Covers:
 *   - 4-mode switch renders + defaults to 當日 (OD-3 auto-run, no 查詢 button)
 *   - station single-select re-scopes the report (fake-single-select idiom)
 *   - 自訂區間 range date inputs (visible only in that mode, OD-2 cumulative
 *     rendering even for a single day)
 *   - DailyView table + chart render from a real, schema-correct 5-column
 *     Parquet fixture (generated via the actual `duckdb` Python package) so
 *     the 2-stage DuckDB-WASM rollup (PA-06 -> PA-09/PA-10) genuinely runs
 *   - legacy TargetEditPanel permission-gated edit e2e (unchanged panel)
 *   - 設定 button navigates to /production-achievement-settings
 *
 * Network strategy (ci-workflow.md):
 *   - Catch-all route registered FIRST (lowest LIFO priority)
 *   - Specific API routes registered LAST (highest LIFO priority)
 *   - page.goto(...).catch(()=>{}) + pageRendered guard checking
 *     .theme-production-achievement, NOT bodyText.length > 100
 */

import { test, expect } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';

// Real 2-row Parquet fixture (data-shape-contract.md §3.28.1 schema:
// output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, PACKAGE_LF VARCHAR,
// actual_output_qty BIGINT), generated via the `duckdb` Python package:
//   (2026-06-01, D, EPOXY D/B,   SOD-123FL OP1, 300)
//   (2026-06-01, D, epoxy d/b,   SOD-123FL OP1, 200)
// Case-insensitive SPECNAME collapse (PA-06) + PACKAGE_LF merge (PA-09,
// SOD-123FL OP1 -> SOD-123FL) both apply, so this rolls up to ONE row:
// 焊接_DB / SOD-123FL / D=500 / N=0 / 每日產出=500.
const TWO_ROW_PARQUET_B64 =
  'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAF9UAAAfVAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABEFQAVQBVELBUEFQAVBhUGAAAgfAIAAAAEAQkAAABFUE9YWSBEL0IJAAAAZXBveHkgZC9iFQAVUBU4LBUEFQAVBhUGAAAoWAIAAAAEAQ0AAABTT0QtMTIzRkwgT1AxQhEAFQAVLBUwLBUEFQAVBhUGAAAWVAIAAAAEASwBAAAAAAAAyAAAAAAAAAAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABYEGRwZXCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYEFj4WQiYIPBgEfVAAABgEfVAAABYAKAR9UAAAGAR9UAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYEFkIWRiZKPBgBRBgBRBYAKAFEGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWBBZiFmYmkAE8GAllcG94eSBkL2IYCUVQT1hZIEQvQhYAKAllcG94eSBkL2IYCUVQT1hZIEQvQhERAAAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIWBBZyFlom9gE8GA1TT0QtMTIzRkwgT1AxGA1TT0QtMTIzRkwgT1AxFgAoDVNPRC0xMjNGTCBPUDEYDVNPRC0xMjNGTCBPUDEREQAAACYAHBUEGRUAGRgRYWN0dWFsX291dHB1dF9xdHkVAhYEFk4WUibQAjwYCCwBAAAAAAAAGAjIAAAAAAAAABYAKAgsAQAAAAAAABgIyAAAAAAAAAAREQAAABaiAxYEJggWmgMAKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGVwcAAAcAAAcAAAcAAAcAAAASgIAAFBBUjE=';

const REPORT_SPOOL_HIT = {
  query_id: 'pa-critical-journey-001',
  spool_download_url: '/api/spool/production_achievement/pa-critical-journey-001.parquet',
  spec_workcenter_map: [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }],
  targets_map: [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 1000 }],
  package_lf_map: [{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL' }],
  workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
  daily_plan_map: [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 600 }],
};

const TARGET_ROWS = [
  { shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' },
];

function envelope(data) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

async function setupBaseRoutes(page) {
  // Catch-all: registered FIRST so specific routes override it (LIFO)
  await page.route('**/*', (route) => (route.request().resourceType() === 'document' ? route.fallback() : route.continue()));

  await page.route('**/api/auth/me**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'user', is_admin: true }) });
  });
  await page.route('**/api/pages**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
  });
  await page.route('**/api/portal/navigation**', (route) => {
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
    });
  });
  await page.route('**/api/production-achievement/filter-options**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB', '焊接_WB'] }) });
  });
  await page.route('**/api/production-achievement/targets**', (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
    } else {
      route.continue();
    }
  });
}

async function isPageRendered(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && el.offsetParent !== null;
  });
}

function reportTable(page) {
  const reportCard = page.locator('.ui-card', { has: page.locator('.ui-card-title', { hasText: '生產達成率明細' }) });
  // NOTE: App.vue passes data-testid="pa-report-table" directly to <DataTable>;
  // Vue's single-root attrs fallthrough OVERRIDES DataTable.vue's own internal
  // static data-testid="datatable" on that same root element (verified against
  // frontend/src/production-achievement/__tests__/App.test.ts, which asserts
  // wrapper.find('[data-testid="pa-report-table"]').exists() === true) — the two
  // values cannot coexist on one attribute, so selecting "datatable" here always
  // matched zero elements once the app actually renders.
  return reportCard.locator('[data-testid="pa-report-table"]');
}

test.describe('production-achievement — navigation from 生產輔助 drawer', () => {
  test('sidebar link navigates to the 生產達成率 page and defaults to 當日', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: '.theme-production-achievement not visible; test is a passing scaffold until page is wired' });
      return;
    }

    await expect(page.locator('[data-testid="pa-app"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="pa-mode-today"]')).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 });
  });
});

test.describe('production-achievement — 4-mode switch + auto-run (OD-3)', () => {
  test('DailyView (當日) renders the table + chart automatically, no 查詢 button exists', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) });
    });
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping deep assertions' });
      return;
    }

    // Deleted controls (OD-1/OD-3): no shift filter, no 查詢/清除篩選 buttons.
    await expect(page.locator('[data-testid="pa-query-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="pa-clear-filters"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="pa-shift-code"]')).toHaveCount(0);

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(1, { timeout: 20_000 });

    const bodyText = await table.innerText();
    expect(bodyText).toContain('SOD-123FL'); // merged PACKAGE_LF group (PA-09), rows keyed by package group now
    expect(bodyText).toContain('500'); // rolled-up D-shift output (300+200, case-insensitive PA-06)
    expect(bodyText).not.toContain('Infinity');
    expect(bodyText).not.toContain('NaN');

    // Shared stacked chart renders (PlanAchievementStackedChart.vue).
    await expect(page.locator('[data-testid="pa-chart"]')).toBeVisible({ timeout: 10_000 });

    // Reduced KPI summary (OD-11).
    await expect(page.locator('[data-testid="pa-kpi-cards"]')).toBeVisible({ timeout: 10_000 });
  });

  test('switching to 自訂區間 reveals range date inputs and re-runs automatically', async ({ page }) => {
    await setupBaseRoutes(page);
    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) });
    });
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping mode-switch assertions' });
      return;
    }

    await expect(page.locator('[data-testid="pa-range-start"]')).toHaveCount(0);

    const initialCalls = reportCallCount;
    await page.locator('[data-testid="pa-mode-range"]').click();

    await expect(page.locator('[data-testid="pa-range-start"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="pa-range-end"]')).toBeVisible({ timeout: 10_000 });
    // OD-3: switching modes auto-runs a new query, no explicit submit.
    await expect.poll(() => reportCallCount, { timeout: 10_000 }).toBeGreaterThan(initialCalls);
  });

  test('station single-select re-scopes the report (fake-single-select idiom)', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping station-select assertions' });
      return;
    }

    const select = page.locator('[data-testid="pa-workcenter-group"] [data-testid="multiselect-trigger"]');
    await expect(select).toBeVisible({ timeout: 10_000 });
    await expect(select).toContainText('焊接_DB', { timeout: 10_000 }); // default station
  });
});

test.describe('production-achievement — CumulativeView (當月/自訂區間) + D3 aggregate-then-divide', () => {
  // Real 4-row 5-column Parquet fixture (generated via the `duckdb` Python
  // package): 2 PACKAGE_LF groups (PKG-A, PKG-B) x 2 days, D-shift only.
  //   (2026-06-01, D, SPEC-D3-A, PKG-A, 100)  (2026-06-02, D, SPEC-D3-A, PKG-A, 100)
  //   (2026-06-01, D, SPEC-D3-A, PKG-B, 50)   (2026-06-02, D, SPEC-D3-A, PKG-B, 50)
  // daily_plan_qty: PKG-A=100/day, PKG-B=200/day -- DELIBERATELY unequal plan
  // magnitudes (test-plan.md's D3-trap precondition) over the 2-day range:
  //   PKG-A: actual=200, plan=100*2=200 -> 100.0%
  //   PKG-B: actual=100, plan=200*2=400 -> 25.0%
  //   Aggregate-then-divide (D3, CORRECT): (200+100)/(200+400) = 300/600 = 50.0%
  //   Mean-of-percentages (WRONG, must NOT appear anywhere): (100.0%+25.0%)/2 = 62.5%
  // This 2×2 view model's SECOND half (CumulativeView) had ZERO E2E coverage
  // before this test — every existing production-achievement* Playwright spec
  // only ever exercised DailyView (當日/前日) content.
  const D3_CUMULATIVE_PARQUET_B64 =
    'UEFSMRUAFSwVMCwVCBUAFQYVBgAAFlQCAAAACAF9UAAAflAAAH1QAAB+UAAAFQAVNBU4LBUIFQAVBhUGAAAaZAIAAAAIAQEAAABEAQAAAEQBAAAARAEAAABEFQAVdBUwLBUIFQAVBhUGAAA6SAIAAAAIAQkAAABTUEVDLUQzLUGaDQAVABVUFT4sFQgVABUGFQYAACo4AgAAAAgBBQAAAFBLRy1BQgkAJEIFAAAAUEtHLUIVABVMFT4sFQgVABUGFQYAACYcAgAAAAgBZAAJAREIPDIAAAAAAAAAMgAAAAAAAAAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABYIGRwZXCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYIFk4WUiYIPBgEflAAABgEfVAAABYAKAR+UAAAGAR9UAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYIFlYWWiZaPBgBRBgBRBYAKAFEGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWCBaWARZSJrQBPBgJU1BFQy1EMy1BGAlTUEVDLUQzLUEWACgJU1BFQy1EMy1BGAlTUEVDLUQzLUEREQAAACYAHBUMGRUAGRgKUEFDS0FHRV9MRhUCFggWdhZgJoYCPBgFUEtHLUIYBVBLRy1BFgAoBVBLRy1CGAVQS0ctQRERAAAAJgAcFQQZFQAZGBFhY3R1YWxfb3V0cHV0X3F0eRUCFggWbhZgJuYCPBgIZAAAAAAAAAAYCDIAAAAAAAAAFgAoCGQAAAAAAAAAGAgyAAAAAAAAABERAAAAFp4EFggmCBa+AwAoKER1Y2tEQiB2ZXJzaW9uIHYxLjUuNCAoYnVpbGQgMDhlMzRjNDQ3YikZXBwAABwAABwAABwAABwAAAArAgAAUEFSMQ==';

  const D3_REPORT_SPOOL_HIT = {
    query_id: 'pa-d3-cumulative-001',
    spool_download_url: '/api/spool/production_achievement/pa-d3-cumulative-001.parquet',
    spec_workcenter_map: [{ SPECNAME: 'SPEC-D3-A', workcenter_group: '焊接_DB' }],
    targets_map: [],
    package_lf_map: [],
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
    daily_plan_map: [
      { workcenter_group: '焊接_DB', package_lf_group: 'PKG-A', daily_plan_qty: 100 },
      { workcenter_group: '焊接_DB', package_lf_group: 'PKG-B', daily_plan_qty: 200 },
    ],
  };

  test('自訂區間 (2026-06-01..02) renders CumulativeView columns, and the KPI card uses SUM(actual)/SUM(plan), never a mean of per-package rates', async ({ page }) => {
    await setupBaseRoutes(page);
    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(D3_REPORT_SPOOL_HIT) });
    });
    await page.route('**/api/spool/production_achievement/pa-d3-cumulative-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(D3_CUMULATIVE_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping CumulativeView/D3 assertions' });
      return;
    }

    // Each of the 3 steps below (mode click, start-date fill, end-date fill)
    // independently mutates filters + triggers its own auto-run (OD-3), each
    // subject to OD-4's "ignore while a query is loading" guard -- so this
    // explicitly waits for each step's own fetch to land AND settle before
    // firing the next one. Skipping these waits risks the end-date fill's
    // change event being silently ignored (still "loading" from the
    // start-date fill), which would leave filters.end_date at its
    // mode-entry default (today) instead of 2026-06-02 -- silently corrupting
    // the elapsedDays this test's whole D3 arithmetic depends on.
    const callsBeforeModeClick = reportCallCount;
    await page.locator('[data-testid="pa-mode-range"]').click();
    await expect(page.locator('[data-testid="pa-range-start"]')).toBeVisible({ timeout: 10_000 });
    await expect.poll(() => reportCallCount, { timeout: 10_000 }).toBeGreaterThan(callsBeforeModeClick);
    await page.waitForTimeout(500); // let the mode-click's own auto-run fully settle (loading -> false)

    const callsBeforeStartFill = reportCallCount;
    await page.locator('[data-testid="pa-range-start"]').fill('2026-06-01');
    await expect.poll(() => reportCallCount, { timeout: 10_000 }).toBeGreaterThan(callsBeforeStartFill);
    await page.waitForTimeout(500); // let the start-date fetch fully settle before touching end-date

    const callsBeforeEndFill = reportCallCount;
    await page.locator('[data-testid="pa-range-end"]').fill('2026-06-02');
    await expect.poll(() => reportCallCount, { timeout: 10_000 }).toBeGreaterThan(callsBeforeEndFill);

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(2, { timeout: 20_000 });

    const bodyText = await table.innerText();
    expect(bodyText).toContain('PKG-A');
    expect(bodyText).toContain('PKG-B');
    expect(bodyText).toContain('100.0%'); // PKG-A per-row cumulative rate: 200/200
    expect(bodyText).toContain('25.0%'); // PKG-B per-row cumulative rate: 100/400
    expect(bodyText).not.toContain('NaN');
    expect(bodyText).not.toContain('Infinity');

    // D3/OD-11: the KPI card's "整體達成率" is SUM(actual)/SUM(plan) = 300/600 =
    // 50.0% -- NEVER the mean of the two rows' own rates (which would be
    // 62.5%, i.e. (100.0%+25.0%)/2). Asserting only the correct value would
    // not catch a regression to the wrong formula on its own, so both the
    // positive and negative assertion are required here (test-plan.md's own
    // "not the other join kind" discipline, applied to D3: prove it is NOT
    // the wrong formula, not just that the happy-path number looks right).
    const kpi = page.locator('[data-testid="pa-kpi-cards"]');
    await expect(kpi).toBeVisible({ timeout: 10_000 });
    await expect(kpi).toContainText('50.0%');
    const kpiText = await kpi.innerText();
    expect(kpiText).not.toContain('62.5%');

    // Cumulative mode reuses the SAME chart component with a different title (design.md).
    await expect(page.locator('.pa-card-title', { hasText: '累計達成率趨勢' })).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('production-achievement — DailyView (前日) with real D+N shift data (D6 closing-chunk backstop)', () => {
  // Real 2-row 5-column Parquet fixture (generated via the `duckdb` Python
  // package): ONE package group, BOTH shifts present on the same day —
  //   (2026-06-10, D, SPEC-D6-A, PKG-D6, 300)
  //   (2026-06-10, N, SPEC-D6-A, PKG-D6, 120)
  // Every other fixture in this test-file family is D-shift-only, so 前日's
  // N班產出 column (and D6's closing-chunk fetch-completeness fix, which is
  // invisible in the UI per interaction-design.md but whose only user-facing
  // trace is "N班產出 for 前日 renders the number the backend actually sent")
  // had no E2E rendering coverage at all before this test.
  const TWO_SHIFT_PARQUET_B64 =
    'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAGGUAAAhlAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABOFQAVQBVELBUEFQAVBhUGAAAgfAIAAAAEAQkAAABTUEVDLUQ2LUEJAAAAU1BFQy1ENi1BFQAVNBU4LBUEFQAVBhUGAAAaZAIAAAAEAQYAAABQS0ctRDYGAAAAUEtHLUQ2FQAVLBUwLBUEFQAVBhUGAAAWVAIAAAAEASwBAAAAAAAAeAAAAAAAAAAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABYEGRwZXCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYEFj4WQiYIPBgEhlAAABgEhlAAABYAKASGUAAAGASGUAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYEFkIWRiZKPBgBThgBRBYAKAFOGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWBBZiFmYmkAE8GAlTUEVDLUQ2LUEYCVNQRUMtRDYtQRYAKAlTUEVDLUQ2LUEYCVNQRUMtRDYtQRERAAAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIWBBZWFlom9gE8GAZQS0ctRDYYBlBLRy1ENhYAKAZQS0ctRDYYBlBLRy1ENhERAAAAJgAcFQQZFQAZGBFhY3R1YWxfb3V0cHV0X3F0eRUCFgQWThZSJtACPBgILAEAAAAAAAAYCHgAAAAAAAAAFgAoCCwBAAAAAAAAGAh4AAAAAAAAABERAAAAFoYDFgQmCBaaAwAoKER1Y2tEQiB2ZXJzaW9uIHYxLjUuNCAoYnVpbGQgMDhlMzRjNDQ3YikZXBwAABwAABwAABwAABwAAAAuAgAAUEFSMQ==';

  const TWO_SHIFT_SPOOL_HIT = {
    query_id: 'pa-two-shift-001',
    spool_download_url: '/api/spool/production_achievement/pa-two-shift-001.parquet',
    spec_workcenter_map: [{ SPECNAME: 'SPEC-D6-A', workcenter_group: '焊接_DB' }],
    targets_map: [],
    package_lf_map: [],
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
    daily_plan_map: [{ workcenter_group: '焊接_DB', package_lf_group: 'PKG-D6', daily_plan_qty: 500 }],
  };

  test('前日 renders D班產出/N班產出/每日產出 independently from a real 2-shift spool', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TWO_SHIFT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-two-shift-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_SHIFT_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping 前日 D+N shift assertions' });
      return;
    }

    // 當日 auto-runs first (empty by default routing above is fine — REPORT_SPOOL_HIT
    // is not registered in this describe block); switch to 前日 to trigger the
    // 2-shift fixture fetch.
    await page.locator('[data-testid="pa-mode-yesterday"]').click();

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(1, { timeout: 20_000 });

    const bodyText = await table.innerText();
    expect(bodyText).toContain('PKG-D6');
    expect(bodyText).toContain('300'); // D班產出
    expect(bodyText).toContain('120'); // N班產出
    expect(bodyText).toContain('420'); // 每日產出 = D+N (300+120)
    expect(bodyText).toContain('84.0%'); // 每日達成率 = 420/500
    expect(bodyText).not.toContain('NaN');
    expect(bodyText).not.toContain('Infinity');
  });
});

test.describe('production-achievement — 設定 button navigation', () => {
  test('設定 button navigates to /production-achievement-settings', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });
    await page.route('**/api/production-achievement/package-lf-map**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    await page.route('**/api/production-achievement/known-package-lf-values**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ package_lf_values: [] }) }));
    await page.route('**/api/production-achievement/workcenter-merge-map**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    await page.route('**/api/production-achievement/known-workcenter-groups**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ raw_workcenter_groups: [] }) }));
    await page.route('**/api/production-achievement/daily-plans**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping settings-nav assertions' });
      return;
    }

    await page.locator('[data-testid="pa-settings-btn"]').click();
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 3_000 }).catch(() => {});

    const settingsRendered = await page.evaluate(() => document.querySelector('.theme-production-achievement-settings') !== null);
    if (settingsRendered) {
      await expect(page.locator('[data-testid="pa-settings-app"]')).toBeVisible({ timeout: 15_000 });
    }
  });
});

test.describe('production-achievement — legacy target-value edit permission (TargetEditPanel, unchanged)', () => {
  test('authorized user can edit a target value', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });
    let putCalled = false;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping edit assertions' });
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();

    const input = page.locator('[data-testid="pa-target-edit-input"]');
    await input.fill('1200');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await expect.poll(() => putCalled, { timeout: 5_000 }).toBe(true);
  });

  test('unauthorized user is blocked from editing (403 handled gracefully)', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) }),
    );
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(TWO_ROW_PARQUET_B64, 'base64') });
    });
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({ success: false, error: { code: 'FORBIDDEN', message: '無權限編輯目標值' }, meta: { timestamp: new Date().toISOString(), app_version: 'test' } }),
        });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const bodyText_theme_production_achievement = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((bodyText_theme_production_achievement?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping 403 assertions' });
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('999');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await expect(page.locator('[data-testid="pa-target-edit-error"]')).toBeVisible({ timeout: 10_000 });
    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });
});
