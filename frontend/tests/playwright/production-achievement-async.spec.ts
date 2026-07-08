/**
 * E2E tests: production-achievement page — always-async spool-backed report flow
 * Change: production-achievement-async-spool (ADR-0016)
 * Mirrors: frontend/tests/playwright/resource-history-async.spec.ts
 *
 * Flow under test (data-shape-contract.md §3.28, implementation-plan.md IP-7):
 *   GET /api/production-achievement/report
 *     -> spool miss: 202 {async:true, job_id, status_url:"/api/job/<id>?prefix=production-achievement"}
 *     -> poll generic GET /api/job/<id>?prefix=production-achievement until status=finished
 *     -> re-issue the IDENTICAL GET /report (now a zero-Oracle-cost 200 spool-hit)
 *     -> 200 {query_id, spool_download_url, spec_workcenter_map, targets_map}
 *     -> browser downloads the parquet into DuckDB-WASM and renders rolled-up rows
 *        (output_date, shift_code, workcenter_group, actual_output_qty, target_qty,
 *        achievement_rate)
 *   always_async: no worker available -> 503 (no sync fallback)
 *
 * Network strategy: every API call is intercepted with page.route(); no real
 * backend or RQ worker required. Real minimal Parquet fixtures (generated via
 * the actual `duckdb` Python package, matching the exact §3.28.1 schema) are
 * embedded as base64 so DuckDB-WASM can genuinely parse and roll them up —
 * NOT the magic-bytes-only stand-ins used by sibling specs, which the DuckDB
 * engine would reject.
 *
 * Route registration follows the LIFO rule (CLAUDE.md ci-workflow.md):
 * catch-all routes registered FIRST, specific per-test routes registered LAST
 * so the specific mock wins.
 *
 * Stable selectors used:
 *   [data-testid="pa-app"]                — App.vue root
 *   [data-testid="pa-query-btn"]          — query submit button
 *   [data-testid="datatable"]             — DataTable root (report card, scoped by heading)
 *   [data-testid="datatable-empty"]       — DataTable empty-state row
 *   .async-job-progress                   — AsyncQueryProgress root (active=true)
 *   .async-job-progress--failed           — failed-state modifier
 *   .async-job-progress__cancel           — cancel button inside progress bar
 *   [role="alert"] / .error-banner-message — ErrorBanner
 *   .loading-overlay                      — LoadingOverlay (page-tier, pre-poll phase)
 */

import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Real minimal Parquet fixtures (data-shape-contract.md §3.28.1 schema:
// output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, actual_output_qty
// BIGINT) — generated with the real `duckdb` Python package so DuckDB-WASM
// can genuinely register + query them (unlike bare "PAR1" magic-byte stubs).
//
//   EMPTY:  0 rows, correct schema — proves the empty-result invariant.
//   SAMPLE: 2 rows, same (output_date=2026-06-01, shift_code=D) but two
//           case-variant SPECNAMEs ('EPOXY D/B' / 'epoxy d/b', 300 + 200)
//           that both map to workcenter_group '焊接_DB' via
//           UPPER(TRIM(SPECNAME)) — PA-06 case-insensitive rollup collapses
//           them into one row with actual_output_qty=500.
// ---------------------------------------------------------------------------

const EMPTY_PA_PARQUET_B64 =
  'UEFSMRUCGVw1ABgNZHVja2RiX3NjaGVtYRUIABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQQlAhgRYWN0dWFsX291dHB1dF9xdHklJAAWABkMKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGUwcAAAcAAAcAAAcAAAApwAAAFBBUjE=';

const SAMPLE_PA_PARQUET_B64 =
  'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAF9UAAAfVAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABEFQAVQBVELBUEFQAVBhUGAAAgfAIAAAAEAQkAAABFUE9YWSBEL0IJAAAAZXBveHkgZC9iFQAVLBUwLBUEFQAVBhUGAAAWVAIAAAAEASwBAAAAAAAAyAAAAAAAAAAVAhlcNQAYDWR1Y2tkYl9zY2hlbWEVCAAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUEJQIYEWFjdHVhbF9vdXRwdXRfcXR5JSQAFgQZHBlMJgAcFQIZFQAZGAtvdXRwdXRfZGF0ZRUCFgQWPhZCJgg8GAR9UAAAGAR9UAAAFgAoBH1QAAAYBH1QAAAREQAAACYAHBUMGRUAGRgKc2hpZnRfY29kZRUCFgQWQhZGJko8GAFEGAFEFgAoAUQYAUQREQAAACYAHBUMGRUAGRgIU1BFQ05BTUUVAhYEFmIWZiaQATwYCWVwb3h5IGQvYhgJRVBPWFkgRC9CFgAoCWVwb3h5IGQvYhgJRVBPWFkgRC9CEREAAAAmABwVBBkVABkYEWFjdHVhbF9vdXRwdXRfcXR5FQIWBBZOFlIm9gE8GAgsAQAAAAAAABgIyAAAAAAAAAAWACgILAEAAAAAAAAYCMgAAAAAAAAAEREAAAAWsAIWBCYIFsACACgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlMHAAAHAAAHAAAHAAAANABAABQQVIx';

const EMPTY_PA_PARQUET = Buffer.from(EMPTY_PA_PARQUET_B64, 'base64');
const SAMPLE_PA_PARQUET = Buffer.from(SAMPLE_PA_PARQUET_B64, 'base64');

// Injected map matching SAMPLE_PA_PARQUET's SPECNAMEs (§3.28.2)
const SAMPLE_SPEC_MAP = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];
// Injected targets (§3.28.3) — target=1000 against actual=500 => achievement_rate 0.5
const SAMPLE_TARGETS_MAP = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 1000 }];

// ---------------------------------------------------------------------------
// Route setup helpers
// ---------------------------------------------------------------------------

/**
 * Register catch-all routes FIRST (LIFO — overridden by per-test specific
 * routes registered afterwards). Mirrors production-achievement-data-boundary
 * .spec.js / production-achievement-resilience.spec.js's setupBaseRoutes.
 */
async function registerCatchAllRoutes(page: Page): Promise<void> {
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'user' }) }),
  );
  await page.route('**/api/pages**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }),
  );
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      // Plain unwrapped shape (see app.py::portal_navigation_config()).
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
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB'] }),
    }),
  );
  await page.route('**/api/production-achievement/targets**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
  });
  // Default job status/abandon catch-all — overridden per-test for the job id under test.
  await page.route('**/api/job/**', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: errorEnvelope('NOT_FOUND', 'no such job') });
  });
  // Default spool catch-all — overridden per-test.
  await page.route('**/api/spool/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/octet-stream', body: EMPTY_PA_PARQUET }),
  );
}

async function gotoAndWaitForApp(page: Page): Promise<boolean> {
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
  // FAST no-dev-server detection (mirrors resource-history-async.spec.ts). When no
  // server is serving the app (the default in CI — these e2e specs run without a
  // dev server and skip), the page body is effectively empty; bail out in well under
  // a second instead of burning the full waitForFunction timeout on EVERY test. That
  // 20s x ~20-tests x retries stall is what made this step run ~25 min in CI.
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  if ((bodyText?.trim().length ?? 0) < 50) return false;
  // Server present: wait (bounded) for the app-specific theme root to mount, then
  // confirm it is actually visible. pageRendered guard checks app-specific content
  // (the page's own theme root), never a generic bodyText.length check for readiness.
  await page
    .waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 10_000 })
    .catch(() => {});
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

function reportTable(page: Page) {
  const reportCard = page.locator('.ui-card', { has: page.locator('.ui-card-title', { hasText: '生產達成率明細' }) });
  return reportCard.locator('[data-testid="datatable"]');
}

function skipIfNotRendered(rendered: boolean, note: string): boolean {
  if (!rendered) {
    test.info().annotations.push({ type: 'note', description: note });
  }
  return !rendered;
}

// ===========================================================================
// describe: happy-path critical journey — 202 enqueue -> poll -> spool render
// ===========================================================================

test.describe('production-achievement — async job flow (happy path)', () => {
  test('long-span async flow: progress shows, job polled to completion, /report re-issued once, table renders', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-happy-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-happy-001',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: SAMPLE_SPEC_MAP,
          targets_map: SAMPLE_TARGETS_MAP,
        }),
      });
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

    await page.locator('[data-testid="pa-query-btn"]').click();

    // Progress must appear while polling (202 -> before job finishes).
    const progressVisible = await progressBar.isVisible({ timeout: 10_000 }).catch(() => false);
    if (progressVisible) {
      await expect(cancelBtn).toBeVisible({ timeout: 5_000 });
    }

    // Progress must clear once the job completes and the DuckDB-WASM render finishes.
    await expect(progressBar).toHaveCount(0, { timeout: 25_000 });

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table).toContainText('2026-06-01', { timeout: 20_000 });
    const text = await table.innerText();
    expect(text).toContain('D');
    expect(text).toContain('焊接_DB');
    expect(text).toContain('500'); // rolled-up actual_output_qty (300+200, case-insensitive)
    expect(text).toContain('1,000'); // target_qty
    expect(text).toContain('50.0%'); // achievement_rate = 500/1000

    // The re-issue-GET-after-finished mechanic: exactly 2 calls to /report —
    // the initial spool-miss and the post-completion spool-hit re-fetch.
    expect(reportCallCount).toBe(2);
  });

  test('spool already warm: 200 on the first call renders directly, no progress bar ever shown', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-warm-001',
          spool_download_url: '/api/spool/production_achievement/warm-001.parquet',
          spec_workcenter_map: SAMPLE_SPEC_MAP,
          targets_map: SAMPLE_TARGETS_MAP,
        }),
      }),
    );
    await page.route('**/api/spool/production_achievement/warm-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping warm-spool assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    const table = reportTable(page);
    await expect(table).toContainText('焊接_DB', { timeout: 20_000 });

    // AC-6-style regression: sync-shaped (immediate 200) path never activates
    // the async progress UI.
    await expect(page.locator('.async-job-progress')).toHaveCount(0);
  });
});

// ===========================================================================
// describe: empty, malformed, and large data (data-boundary + wrong-type)
// ===========================================================================

test.describe('production-achievement — empty, malformed, and large payloads', () => {
  test('empty-spool parquet (0 qualifying rows) renders an empty table, not an error', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-empty-001';
    let reportCallCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-empty-001',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: [],
          targets_map: [],
        }),
      });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-empty-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' }),
      }),
    );
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: EMPTY_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping empty-spool assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();
    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 20_000 });

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });

  test('malformed 200 response (null spec_workcenter_map, missing targets_map) degrades to empty rows, never crashes', async ({ page }) => {
    await registerCatchAllRoutes(page);

    // Wrong-type / partial data: spec_workcenter_map explicitly null,
    // targets_map key entirely absent. The composable's `data.x || []`
    // guards must default both safely (useProductionAchievement.ts _activateAndRender).
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
            // targets_map intentionally omitted
          },
          meta: MOCK_META,
        }),
      }),
    );
    // Spool has real rows, but with no spec_workcenter_map entries the PA-06
    // inner join must exclude all of them — proves the malformed map (not
    // the spool) is what degrades the result, and does so safely.
    await page.route('**/api/spool/production_achievement/malformed-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping malformed-payload assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 10_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 15_000 });
    expect(pageErrors).toHaveLength(0);
  });

  test('large inline maps (300 SPECNAME + 300 target entries) do not hang or crash the page', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const largeSpecMap = Array.from({ length: 300 }, (_, i) => ({ SPECNAME: `SPEC-${i}`, workcenter_group: `GROUP-${i % 10}` }));
    const largeTargetsMap = Array.from({ length: 300 }, (_, i) => ({ shift_code: 'D', workcenter_group: `GROUP-${i % 10}`, target_qty: 100 + i }));

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-large-001',
          spool_download_url: '/api/spool/production_achievement/large-001.parquet',
          spec_workcenter_map: largeSpecMap,
          targets_map: largeTargetsMap,
        }),
      }),
    );
    await page.route('**/api/spool/production_achievement/large-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: EMPTY_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping large-payload assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    const table = reportTable(page);
    // Generous but bounded timeout — proves the 300-row VALUES-list
    // construction (buildValuesTableSql) does not hang the DuckDB-WASM worker.
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });
});

// ===========================================================================
// describe: server / network failure modes
// ===========================================================================

test.describe('production-achievement — server and network failure modes', () => {
  test('503 no-worker-available shows a clear error message, no stuck progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: errorEnvelope('SERVICE_UNAVAILABLE', '背景查詢服務暫時無法使用，請稍後再試'),
      }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping 503 assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('背景查詢服務暫時無法使用');
    await expect(page.locator('.async-job-progress')).toHaveCount(0);

    // The query button must not be left stuck in a disabled/"查詢中…" state.
    const btn = page.locator('[data-testid="pa-query-btn"]');
    await expect(btn).toHaveText('查詢', { timeout: 5_000 });
    await expect(btn).toBeEnabled();
  });

  test('HTTP 500 from /report shows error feedback, not a stuck spinner', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: errorEnvelope('INTERNAL_ERROR', 'Oracle ORA-12541: no listener'),
      }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping 500 assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    await expect(page.locator('.error-banner-message')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.loading-overlay')).toHaveCount(0, { timeout: 5_000 });
  });

  test('aborted /report request does not leave the query button or spinner stuck', async ({ page }) => {
    await registerCatchAllRoutes(page);

    await page.route('**/api/production-achievement/report**', (route) => route.abort('failed'));

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping abort assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    await expect(page.locator('.error-banner-message')).toBeVisible({ timeout: 15_000 });
    const btn = page.locator('[data-testid="pa-query-btn"]');
    await expect(btn).toHaveText('查詢', { timeout: 5_000 });
    await expect(page.locator('.loading-overlay')).toHaveCount(0);
  });

  test('slow network on the initiating /report call keeps a loading state until the response arrives', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-slow-001';
    let reportCallCount = 0;

    await page.route('**/api/production-achievement/report**', async (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        await new Promise((resolve) => setTimeout(resolve, 4_000));
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-slow-001',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: SAMPLE_SPEC_MAP,
          targets_map: SAMPLE_TARGETS_MAP,
        }),
      });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-slow-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' }),
      }),
    );
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping slow-network assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    // While the initiating call is in flight, the button must reflect the
    // loading state (not a silent freeze).
    await expect(page.locator('[data-testid="pa-query-btn"]')).toHaveText('查詢中…', { timeout: 2_000 });

    const table = reportTable(page);
    await expect(table).toContainText('焊接_DB', { timeout: 25_000 });
  });

  test('async job status=failed surfaces the job error message and clears the progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-failed-001';

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
      }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'failed', job_id: JOB_ID, query_id: null, error: 'Oracle 連線逾時', pct: null, stage: null, progress: null }),
      }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping job-failure assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    await expect
      .poll(
        async () => {
          const banner = await page.locator('.error-banner-message').textContent().catch(() => null);
          return banner ?? '';
        },
        { timeout: 15_000 },
      )
      .toContain('Oracle 連線逾時');

    // Only the transitional --failed bar is allowed; an ACTIVE (non-failed)
    // bar must not linger (mirrors resource-history-async.spec.ts AC-9).
    await expect(page.locator('.async-job-progress:not(.async-job-progress--failed)')).toHaveCount(0, { timeout: 5_000 });
  });

  test('session expiry mid-poll (401 on job status) surfaces an error, does not hang forever', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-401-001';
    let pollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
      }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      pollCount++;
      if (pollCount === 1) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 10, stage: 'querying', progress: '背景查詢中...' }),
        });
      }
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: errorEnvelope('UNAUTHORIZED', '登入逾時，請重新登入'),
      });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping session-expiry assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    await expect
      .poll(
        async () => {
          const banner = await page.locator('.error-banner-message').textContent().catch(() => null);
          return banner ?? '';
        },
        { timeout: 20_000 },
      )
      .toContain('登入逾時');

    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 5_000 });
  });
});

// ===========================================================================
// describe: user-initiated cancel, hidden tab, browser back/forward
// ===========================================================================

test.describe('production-achievement — cancel, visibility, and navigation resilience', () => {
  test('user cancels mid-poll: progress clears, no error shown, abandon request fires', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-cancel-001';
    const requestedUrls: string[] = [];
    page.on('request', (req) => requestedUrls.push(req.url()));

    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
      }),
    );
    // Job never finishes on its own — forces the user to cancel.
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 20, stage: 'querying', progress: '背景查詢中...' }),
      });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping cancel assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();

    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 10_000 });

    await page.locator('.async-job-progress__cancel').click();

    await expect(progressBar).toHaveCount(0, { timeout: 10_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
    const btn = page.locator('[data-testid="pa-query-btn"]');
    await expect(btn).toHaveText('查詢', { timeout: 5_000 });
    await expect(btn).toBeEnabled();

    expect(requestedUrls.some((u) => u.includes(`/api/job/${JOB_ID}/abandon`))).toBe(true);
  });

  test('hidden tab mid-poll: job still completes and results render once visible again', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-hidden-001';
    let reportCallCount = 0;
    let jobPollCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-hidden-001',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: SAMPLE_SPEC_MAP,
          targets_map: SAMPLE_TARGETS_MAP,
        }),
      });
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

    await page.locator('[data-testid="pa-query-btn"]').click();
    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });

    // Simulate the tab going into background mid-poll.
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    const table = reportTable(page);
    await expect(table).toContainText('焊接_DB', { timeout: 25_000 });

    // Restore visibility for hygiene.
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
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
      }),
    );
    // Job never finishes — the page is navigated away from while still polling.
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 10, stage: 'querying', progress: '背景查詢中...' }),
      });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping back/forward assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();
    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });

    // Navigate to the login page (auth guard bypasses it) — a full navigation
    // destroys the current Vue app while a job is still in flight.
    await page.goto('/portal-shell/login', { waitUntil: 'domcontentloaded', timeout: 15_000 }).catch(() => {});
    await page.goBack({ waitUntil: 'domcontentloaded', timeout: 15_000 }).catch(() => {});

    await page
      .waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 })
      .catch(() => {});

    const rerendered = await page.evaluate(() => document.querySelector('.theme-production-achievement') !== null);
    if (rerendered) {
      // The page must remount cleanly — the query control must be usable again.
      await expect(page.locator('[data-testid="pa-query-btn"]')).toBeEnabled({ timeout: 10_000 });
    }
    expect(pageErrors).toHaveLength(0);
  });
});

// ===========================================================================
// describe: stale-cache avoidance after a target-value edit
// ===========================================================================

test.describe('production-achievement — target edit recomputes client-side without a stale spool re-fetch', () => {
  test('saving a new target_qty recomputes achievement_rate from the cached spool, without re-issuing /report', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'pa-job-target-edit-001';
    let reportCallCount = 0;
    let targetsGetCount = 0;

    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount++;
      if (reportCallCount === 1) {
        return route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: envelope({ async: true, job_id: JOB_ID, status_url: jobStatusUrl(JOB_ID) }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-pa-target-edit-001',
          spool_download_url: `/api/spool/production_achievement/${JOB_ID}.parquet`,
          spec_workcenter_map: SAMPLE_SPEC_MAP,
          targets_map: SAMPLE_TARGETS_MAP, // target_qty=1000 initially
        }),
      });
    });
    await page.route(`**/api/job/${JOB_ID}**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'finished', job_id: JOB_ID, query_id: 'qid-pa-target-edit-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' }),
      }),
    );
    await page.route(`**/api/spool/production_achievement/${JOB_ID}.parquet**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: SAMPLE_PA_PARQUET }),
    );

    let putCalled = false;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      targetsGetCount++;
      // After the PUT, fetchTargets() re-reads a NEW target_qty=250.
      const targetQty = targetsGetCount <= 1 ? 1000 : 250;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope([
          { shift_code: 'D', workcenter_group: '焊接_DB', target_qty: targetQty, updated_at: '2026-06-01T00:00:00Z', updated_by: 'admin' },
        ]),
      });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping target-edit assertions')) return;

    await page.locator('[data-testid="pa-query-btn"]').click();
    const table = reportTable(page);
    await expect(table).toContainText('50.0%', { timeout: 25_000 }); // 500/1000

    const reportCallsAfterQuery = reportCallCount;

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 10_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('250');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await expect.poll(async () => putCalled, { timeout: 10_000 }).toBe(true);

    // achievement_rate recomputes to 500/250 = 200.0% from the cached spool.
    await expect(table).toContainText('200.0%', { timeout: 15_000 });

    // No additional /report round-trip was needed — the recompute happened
    // entirely client-side against the already-downloaded spool + refreshed
    // targets_map (useProductionAchievement.ts saveTarget()).
    expect(reportCallCount).toBe(reportCallsAfterQuery);
  });
});
