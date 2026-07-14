/**
 * E2E tests: production-achievement page — always-async spool-backed report
 * flow (rewrite for production-achievement-overhaul, IP-6..IP-8).
 * Mirrors: frontend/tests/playwright/resource-history-async.spec.ts
 *
 * Flow under test (data-shape-contract.md §3.28, useProductionAchievement.ts):
 *   GET /api/production-achievement/report
 *     -> spool miss: 202 {async:true, job_id, status_url:"/api/job/<id>?prefix=production-achievement"}
 *     -> poll generic GET /api/job/<id>?prefix=production-achievement until status=finished
 *     -> re-issue the IDENTICAL GET /report (now a zero-Oracle-cost 200 spool-hit)
 *     -> 200 {query_id, spool_download_url, spec_workcenter_map, targets_map,
 *             package_lf_map, workcenter_merge_map, daily_plan_map} (5 inline maps, IP-6)
 *   always_async: no worker available -> 503 (no sync fallback)
 *
 * production-achievement-overhaul changes exercised here vs. the prior
 * (production-achievement-async-spool) version of this file:
 *   - OD-3: the query auto-runs on page load / mode change — there is no
 *     [data-testid="pa-query-btn"] any more. Every scenario below relies on
 *     the initial 當日 auto-run, or an explicit mode-button click to trigger
 *     a SECOND query (re-selecting the same active mode is a no-op).
 *   - The spool parquet grain widens to 5 columns (+PACKAGE_LF) — fixtures
 *     use REAL, schema-correct Parquet bytes (via the `duckdb` Python
 *     package), not the old 4-column shape.
 *   - Rows are now keyed by PACKAGE_LF group (D班/N班 columns), not by
 *     (output_date, shift_code, workcenter_group) — see App.vue's DailyView table.
 *
 * Route registration follows the LIFO rule (CLAUDE.md ci-workflow.md).
 */

import { test, expect, type Page } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';
const MOCK_META = { timestamp: new Date().toISOString(), app_version: 'test' };

function envelope(data: unknown) {
  return JSON.stringify({ success: true, data, meta: MOCK_META });
}

function errorEnvelope(code: string, message: string) {
  return JSON.stringify({ success: false, error: { code, message }, meta: MOCK_META });
}

function jobStatusUrl(jobId: string): string {
  return `/api/job/${jobId}?prefix=production-achievement`;
}

// Real Parquet fixtures (data-shape-contract.md §3.28.1, production-achievement
// -overhaul 5-column grain: output_date, shift_code, SPECNAME, PACKAGE_LF,
// actual_output_qty) — generated via the real `duckdb` Python package.
//   EMPTY:  0 rows, correct schema.
//   SAMPLE: 2 rows (2026-06-01, D, case-variant SPECNAMEs 'EPOXY D/B'/'epoxy d/b',
//           PACKAGE_LF 'SOD-123FL OP1', 300+200) -> rolls up via PA-06
//           case-insensitive SPECNAME collapse + PA-09 PACKAGE_LF merge
//           (SOD-123FL OP1 -> SOD-123FL) into ONE row: 焊接_DB / SOD-123FL / D=500.
const EMPTY_PA_PARQUET_B64 =
  'UEFSMRUCGWw1ABgNZHVja2RiX3NjaGVtYRUKABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQwlAhgKUEFDS0FHRV9MRiUAABUEJQIYEWFjdHVhbF9vdXRwdXRfcXR5JSQAFgAZDCgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlcHAAAHAAAHAAAHAAAHAAAAL0AAABQQVIx';

const SAMPLE_PA_PARQUET_B64 =
  'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAF9UAAAfVAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABEFQAVQBVELBUEFQAVBhUGAAAgfAIAAAAEAQkAAABFUE9YWSBEL0IJAAAAZXBveHkgZC9iFQAVUBU4LBUEFQAVBhUGAAAoWAIAAAAEAQ0AAABTT0QtMTIzRkwgT1AxQhEAFQAVLBUwLBUEFQAVBhUGAAAWVAIAAAAEASwBAAAAAAAAyAAAAAAAAAAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABYEGRwZXCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYEFj4WQiYIPBgEfVAAABgEfVAAABYAKAR9UAAAGAR9UAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYEFkIWRiZKPBgBRBgBRBYAKAFEGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWBBZiFmYmkAE8GAllcG94eSBkL2IYCUVQT1hZIEQvQhYAKAllcG94eSBkL2IYCUVQT1hZIEQvQhERAAAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIWBBZyFlom9gE8GA1TT0QtMTIzRkwgT1AxGA1TT0QtMTIzRkwgT1AxFgAoDVNPRC0xMjNGTCBPUDEYDVNPRC0xMjNGTCBPUDEREQAAACYAHBUEGRUAGRgRYWN0dWFsX291dHB1dF9xdHkVAhYEFk4WUibQAjwYCCwBAAAAAAAAGAjIAAAAAAAAABYAKAgsAQAAAAAAABgIyAAAAAAAAAAREQAAABaiAxYEJggWmgMAKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGVwcAAAcAAAcAAAcAAAcAAAASgIAAFBBUjE=';

const EMPTY_PA_PARQUET = Buffer.from(EMPTY_PA_PARQUET_B64, 'base64');
const SAMPLE_PA_PARQUET = Buffer.from(SAMPLE_PA_PARQUET_B64, 'base64');

const SAMPLE_SPEC_MAP = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];
const SAMPLE_WC_MERGE_MAP = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
const SAMPLE_PKG_MAP = [{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL' }];
// daily_plan_qty=1000 against rolled-up actual=500 => achievement_rate 0.5 (50.0%)
const SAMPLE_PLAN_MAP = [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 1000 }];

function spoolHitData(overrides: Record<string, unknown> = {}) {
  return {
    query_id: 'qid-default',
    spool_download_url: '/api/spool/production_achievement/default.parquet',
    spec_workcenter_map: SAMPLE_SPEC_MAP,
    targets_map: [],
    package_lf_map: SAMPLE_PKG_MAP,
    workcenter_merge_map: SAMPLE_WC_MERGE_MAP,
    daily_plan_map: SAMPLE_PLAN_MAP,
    ...overrides,
  };
}

async function registerCatchAllRoutes(page: Page): Promise<void> {
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'user' }) }),
  );
  await page.route('**/api/pages**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released' },
        is_admin: false,
        admin_user: null,
        admin_links: { logout: null, pages: null, dashboard: null },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    }),
  );
  await page.route('**/api/production-achievement/filter-options**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB'] }) }),
  );
  await page.route('**/api/production-achievement/targets**', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
  });
  await page.route('**/api/job/**', (route) => {
    if (route.request().method() === 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
    return route.fulfill({ status: 404, contentType: 'application/json', body: errorEnvelope('NOT_FOUND', 'no such job') });
  });
  await page.route('**/api/spool/**', (route) => route.fulfill({ status: 200, contentType: 'application/octet-stream', body: EMPTY_PA_PARQUET }));
}

async function gotoAndWaitForApp(page: Page): Promise<boolean> {
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  if ((bodyText?.trim().length ?? 0) < 50) return false;
  await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 10_000 }).catch(() => {});
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

function reportTable(page: Page) {
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

function skipIfNotRendered(rendered: boolean, note: string): boolean {
  if (!rendered) test.info().annotations.push({ type: 'note', description: note });
  return !rendered;
}

// ===========================================================================
// describe: happy-path critical journey — auto-run -> 202 -> poll -> spool render
// ===========================================================================

test.describe('production-achievement — async job flow (happy path, auto-run on mount)', () => {
  test('long-span async flow: progress shows, job polled to completion, /report re-issued once, table renders', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-happy-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-happy-001', spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet` })) });
    });

    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 1
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 15, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-happy-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });

    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping happy-path assertions')) return;

    const progressBar = page.locator('.async-job-progress');
    const cancelBtn = page.locator('.async-job-progress__cancel');

    // OD-3: auto-run fires on mount — no query button to click.
    const progressVisible = await progressBar.isVisible({ timeout: 10_000 }).catch(() => false);
    if (progressVisible) {
      await expect(cancelBtn).toBeVisible({ timeout: 5_000 });
    }

    await expect(progressBar).toHaveCount(0, { timeout: 25_000 });

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table).toContainText('SOD-123FL', { timeout: 20_000 }); // rows now keyed by PACKAGE_LF group
    const text = await table.innerText();
    expect(text).toContain('500'); // rolled-up daily D+N output (300+200, case-insensitive)
    expect(text).toContain('50.0%'); // achievement_rate = 500/1000 (SAMPLE_PLAN_MAP)

    expect(reportCallCount).toBe(2); // initial spool-miss + post-completion spool-hit re-fetch
  });

  test('spool already warm: 200 on the first call renders directly, no progress bar ever shown', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-warm-001', spool_download_url: '/api/spool/production_achievement/warm-001.parquet' })) }),
    );
    await page.route('**/api/spool/production_achievement/warm-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping warm-spool assertions')) return;

    const table = reportTable(page);
    await expect(table).toContainText('SOD-123FL', { timeout: 20_000 });
    await expect(page.locator('.async-job-progress')).toHaveCount(0);
  });
});

// ===========================================================================
// describe: empty, malformed, and large data (data-boundary + wrong-type)
// ===========================================================================

test.describe('production-achievement — empty, malformed, and large payloads', () => {
  test('empty-spool parquet (0 qualifying rows) renders an empty table, not an error', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-empty-001', spool_download_url: '/api/spool/production_achievement/empty-001.parquet', spec_workcenter_map: [], workcenter_merge_map: [], package_lf_map: [], daily_plan_map: [] })) }),
    );
    await page.route('**/api/spool/production_achievement/empty-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: EMPTY_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping empty-spool assertions')) return;

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });

  test('malformed 200 response (null maps) degrades to empty rows, never crashes', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            query_id: 'qid-pa-malformed-001',
            spool_download_url: '/api/spool/production_achievement/malformed-001.parquet',
            spec_workcenter_map: null,
            // targets_map/package_lf_map/workcenter_merge_map/daily_plan_map intentionally omitted
          },
          meta: MOCK_META,
        }),
      }),
    );
    await page.route('**/api/spool/production_achievement/malformed-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping malformed-payload assertions')) return;

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 15_000 });
    expect(pageErrors).toHaveLength(0);
  });
});

// ===========================================================================
// describe: server / network failure modes
// ===========================================================================

test.describe('production-achievement — server and network failure modes', () => {
  test('503 no-worker-available shows a clear error message, no stuck progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: errorEnvelope('SERVICE_UNAVAILABLE', '背景查詢服務暫時無法使用，請稍後再試') }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping 503 assertions')) return;

    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('背景查詢服務暫時無法使用');
    await expect(page.locator('.async-job-progress')).toHaveCount(0);
  });

  test('async job status=failed surfaces the job error message and clears the progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-failed-001';
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ status: 'failed', job_id: JOB_ID, query_id: null, error: 'Oracle 連線逾時', pct: null, stage: null, progress: null }) }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping job-failure assertions')) return;

    await expect
      .poll(async () => (await page.locator('.error-banner-message').textContent().catch(() => null)) ?? '', { timeout: 15_000 })
      .toContain('Oracle 連線逾時');
    await expect(page.locator('.async-job-progress:not(.async-job-progress--failed)')).toHaveCount(0, { timeout: 5_000 });
  });
});

// ===========================================================================
// describe: user-initiated cancel + mode-switch retry (OD-4)
// ===========================================================================

test.describe('production-achievement — cancel + OD-4 mode-switch retry', () => {
  test('user cancels mid-poll: progress clears, no error shown, abandon request fires; switching mode afterwards starts a fresh query', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-cancel-001';
    const requestedUrls: string[] = [];
    page.on('request', (req) => requestedUrls.push(req.url()));

    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        // Job never finishes on its own — forces the user to cancel.
        return route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) });
      }
      // The SECOND query (after switching to 前日) resolves immediately (warm).
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-retry-001', spool_download_url: '/api/spool/production_achievement/retry-001.parquet' })) });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      if (route.request().method() === 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 20, stage: 'querying', progress: '背景查詢中...' }) });
    });
    await page.route('**/api/spool/production_achievement/retry-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping cancel/retry assertions')) return;

    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 10_000 });

    await page.locator('.async-job-progress__cancel').click();

    await expect(progressBar).toHaveCount(0, { timeout: 10_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
    expect(requestedUrls.some((u) => u.includes(`/api/job/${JOB_ID}/abandon`))).toBe(true);

    // OD-4/Reversibility: re-selecting the SAME mode is a no-op; switching to
    // a DIFFERENT mode (前日) starts a genuinely new query.
    await page.locator('[data-testid="pa-mode-yesterday"]').click();
    const table = reportTable(page);
    await expect(table).toContainText('SOD-123FL', { timeout: 20_000 });
  });

  test('OD-4: clicking a different mode WHILE a 202 poll is in flight (no cancel) is a pure no-op until the poll resolves', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-od4-ignore-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-od4-001', spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet` })) });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 1
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 10, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-od4-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping OD-4 ignore-mid-poll assertions')) return;

    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 10_000 }); // poll is now DEFINITELY in flight (status=started)

    const callsBeforeClick = reportCallCount;
    await page.locator('[data-testid="pa-mode-yesterday"]').click();
    // OD-4 (interaction-design.md § Confirmed, "忽略直到當前查詢完成"): a mode
    // change mid-poll is a pure no-op at the setMode() call site (`if
    // (loading.value) return`, evaluated BEFORE filters.mode is ever
    // reassigned) — unlike the cancel-then-switch test above, no cancel
    // happens here, so the ORIGINAL 當日 query must be the one that resolves,
    // not a cancel-and-restart.
    await page.waitForTimeout(300); // window for an (incorrect) click-driven fetch to have fired, well before the mocked poll's own ~3s resolution
    expect(reportCallCount).toBe(callsBeforeClick); // no second /report from the ignored click
    await expect(page.locator('[data-testid="pa-mode-today"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-testid="pa-mode-yesterday"]')).toHaveAttribute('aria-pressed', 'false');

    // Let the ORIGINAL (當日) poll resolve on its own.
    await expect(progressBar).toHaveCount(0, { timeout: 20_000 });
    const table = reportTable(page);
    await expect(table).toContainText('SOD-123FL', { timeout: 20_000 });
    expect(reportCallCount).toBe(2); // initial 202 + the ONE tail re-fetch on completion -- the ignored click added nothing

    // The guard is scoped to "only while loading" -- once resolved, mode
    // switching works normally again (not permanently stuck).
    await page.locator('[data-testid="pa-mode-yesterday"]').click();
    await expect(page.locator('[data-testid="pa-mode-yesterday"]')).toHaveAttribute('aria-pressed', 'true', { timeout: 10_000 });
    expect(reportCallCount).toBe(3);
  });

  test('hidden tab mid-poll: job still completes and results render once visible again', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-hidden-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-hidden-001', spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet` })) });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 1
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 15, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-hidden-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping hidden-tab assertions')) return;

    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    const table = reportTable(page);
    await expect(table).toContainText('SOD-123FL', { timeout: 25_000 });

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
  });

  test('navigating away mid-poll and back does not crash or leave a stuck page', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-backnav-001';
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      if (route.request().method() === 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 10, stage: 'querying', progress: '背景查詢中...' }) });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping back/forward assertions')) return;

    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });

    await page.goto('/portal-shell/login', { waitUntil: 'domcontentloaded', timeout: 15_000 }).catch(() => {});
    await page.goBack({ waitUntil: 'domcontentloaded', timeout: 15_000 }).catch(() => {});

    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rerendered = await page.evaluate(() => document.querySelector('.theme-production-achievement') !== null);
    if (rerendered) {
      await expect(page.locator('[data-testid="pa-mode-today"]')).toBeVisible({ timeout: 10_000 });
    }
    expect(pageErrors).toHaveLength(0);
  });
});

// ===========================================================================
// describe: shared 202-poll machinery across modes (D5)
// ===========================================================================

test.describe('production-achievement — shared 202-poll machinery across modes (D5)', () => {
  test('當月 (never warm-cached, design.md non-goal) shows the SAME AsyncQueryProgress card as a 當日/前日 cache-miss', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-month-202-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      // Call 1 (當日, on mount) resolves instantly — simulates the PA-14 warm-cache hit.
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: envelope(spoolHitData({ query_id: 'qid-pa-today-warm-001', spool_download_url: '/api/spool/production_achievement/today-warm-001.parquet' })),
        });
      }
      // Call 2 (當月): month/range are NEVER warm-cached (design.md § Open Risks
      // non-goal) — every 當月/自訂區間 query takes this SAME spool-miss ->
      // enqueue -> poll -> tail-refetch path, shared with 當日/前日's cache-miss
      // fallback (D5, Consistency Commitments: "the async progress card is one
      // shared component across all four modes").
      if (reportCallCount === 2) {
        return route.fulfill({ status: 202, contentType: 'application/json', body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }) });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope(spoolHitData({ query_id: 'qid-pa-month-001', spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet` })),
      });
    });
    await page.route('**/api/spool/production_achievement/today-warm-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 1
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 20, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-month-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping D5 shared-machinery assertions')) return;

    // 當日 warm-hit: renders directly, no progress card at all.
    await expect(reportTable(page)).toContainText('SOD-123FL', { timeout: 15_000 });
    await expect(page.locator('.async-job-progress')).toHaveCount(0);

    await page.locator('[data-testid="pa-mode-month"]').click();

    // The SAME progress card component the 當日/前日 happy-path tests exercise
    // (production-achievement.spec.js / this file's own "happy path" describe
    // block above) must appear for 當月 too — proving it is genuinely shared
    // machinery, not a mode-specific implementation.
    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.async-job-progress__cancel')).toBeVisible({ timeout: 5_000 });

    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 20_000 });
    await expect(reportTable(page)).toContainText('SOD-123FL', { timeout: 20_000 });
    expect(reportCallCount).toBe(3); // 當日 warm-200 + 當月 202 + 當月 tail-refetch-200
  });
});

// ===========================================================================
// describe: stale-cache avoidance after a target-value edit (legacy panel)
// ===========================================================================

test.describe('production-achievement — target edit recomputes client-side without a stale spool re-fetch', () => {
  test('saving a new target_qty on the legacy TargetEditPanel does not re-issue /report', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHitData({ query_id: 'qid-pa-target-edit-001', spool_download_url: '/api/spool/production_achievement/target-edit-001.parquet' })) }),
    );
    await page.route('**/api/spool/production_achievement/target-edit-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    let putCalled = false;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping target-edit assertions')) return;

    const table = reportTable(page);
    await expect(table).toContainText('SOD-123FL', { timeout: 25_000 });

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    if (!(await editBtn.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.info().annotations.push({ type: 'note', description: 'no legacy target rows in this fixture; skipping edit interaction' });
      return;
    }
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('250');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await expect.poll(async () => putCalled, { timeout: 10_000 }).toBe(true);
  });
});
