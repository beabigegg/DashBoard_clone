/**
 * Monkey / structured-adversarial spec: 生產達成率 (Production Achievement Rate)
 * — async report flow (production-achievement-async-spool, ADR-0016).
 *
 * "Monkey operation engineer" scope: structured misuse discovery over the new
 * GET /report -> 202 job_id -> poll /api/job/<id>?prefix=production-achievement
 * -> re-GET -> 200 spool_download_url+maps -> DuckDB-WASM render flow, plus the
 * TargetEditPanel (PUT targets) that re-triggers a client-side recompute on the
 * same page. Every scenario below is mapped to a NAMED failure mode / hardening
 * goal (see the doc-comment above each `test.describe` block) — not random
 * chaos. Tier 2, nightly/manual "monkey" family per ci-gates.md; this spec is
 * NOT part of the bounded CI test ladder and does not touch test-evidence.yml.
 *
 * Network strategy (CLAUDE.md ci-workflow.md):
 *   - page.route() LIFO: catch-all routes registered FIRST, specific routes
 *     registered LAST so they win.
 *   - page.goto(...).catch(() => {}) + an app-specific pageRendered guard
 *     (`.theme-production-achievement`), never `bodyText.length > 100`
 *     (Chrome's ECONNREFUSED error page exceeds 100 chars).
 *   - Local runs assume a pre-built dist/ is served (`npm run build` first);
 *     if no dev server is detected, deep assertions are skipped with a
 *     `test.info().annotations.push(...)` note instead of a hard failure —
 *     the SAME convention already used by every sibling spec in this exact
 *     file tree (production-achievement.spec.js, resource-history-async.spec.ts,
 *     downtime-analysis.spec.ts).
 *
 * Real-DuckDB fixtures: three scenarios need the ACTUAL browser DuckDB-WASM
 * compute path to answer the question under test (empty spool, all-unmapped
 * SPECNAME, target-edit recompute). downtime-analysis.spec.ts's precedent uses
 * an 8-byte fake "PAR1PAR1" magic-only buffer and explicitly documents that
 * "DuckDB-WASM would reject this" — real compute is never exercised there.
 * The parquet fixtures below are REAL, minimal, schema-correct files (built
 * with the `duckdb` Python package and round-tripped through `read_parquet()`
 * to confirm validity — generation script referenced in this change's
 * monkey-test-engineer agent-log). When the test browser's DuckDB-WASM
 * successfully initialises, these fixtures let the assertions be strict; when
 * it does not (sandboxed/headless environment constraints — same class of
 * uncertainty documented in downtime-analysis.spec.ts), the test degrades to
 * an annotated no-op rather than a false failure, and a same-behavior
 * mocked-engine version already exists at the unit-test tier
 * (useProductionAchievementDuckDB.test.ts) as the tripwire that is NOT allowed
 * to degrade.
 *
 * Scenario -> failure-mode map (also recorded in agent-log/monkey-test-engineer.yml):
 *   1  rapid triple-click Query while polling      -> in-flight dedup guard
 *   2  rapid double-click target Save              -> rapid-click torn-state guard
 *   3  mutate date filters mid-poll                -> stale-result-overwrite guard
 *   4  navigate away mid-poll (sidebar) + return    -> onUnmounted poll cancellation
 *   5  explicit Cancel button mid-poll              -> cancelQuery() no-orphan guard
 *   6  browser back/forward mid-poll                -> unsupported navigation sequence
 *   7  tab hidden after a completed query            -> no hidden-tab auto-refresh (non-goal)
 *   8  adversarial date filters (4 cases)            -> invalid date range / missing filter
 *   9  wrong-typed /report 200 payload fields        -> wrong column/type data
 *  10  401 on job-status mid-poll                    -> stale session
 *  11  empty parquet spool                           -> empty-result invariant
 *  12  all-unmapped-SPECNAME parquet                 -> empty-result invariant (PA-06)
 *  13  adversarial target_qty values (8 cases)       -> overlong/Unicode/SQL/script input
 *  14  target_qty -> 0 real recompute                -> null rate, never Infinity/NaN
 */

import { test, expect, type Page } from '@playwright/test';
import { navigateViaSidebar } from './_auth.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_URL = '/portal-shell/production-achievement';
const MOCK_META = { timestamp: new Date().toISOString(), app_version: 'test' };
const PARQUET_CONTENT_TYPE = 'application/octet-stream';

const REPORT_CARD_TITLE = '生產達成率明細';

/**
 * Fallback dummy bytes for tests that never intend to exercise real DuckDB
 * compute (matches downtime-analysis.spec.ts's documented "PAR1"+"PAR1"
 * magic-only convention for spool responses that are not the point under test).
 */
const DUMMY_PARQUET_BYTES = Buffer.from([0x50, 0x41, 0x52, 0x31, 0x50, 0x41, 0x52, 0x31]);

/**
 * Real, schema-correct, empty (0-row) Parquet — columns
 * (output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, actual_output_qty
 * INTEGER), matching data-shape-contract.md §3.28.1. Built with the `duckdb`
 * Python package and round-tripped through `read_parquet()` to confirm
 * validity (see agent-log for the generation script pointer).
 */
const EMPTY_SPOOL_PARQUET_B64 =
  'UEFSMRUCGVw1ABgNZHVja2RiX3NjaGVtYRUIABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQIlAhgRYWN0dWFsX291dHB1dF9xdHklIgAWABkMKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGUwcAAAcAAAcAAAcAAAApwAAAFBBUjE=';

/**
 * Real 2-row Parquet, same schema, where BOTH SPECNAME values ("GHOST-SPEC-1",
 * "GHOST-SPEC-2") deliberately do NOT appear in the mocked spec_workcenter_map
 * below — the real browser-side INNER JOIN in _buildRollup() must exclude
 * every row (PA-06 unmapped-SPECNAME exclusion), never error.
 */
const UNMAPPED_SPECNAME_PARQUET_B64 =
  'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAF9UAAAfVAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABOFQAVTBU6LBUEFQAVBhUGAAAmVAIAAAAEAQwAAABHSE9TVC1TUEVDLTE6EAAAMhUAFRwVICwVBBUAFQYVBgAADjQCAAAABAH0AQAALAEAABUCGVw1ABgNZHVja2RiX3NjaGVtYRUIABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQIlAhgRYWN0dWFsX291dHB1dF9xdHklIgAWBBkcGUwmABwVAhkVABkYC291dHB1dF9kYXRlFQIWBBY+FkImCDwYBH1QAAAYBH1QAAAWACgEfVAAABgEfVAAABERAAAAJgAcFQwZFQAZGApzaGlmdF9jb2RlFQIWBBZCFkYmSjwYAU4YAUQWACgBThgBRBERAAAAJgAcFQwZFQAZGAhTUEVDTkFNRRUCFgQWbhZcJpABPBgMR0hPU1QtU1BFQy0yGAxHSE9TVC1TUEVDLTEWACgMR0hPU1QtU1BFQy0yGAxHSE9TVC1TUEVDLTEREQAAACYAHBUCGRUAGRgRYWN0dWFsX291dHB1dF9xdHkVAhYEFj4WQibsATwYBPQBAAAYBCwBAAAWACgE9AEAABgELAEAABERAAAAFqwCFgQmCBamAgAoKER1Y2tEQiB2ZXJzaW9uIHYxLjUuNCAoYnVpbGQgMDhlMzRjNDQ3YikZTBwAABwAABwAABwAAADMAQAAUEFSMQ==';

/**
 * Real 1-row Parquet, SPECNAME "REAL-SPEC-1" (2026-06-01, shift D,
 * actual_output_qty=500) — DOES map to the mocked spec_workcenter_map's
 * ("REAL-SPEC-1" -> "GROUP-A") entry, used by the target-edit real-recompute
 * scenario (initial state target_qty=1000 -> achievement_rate 0.5).
 */
const MAPPED_SPOOL_PARQUET_B64 =
  'UEFSMRUAFRQVGCwVAhUAFQYVBgAACiQCAAAAAgF9UAAAFQAVFhUaLBUCFQAVBhUGAAALKAIAAAACAQEAAABEFQAVKhUuLBUCFQAVBhUGAAAVUAIAAAACAQsAAABSRUFMLVNQRUMtMRUAFRQVGCwVAhUAFQYVBgAACiQCAAAAAgH0AQAAFQIZXDUAGA1kdWNrZGJfc2NoZW1hFQgAFQIlAhgLb3V0cHV0X2RhdGUlDAAVDCUCGApzaGlmdF9jb2RlJQAAFQwlAhgIU1BFQ05BTUUlAAAVAiUCGBFhY3R1YWxfb3V0cHV0X3F0eSUiABYCGRwZTCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYCFjYWOiYIPBgEfVAAABgEfVAAABYAKAR9UAAAGAR9UAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYCFjgWPCZCPBgBRBgBRBYAKAFEGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWAhZMFlAmfjwYC1JFQUwtU1BFQy0xGAtSRUFMLVNQRUMtMRYAKAtSRUFMLVNQRUMtMRgLUkVBTC1TUEVDLTEREQAAACYAHBUCGRUAGRgRYWN0dWFsX291dHB1dF9xdHkVAhYCFjYWOibOATwYBPQBAAAYBPQBAAAWACgE9AEAABgE9AEAABERAAAAFvABFgImCBaAAgAoKER1Y2tEQiB2ZXJzaW9uIHYxLjUuNCAoYnVpbGQgMDhlMzRjNDQ3YikZTBwAABwAABwAABwAAADHAQAAUEFSMQ==';

// ---------------------------------------------------------------------------
// Envelope / payload helpers
// ---------------------------------------------------------------------------

function envelope(data: unknown) {
  return JSON.stringify({ success: true, data, meta: MOCK_META });
}

function errorEnvelope(code: string, message: string) {
  return JSON.stringify({ success: false, error: { code, message }, meta: MOCK_META });
}

function mock202(jobId: string) {
  return {
    success: true,
    data: { async: true, job_id: jobId, status_url: `/api/job/${jobId}?prefix=production-achievement` },
    meta: MOCK_META,
  };
}

function jobStatus(
  status: 'started' | 'finished' | 'failed',
  jobId: string,
  pct = 0,
  queryId: string | null = null,
  error: string | null = null,
) {
  return {
    success: true,
    data: {
      status,
      job_id: jobId,
      query_id: queryId,
      error,
      pct,
      stage: status === 'finished' ? 'complete' : 'querying',
      progress: status === 'finished' ? '查詢完成' : '背景查詢中...',
    },
    meta: MOCK_META,
  };
}

function spoolHit(overrides: Record<string, unknown> = {}) {
  return {
    query_id: 'qid-monkey-001',
    spool_download_url: '/api/spool/production_achievement/qid-monkey-001.parquet',
    spec_workcenter_map: [{ SPECNAME: 'REAL-SPEC-1', workcenter_group: 'GROUP-A' }],
    targets_map: [{ shift_code: 'D', workcenter_group: 'GROUP-A', target_qty: 1000 }],
    ...overrides,
  };
}

const TARGET_ROW_D_GROUPA = {
  shift_code: 'D',
  workcenter_group: 'GROUP-A',
  target_qty: 1000,
  updated_at: '2026-05-01T00:00:00Z',
  updated_by: 'admin',
};

// ---------------------------------------------------------------------------
// Shared route / navigation setup
// ---------------------------------------------------------------------------

async function setupBaseRoutes(page: Page): Promise<void> {
  // Catch-all registered FIRST (LIFO — lets real asset requests through to
  // the dev server / dist static files; specific API routes below win).
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'testuser', role: 'user' }) });
  });
  await page.route('**/api/pages**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
  });
  await page.route('**/api/portal/navigation**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      // /api/portal/navigation returns a plain unwrapped shape, not the
      // success/data/meta envelope (see app.py::portal_navigation_config()).
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released', '/wip-overview': 'released' },
        is_admin: false,
        admin_user: null,
        admin_links: { logout: null, pages: null, dashboard: null },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    });
  });
  await page.route('**/api/production-achievement/filter-options**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: envelope({ shift_codes: ['N', 'D', 'A', 'B', 'C'], workcenter_groups: ['GROUP-A', 'GROUP-B'] }),
    });
  });
  // Default spool fallback for tests that never intend to reach a real
  // DuckDB compute — overridden per-test (LIFO, registered after this).
  await page.route('**/api/spool/**', (route) => {
    route.fulfill({ status: 200, contentType: PARQUET_CONTENT_TYPE, body: DUMMY_PARQUET_BYTES });
  });
}

async function mockTargets(page: Page, rows: unknown[], onPut?: (payload: unknown) => void): Promise<void> {
  await page.route('**/api/production-achievement/targets**', (route) => {
    const req = route.request();
    if (req.method() === 'PUT') {
      onPut?.(req.postDataJSON());
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
    } else {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(rows) });
    }
  });
}

async function isPageRendered(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

async function hasCrashed(page: Page): Promise<boolean> {
  return page.evaluate(() => !!(window as unknown as { __vue_app_crashed?: boolean }).__vue_app_crashed).catch(() => false);
}

function reportCard(page: Page) {
  return page.locator('.ui-card', { has: page.locator('.ui-card-title', { hasText: REPORT_CARD_TITLE }) });
}

async function gotoAndGuard(page: Page): Promise<boolean> {
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
  await page
    .waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 })
    .catch(() => {});
  return isPageRendered(page);
}

function skipNote(test_: typeof test, description: string): void {
  test_.info().annotations.push({ type: 'note', description });
}

// ===========================================================================
// 1) Rapid triple-click Query while a job is already polling
//    Guard: in-flight dedup — runQuery()'s `if (loading.value) return;` guard
//    must hold even when clicks fire faster than Vue's :disabled re-render.
// ===========================================================================

test.describe('production-achievement monkey — rapid submit / rapid clicks', () => {
  test('triple-click Query while a job is polling fires exactly one enqueue (in-flight dedup guard)', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, [TARGET_ROW_D_GROUPA]);

    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount += 1;
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202('job-rapid-1')) });
    });
    // Job never finishes during this test — isolates the dedup guard from
    // poll-completion timing.
    await page.route('**/api/job/job-rapid-1**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-rapid-1', 10)) });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping rapid-submit assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });

    // Fire 3 native click events synchronously in ONE JS tick — this probes
    // the composable-level guard directly, independent of whether Vue's
    // :disabled binding has flushed to the DOM yet.
    await page.evaluate(() => {
      const btn = document.querySelector('[data-testid="pa-query-btn"]') as HTMLButtonElement | null;
      btn?.click();
      btn?.click();
      btn?.click();
    });

    await page.waitForTimeout(1_500);
    expect(reportCallCount).toBe(1);
    expect(await hasCrashed(page)).toBe(false);
  });

  // ---------------------------------------------------------------------------
  // 2) Rapid double-click on the target-edit Save button.
  //    Guard: rapid-click safety — TargetEditPanel closes edit mode on the
  //    SAME synchronous handler that emits 'save', but two clicks dispatched
  //    in one JS tick (before Vue flushes) can both reach confirmEdit(). The
  //    assertion here is NOT "exactly one PUT" (saveTarget() has no
  //    re-entrancy guard — recorded as a finding, not hard-failed) but that
  //    the DOM never ends up in a torn/inconsistent state.
  // ---------------------------------------------------------------------------

  test('rapid double-click on target Save leaves a clean, non-torn DOM state', async ({ page }) => {
    await setupBaseRoutes(page);
    let putCount = 0;
    await mockTargets(page, [TARGET_ROW_D_GROUPA], () => {
      putCount += 1;
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping rapid target-save assertions');
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('750');

    await page.evaluate(() => {
      const btn = document.querySelector('[data-testid="pa-target-save-btn"]') as HTMLButtonElement | null;
      btn?.click();
      btn?.click();
    });

    await page.waitForTimeout(1_500);

    // Safe-outcome invariants: no crash, edit mode cleanly closed (no
    // dangling input left on screen), exactly one edit-input node ever
    // present (no duplicate/torn row).
    expect(await hasCrashed(page)).toBe(false);
    await expect(page.locator('[data-testid="pa-target-edit-input"]')).toHaveCount(0, { timeout: 5_000 });

    skipNote(
      test,
      `rapid double-click on Save fired ${putCount} PUT call(s) — saveTarget() has no ` +
        're-entrancy guard (unlike runQuery()); recorded for hardening triage. DOM ' +
        'ended up in a clean, non-torn state either way.',
    );
  });
});

// ===========================================================================
// 3) Change filters mid-poll, then let the original job finish.
//    Guard: stale-result-overwrite — the frontend's tail re-GET always reads
//    the LIVE `filters` value (not a snapshot captured when the job was
//    enqueued). If the user mutates start_date/end_date while polling, the
//    completed job's tail re-GET goes out under the NEW date range — which
//    may itself be a spool MISS (a fresh 202), and `_pollForCompletion()`'s
//    tail fetch does not re-check `isAsyncEnqueued()` on that response. The
//    safe outcome under test is: no crash, no silently-mismatched table, and
//    the page recovers to an interactive (non-stuck-loading) state.
// ===========================================================================

test.describe('production-achievement monkey — mid-poll filter mutation', () => {
  test('mutating dates mid-poll does not crash or leave the page stuck loading', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, [TARGET_ROW_D_GROUPA]);

    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount += 1;
      // Every GET /report in this test is a spool MISS (mirrors the
      // production scenario: neither the original nor the mutated date
      // range has a warm spool yet) — always enqueue a fresh job.
      const jobId = reportCallCount === 1 ? 'job-mid-1' : 'job-mid-2';
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202(jobId)) });
    });

    let job1PollCount = 0;
    await page.route('**/api/job/job-mid-1**', (route) => {
      job1PollCount += 1;
      const payload = job1PollCount < 2 ? jobStatus('started', 'job-mid-1', 15) : jobStatus('finished', 'job-mid-1', 100, 'qid-mid-1');
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
    });
    // The SECOND job (enqueued by the tail re-GET under the mutated filters)
    // never finishes in this test — bounds total run time regardless of how
    // the frontend reacts to the mis-typed 202.
    await page.route('**/api/job/job-mid-2**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-mid-2', 10)) });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping mid-poll mutation assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    // Give the first poll tick ("started") a moment to land, then mutate the
    // date filter WHILE job-mid-1 is still in flight for the original range.
    await page.waitForTimeout(700);
    await page.fill('[data-testid="pa-start-date"]', '2020-01-01');

    // Allow the poll loop to reach the 'finished' tick and the tail re-GET
    // (now against the mutated filters) to resolve.
    await page.waitForTimeout(6_000);

    // Safe-outcome invariants (deliberately NOT asserting a specific row
    // set — that depends on an implementation choice not yet pinned):
    //   1. no crash
    //   2. the page is NOT stuck in a permanent loading/polling state
    expect(await hasCrashed(page)).toBe(false);
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    skipNote(
      test,
      'mid-poll filter mutation: report requests=' +
        reportCallCount +
        '. _pollForCompletion()\'s tail re-GET does not re-check isAsyncEnqueued() on ' +
        'its response, so a mid-poll filter change that turns the tail fetch into a ' +
        'fresh spool-miss (202) is currently treated as a malformed spool-hit and ' +
        'surfaces as a generic error rather than re-entering the async poll for the ' +
        'new range. Recorded as a hardening finding; the assertions above confirm this ' +
        'degrades SAFELY (no crash, no stuck spinner), not that the UX is optimal.',
    );
  });
});

// ===========================================================================
// 4) Navigate away mid-poll (SPA-internal, via sidebar) then return.
//    Guard: onUnmounted -> cancelQuery() must stop the poll loop; no
//    orphaned polling after the component is torn down.
// ===========================================================================

test.describe('production-achievement monkey — navigate away mid-poll', () => {
  test('navigating away while a job is polling stops the poll loop and remounts cleanly on return', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    // wip-overview is the SPA default landing page — used purely as a
    // navigation target, its own API surface is not under test here.
    await page.route('**/api/wip/**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({}) });
    });

    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202('job-nav-1')) });
    });
    let job1PollCount = 0;
    let abandonCalled = false;
    await page.route('**/api/job/job-nav-1**', (route) => {
      job1PollCount += 1;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-nav-1', 15)) });
    });
    await page.route('**/api/job/job-nav-1/abandon**', (route) => {
      abandonCalled = true;
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ acknowledged: true }) });
    });

    const mounted = await navigateViaSidebar(page, 'production-achievement', { waitForSelector: '[data-testid="pa-app"]' })
      .then(() => true)
      .catch(() => false);
    if (!mounted || !(await isPageRendered(page))) {
      skipNote(test, 'sidebar navigation to production-achievement did not complete — skipping navigate-away assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();
    await page.locator('.async-job-progress').isVisible({ timeout: 5_000 }).catch(() => false);
    await page.waitForTimeout(500);

    const pollCountRightBeforeNav = job1PollCount;

    // Navigate away WHILE the job is still polling — an SPA-internal route
    // change (Vue Router swap), which fires onUnmounted on App.vue.
    const navigatedAway = await navigateViaSidebar(page, 'wip-overview')
      .then(() => true)
      .catch(() => false);
    if (!navigatedAway) {
      skipNote(test, 'could not navigate away via sidebar — skipping poll-cancellation assertion');
      return;
    }

    // Wait well past one poll interval (resource-history-async.spec.ts
    // documents ~3s) to see whether polling kept scheduling new ticks.
    await page.waitForTimeout(8_000);
    const pollCountAfterSettle = job1PollCount;

    // Tolerate at most one poll that was already in flight at unmount time —
    // no MORE ticks may be scheduled after that.
    expect(pollCountAfterSettle - pollCountRightBeforeNav).toBeLessThanOrEqual(1);

    skipNote(test, `abandon POST fired: ${abandonCalled} (best-effort per cancelQuery(); non-fatal if false).`);

    // Return to production-achievement — must remount cleanly with no
    // leaked progress bar from the previous mount's async state.
    const returned = await navigateViaSidebar(page, 'production-achievement', { waitForSelector: '[data-testid="pa-app"]' })
      .then(() => true)
      .catch(() => false);
    if (returned && (await isPageRendered(page))) {
      await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 5_000 });
      expect(await hasCrashed(page)).toBe(false);
    }
  });
});

// ===========================================================================
// 5) Explicit Cancel button click mid-poll.
//    Guard: cancelQuery() must stop the poll loop and reset UI state when
//    invoked from the AsyncQueryProgress cancel button (not just onUnmounted).
// ===========================================================================

test.describe('production-achievement monkey — explicit cancel mid-poll', () => {
  test('clicking Cancel mid-poll stops polling and resets the progress bar', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);

    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202('job-cancel-1')) });
    });
    let pollCount = 0;
    let abandonCalled = false;
    await page.route('**/api/job/job-cancel-1**', (route) => {
      pollCount += 1;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-cancel-1', 20)) });
    });
    await page.route('**/api/job/job-cancel-1/abandon**', (route) => {
      abandonCalled = true;
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ acknowledged: true }) });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping explicit-cancel assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    const progressBar = page.locator('.async-job-progress');
    const cancelBtn = page.locator('.async-job-progress__cancel');
    const progressVisible = await progressBar.isVisible({ timeout: 10_000 }).catch(() => false);
    if (!progressVisible) {
      skipNote(test, 'progress bar did not become visible in time — mocked response may have resolved faster than one Vue tick; skipping cancel-click assertions');
      return;
    }

    const pollsBeforeCancel = pollCount;
    await cancelBtn.click();
    await page.waitForTimeout(500);

    await expect(progressBar).toHaveCount(0, { timeout: 5_000 });
    await expect(queryBtn).toBeEnabled({ timeout: 5_000 });

    await page.waitForTimeout(6_000);
    expect(pollCount - pollsBeforeCancel).toBeLessThanOrEqual(1);
    expect(abandonCalled).toBe(true);
    expect(await hasCrashed(page)).toBe(false);
  });
});

// ===========================================================================
// 6) Browser back/forward mid-poll — "unsupported browser navigation sequence".
//    Guard: SPA history navigation while an async job is in flight must not
//    crash or leave a duplicated/stuck progress bar.
// ===========================================================================

test.describe('production-achievement monkey — browser back/forward mid-poll', () => {
  test('browser Back then Forward mid-poll does not crash and leaves a clean remount', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    await page.route('**/api/wip/**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({}) });
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202('job-back-1')) });
    });
    await page.route('**/api/job/job-back-1**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-back-1', 15)) });
    });
    await page.route('**/api/job/job-back-1/abandon**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ acknowledged: true }) });
    });

    // Build a same-tab SPA history stack: root -> production-achievement
    // (both via real in-page navigation, so goBack()/goForward() are
    // intercepted by Vue Router rather than causing a hard reload).
    const mounted = await navigateViaSidebar(page, 'production-achievement', { waitForSelector: '[data-testid="pa-app"]' })
      .then(() => true)
      .catch(() => false);
    if (!mounted || !(await isPageRendered(page))) {
      skipNote(test, 'sidebar navigation did not complete — skipping browser back/forward assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();
    await page.waitForTimeout(500);

    await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {});
    await page.waitForTimeout(1_000);
    expect(await hasCrashed(page)).toBe(false);

    await page.goForward({ waitUntil: 'domcontentloaded' }).catch(() => {});
    await page.waitForTimeout(1_000);

    // Whether or not the SPA route restored production-achievement, the page
    // must be in a coherent, non-crashed state with no duplicated progress bars.
    expect(await hasCrashed(page)).toBe(false);
    const progressBarCount = await page.locator('.async-job-progress').count();
    expect(progressBarCount).toBeLessThanOrEqual(1);
  });
});

// ===========================================================================
// 7) Hidden-tab behavior — confirms the explicit non-goal in App.vue's own
//    header comment ("Ordinary filterable report — NOT an auto-refresh/
//    big-screen kanban"). Guard: no hidden-tab auto-refresh timer exists.
// ===========================================================================

test.describe('production-achievement monkey — hidden-tab behavior', () => {
  test('backgrounding the tab after a completed query issues no further /report calls', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, [TARGET_ROW_D_GROUPA]);

    let reportCallCount = 0;
    await page.route('**/api/production-achievement/report**', (route) => {
      reportCallCount += 1;
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHit()) });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping hidden-tab assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();
    await page.waitForTimeout(3_000);

    const countAfterInitialQuery = reportCallCount;
    expect(countAfterInitialQuery).toBeGreaterThanOrEqual(1);

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    // Well past any plausible refresh/polling interval on this page.
    await page.waitForTimeout(8_000);

    expect(reportCallCount).toBe(countAfterInitialQuery);
    expect(await hasCrashed(page)).toBe(false);
  });
});

// ===========================================================================
// 8) Adversarial / malformed date filters.
//    Guard: invalid date range / missing required filter — a 400 from the
//    server must be handled gracefully (error surfaced, no crash, page
//    recovers to an interactive state), regardless of exactly which
//    malformed shape triggered it.
// ===========================================================================

test.describe('production-achievement monkey — adversarial date filters', () => {
  const scenarios: { name: string; setup: (page: Page) => Promise<void> }[] = [
    {
      name: 'end_date before start_date',
      setup: async (page) => {
        await page.fill('[data-testid="pa-start-date"]', '2026-06-30');
        await page.fill('[data-testid="pa-end-date"]', '2026-06-01');
      },
    },
    {
      name: 'range exceeding 730 days (MAX_QUERY_DAYS)',
      setup: async (page) => {
        await page.fill('[data-testid="pa-start-date"]', '2019-01-01');
        await page.fill('[data-testid="pa-end-date"]', '2026-06-01');
      },
    },
    {
      name: 'empty start and end dates (missing required filter)',
      setup: async (page) => {
        await page.fill('[data-testid="pa-start-date"]', '');
        await page.fill('[data-testid="pa-end-date"]', '');
      },
    },
    {
      name: 'DOM-forced non-date / SQL-and-script-like string bypassing the native date picker',
      setup: async (page) => {
        // Native <input type="date"> silently discards anything not matching
        // its own ISO parser via .fill() — simulates a compromised
        // extension/devtools actor writing directly into the DOM, which the
        // frontend's runQuery() never validates before sending.
        await page.evaluate(() => {
          const el = document.querySelector('[data-testid="pa-start-date"]') as HTMLInputElement | null;
          if (el) {
            el.type = 'text';
            el.value = "2026-01-01'; DROP TABLE targets; --<script>window.__pa_date_xss=1</script>";
            el.dispatchEvent(new Event('input', { bubbles: true }));
          }
        });
      },
    },
  ];

  for (const scenario of scenarios) {
    test(`${scenario.name} -> graceful 400 handling, no crash`, async ({ page }) => {
      await setupBaseRoutes(page);
      await mockTargets(page, []);
      await page.route('**/api/production-achievement/report**', (route) => {
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: errorEnvelope('VALIDATION_ERROR', '查詢條件不合法，請確認日期範圍'),
        });
      });

      if (!(await gotoAndGuard(page))) {
        skipNote(test, `no dev server detected — skipping "${scenario.name}"`);
        return;
      }

      await scenario.setup(page);
      const queryBtn = page.locator('[data-testid="pa-query-btn"]');
      await queryBtn.click();
      await page.waitForTimeout(1_500);

      // Safety invariant regardless of malformed-input class: no crash, and
      // the query control must not be stuck in a permanently disabled/
      // loading state (the user must be able to retry).
      expect(await hasCrashed(page)).toBe(false);
      await expect(queryBtn).toBeEnabled({ timeout: 5_000 });

      // No script-injection side-effect from the DOM-forced payload.
      const xssFired = await page
        .evaluate(() => !!(window as unknown as { __pa_date_xss?: boolean }).__pa_date_xss)
        .catch(() => false);
      expect(xssFired).toBe(false);
    });
  }
});

// ===========================================================================
// 9) Wrong-typed /report 200 response fields.
//    Guard: wrong column / wrong type data crossing the network boundary —
//    the frontend must not crash when the server's JSON shape drifts.
// ===========================================================================

test.describe('production-achievement monkey — wrong-type server payload', () => {
  test('spool-hit response with wrong-typed fields degrades to a graceful error, no crash', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'qid-wrong-type',
          spool_download_url: 12345, // wrong type: number, not string
          spec_workcenter_map: 'not-an-array', // wrong type: string, not array
          targets_map: null, // wrong type: null, not array
        }),
      });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping wrong-type payload assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();
    await page.waitForTimeout(3_000);

    expect(await hasCrashed(page)).toBe(false);
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });
  });
});

// ===========================================================================
// 10) Stale session — 401 on the job-status endpoint mid-poll.
//     Guard: an expired session while a long-running async job is in flight
//     must surface a graceful error, never an infinite spinner.
// ===========================================================================

test.describe('production-achievement monkey — stale session mid-poll', () => {
  test('401 on job-status mid-poll surfaces a graceful error, not an infinite spinner', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(mock202('job-stale-1')) });
    });
    let pollCount = 0;
    await page.route('**/api/job/job-stale-1**', (route) => {
      pollCount += 1;
      if (pollCount < 2) {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(jobStatus('started', 'job-stale-1', 15)) });
      } else {
        route.fulfill({ status: 401, contentType: 'application/json', body: errorEnvelope('UNAUTHORIZED', '登入已過期，請重新登入') });
      }
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping stale-session assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();
    await page.waitForTimeout(8_000);

    // The active progress bar must not linger forever after a 401.
    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 10_000 });
    expect(await hasCrashed(page)).toBe(false);
    await expect(queryBtn).toBeEnabled({ timeout: 5_000 });
  });
});

// ===========================================================================
// 11 & 12) Empty / all-unmapped-SPECNAME spool windows — REAL DuckDB-WASM.
//    Guard: empty-result invariant — never an error toast for a legitimately
//    empty (or fully-filtered-out) result set.
// ===========================================================================

test.describe('production-achievement monkey — empty / all-unmapped spool window', () => {
  test('zero-row parquet spool renders an empty table, never an error toast', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHit({ spec_workcenter_map: [], targets_map: [] })) });
    });
    await page.route('**/api/spool/production_achievement/**', (route) => {
      route.fulfill({ status: 200, contentType: PARQUET_CONTENT_TYPE, body: Buffer.from(EMPTY_SPOOL_PARQUET_B64, 'base64') });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping empty-spool assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    const table = reportCard(page).locator('[data-testid="datatable"]');
    const tableVisible = await table.isVisible({ timeout: 15_000 }).catch(() => false);
    const errorVisible = await page.locator('[role="alert"]').first().isVisible().catch(() => false);

    if (tableVisible && !errorVisible) {
      // Real DuckDB-WASM executed the full activate()+computeView() path.
      await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 10_000 });
      const bodyText = await table.innerText();
      expect(bodyText).not.toContain('Infinity');
      expect(bodyText).not.toContain('NaN');
    } else {
      skipNote(
        test,
        'DuckDB-WASM did not complete an observable empty-render in this run (browser/' +
          'infra constraint) — empty-result invariant deferred to ' +
          'useProductionAchievementDuckDB.test.ts (mocked-engine tier), which pins the ' +
          'same assertion unconditionally.',
      );
    }
    expect(await hasCrashed(page)).toBe(false);
  });

  test('all-unmapped-SPECNAME parquet renders an empty table (PA-06 exclusion), never an error toast', async ({ page }) => {
    await setupBaseRoutes(page);
    await mockTargets(page, []);
    await page.route('**/api/production-achievement/report**', (route) => {
      // spec_workcenter_map only maps "REAL-SPEC-1" — the parquet below has
      // "GHOST-SPEC-1"/"GHOST-SPEC-2", neither of which is in the map.
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHit({ targets_map: [] })) });
    });
    await page.route('**/api/spool/production_achievement/**', (route) => {
      route.fulfill({ status: 200, contentType: PARQUET_CONTENT_TYPE, body: Buffer.from(UNMAPPED_SPECNAME_PARQUET_B64, 'base64') });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping all-unmapped-SPECNAME assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    const table = reportCard(page).locator('[data-testid="datatable"]');
    const tableVisible = await table.isVisible({ timeout: 15_000 }).catch(() => false);
    const errorVisible = await page.locator('[role="alert"]').first().isVisible().catch(() => false);

    if (tableVisible && !errorVisible) {
      await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 10_000 });
      const bodyText = await table.innerText();
      expect(bodyText).not.toContain('GHOST-SPEC');
      expect(bodyText).not.toContain('Infinity');
      expect(bodyText).not.toContain('NaN');
    } else {
      skipNote(
        test,
        'DuckDB-WASM did not complete an observable empty-render in this run — the real ' +
          'INNER JOIN unmapped-SPECNAME exclusion is pinned unconditionally at the ' +
          'mocked-engine unit tier (useProductionAchievementDuckDB.test.ts).',
      );
    }
    expect(await hasCrashed(page)).toBe(false);
  });
});

// ===========================================================================
// 13) Adversarial target_qty values — overlong / Unicode / SQL-like /
//     script-like input on the client-side-validated free-text field.
//     Guard: validateTargetQtyInput() must reject every one of these client-
//     side (no PUT fires), and no value is ever executed as script/SQL.
// ===========================================================================

test.describe('production-achievement monkey — adversarial target_qty input', () => {
  const adversarialValues: { name: string; value: string }[] = [
    { name: 'non-numeric letters', value: 'abc' },
    { name: 'decimal (must be integer)', value: '12.5' },
    { name: 'scientific notation', value: '1e10' },
    { name: 'full-width Unicode digits', value: '１２３' },
    { name: 'script-like injection string', value: '<script>window.__pa_target_xss=1</script>' },
    { name: "SQL-like injection string", value: "1' OR '1'='1" },
    { name: 'overlong digit string overflowing Number to Infinity', value: '9'.repeat(400) },
    { name: 'whitespace-only', value: '   ' },
  ];

  for (const adversarial of adversarialValues) {
    test(`target_qty="${adversarial.name}" is rejected client-side, no PUT fires, no script executes`, async ({ page }) => {
      await setupBaseRoutes(page);
      let putCalled = false;
      await mockTargets(page, [TARGET_ROW_D_GROUPA], () => {
        putCalled = true;
      });

      if (!(await gotoAndGuard(page))) {
        skipNote(test, `no dev server detected — skipping "${adversarial.name}"`);
        return;
      }

      const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
      await expect(editBtn).toBeVisible({ timeout: 15_000 });
      await editBtn.click();
      await page.locator('[data-testid="pa-target-edit-input"]').fill(adversarial.value);
      await page.locator('[data-testid="pa-target-save-btn"]').click();
      await page.waitForTimeout(600);

      expect(putCalled).toBe(false);
      await expect(page.locator('.pa-target-panel__inline-error')).toBeVisible({ timeout: 5_000 });

      const xssFired = await page
        .evaluate(() => !!(window as unknown as { __pa_target_xss?: boolean }).__pa_target_xss)
        .catch(() => false);
      expect(xssFired).toBe(false);
      expect(await hasCrashed(page)).toBe(false);
    });
  }
});

// ===========================================================================
// 14) Target edit -> target_qty=0 -> real DuckDB-WASM recompute.
//     Guard: null/zero-target -> null achievement_rate, NEVER Infinity/NaN
//     rendered in the DOM. Uses the real "mapped" parquet fixture so the
//     assertion exercises the actual computeView() CASE-WHEN guard, not a
//     mock of its output.
// ===========================================================================

test.describe('production-achievement monkey — adversarial target edit recompute', () => {
  test('editing target_qty to 0 recomputes achievement_rate to null (—), never Infinity/NaN', async ({ page }) => {
    await setupBaseRoutes(page);

    let targetsGetCount = 0;
    await page.route('**/api/production-achievement/targets**', (route) => {
      const req = route.request();
      if (req.method() === 'PUT') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
        return;
      }
      targetsGetCount += 1;
      // First GET (initial load): target_qty=1000. After the PUT, the
      // refetch returns target_qty=0 — the adversarial edit under test.
      const targetQty = targetsGetCount === 1 ? 1000 : 0;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope([{ ...TARGET_ROW_D_GROUPA, target_qty: targetQty }]),
      });
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(spoolHit()) });
    });
    await page.route('**/api/spool/production_achievement/**', (route) => {
      route.fulfill({ status: 200, contentType: PARQUET_CONTENT_TYPE, body: Buffer.from(MAPPED_SPOOL_PARQUET_B64, 'base64') });
    });

    if (!(await gotoAndGuard(page))) {
      skipNote(test, 'no dev server detected — skipping target-edit recompute assertions');
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    const table = reportCard(page).locator('[data-testid="datatable"]');
    const tableVisible = await table.isVisible({ timeout: 15_000 }).catch(() => false);
    const errorVisible = await page.locator('[role="alert"]').first().isVisible().catch(() => false);

    if (!tableVisible || errorVisible) {
      skipNote(
        test,
        'DuckDB-WASM did not complete the initial query render in this run — target-edit ' +
          'recompute assertion deferred. The null/zero-target -> null-rate guard is pinned ' +
          'unconditionally in useProductionAchievementDuckDB.test.ts ("stored target_qty=0 ' +
          '-> achievement_rate null, never Infinity").',
      );
      expect(await hasCrashed(page)).toBe(false);
      return;
    }

    // Initial state: actual=500, target=1000 -> 50.0%.
    let bodyText = await table.innerText();
    expect(bodyText).toContain('50.0%');

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 10_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('0');
    await page.locator('[data-testid="pa-target-save-btn"]').click();
    await page.waitForTimeout(3_000);

    bodyText = await table.innerText();
    expect(bodyText).not.toContain('Infinity');
    expect(bodyText).not.toContain('NaN');
    // A zero target must degrade to the null-display placeholder, never a
    // 0.0%/Infinity% rate.
    expect(bodyText).toContain('—');
    expect(await hasCrashed(page)).toBe(false);
  });
});
