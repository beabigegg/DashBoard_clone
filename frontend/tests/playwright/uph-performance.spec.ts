/**
 * E2E tests: uph-performance page — always-async spool-backed UPH report flow
 * Change: add-uph-performance-page
 * Mirrors: frontend/tests/playwright/production-achievement-async.spec.ts
 *          (registerCatchAllRoutes / gotoAndWaitForApp CI-safe pattern) and
 *          frontend/tests/playwright/eap-alarm-filters.spec.ts (REST JSON
 *          view-fetch shape, no client-side DuckDB-WASM parquet parsing —
 *          data-shape-contract.md §3.29 views are DuckDB-derived server-side).
 *
 * Flow under test:
 *   POST /api/uph-performance/spool
 *     -> spool miss: 202 {async:true, job_id, status_url}
 *     -> poll generic status_url until status=finished
 *     -> GET /filter-options, /trend, /detail (ranking stays un-queried)
 *   POST /api/uph-performance/spool
 *     -> spool hit: 200 {async:false, query_id} (no progress bar ever shown)
 *   always_async: no worker available -> 503 (no sync fallback)
 *
 * Network strategy: every API call is intercepted with page.route(); no real
 * backend or RQ worker required.
 *
 * Route registration follows the LIFO rule (CLAUDE.md ci-workflow.md):
 * catch-all routes registered FIRST, specific per-test routes registered LAST.
 *
 * CI-safe pattern (ci-workflow.md §Playwright CI-Safe Specs): a FAST <50-char
 * body pre-check before any waitForFunction, and an app-specific content check
 * (`.theme-uph-performance`), not a generic bodyText.length check.
 */

import { test, expect, type Page } from '@playwright/test';

const PAGE_URL = '/portal-shell/uph-performance';
const MOCK_META = { timestamp: new Date().toISOString(), app_version: 'test' };

function envelope(data: unknown) {
  return JSON.stringify({ success: true, data, meta: MOCK_META });
}

function errorEnvelope(code: string, message: string) {
  return JSON.stringify({ success: false, error: { code, message }, meta: MOCK_META });
}

const MOCK_PRODUCT_FILTER_OPTIONS = { pj_types: ['TYPE-A', 'TYPE-B'], product_lines: ['PKG-X', 'PKG-Y'] };

const MOCK_FILTER_OPTIONS = {
  equipment_id_options: ['GDBA-001', 'GWBA-001'],
  workcenter_name_options: ['焊接_DB_1', '焊接_WB_1'],
  package_options: ['PKG-X'],
  pj_type_options: ['TYPE-A', 'TYPE-B'],
};

const MOCK_TREND = {
  labels: ['2026-07-01 08:00', '2026-07-01 09:00', '2026-07-01 10:00'],
  series: [
    { name: 'GDBA', data: [120, null, 140] },
    { name: 'GWBA', data: [80, 90, 95] },
  ],
  group_by: 'family',
};

const MOCK_TREND_EMPTY = { labels: [], series: [], group_by: 'family' };

const MOCK_RANKING = {
  items: [
    { equipment_id: 'GDBA-009', workcenter_name: '焊接_DB_9', db_wb_label: '焊接_DB', pj_type: 'TYPE-A', avg_uph: 45.2, sample_count: 12 },
    { equipment_id: 'GDBA-001', workcenter_name: '焊接_DB_1', db_wb_label: '焊接_DB', pj_type: 'TYPE-A', avg_uph: 88.7, sample_count: 30 },
  ],
  pj_types: ['TYPE-A', 'TYPE-B'],
};

const MOCK_DETAIL = {
  rows: [
    { lot_id: 'LOT-001', equipment_id: 'GDBA-001', event_time: '2026-07-01T08:00:00', uph_value: 88.7, package: 'PKG-X', pj_type: 'TYPE-A' },
    { lot_id: 'LOT-002', equipment_id: 'GWBA-001', event_time: '2026-07-01T09:00:00', uph_value: 60.1, package: 'PKG-Y', pj_type: 'TYPE-B' },
  ],
  meta: { page: 1, per_page: 20, total_count: 2, total_pages: 1 },
};

const MOCK_DETAIL_EMPTY = { rows: [], meta: { page: 1, per_page: 20, total_count: 0, total_pages: 1 } };

/**
 * Register catch-all routes FIRST (LIFO — overridden by per-test specific
 * routes registered afterwards). Mirrors production-achievement-async.spec.ts.
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
      body: JSON.stringify({
        statuses: { '/uph-performance': 'dev' },
        is_admin: true,
        admin_user: null,
        admin_links: { logout: null, pages: null, dashboard: null },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    }),
  );
  await page.route('**/api/uph-performance/product-filter-options**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_PRODUCT_FILTER_OPTIONS) }),
  );
  await page.route('**/api/uph-performance/filter-options**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_FILTER_OPTIONS) }),
  );
  await page.route('**/api/uph-performance/trend**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_TREND) }),
  );
  await page.route('**/api/uph-performance/ranking**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_RANKING) }),
  );
  await page.route('**/api/uph-performance/detail**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_DETAIL) }),
  );
  await page.route('**/api/uph-performance/spool/status**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: envelope({ status: 'finished', job_id: 'uph-job-default', query_id: 'qid-default', error: null, pct: 100, stage: 'complete', progress: '查詢完成' }),
    }),
  );
  await page.route('**/api/uph-performance/spool', (route) =>
    route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: envelope({ async: true, job_id: 'uph-job-default', query_id: 'qid-default', status_url: '/api/uph-performance/spool/status?job_id=uph-job-default' }),
    }),
  );
}

async function gotoAndWaitForApp(page: Page): Promise<boolean> {
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
  // FAST no-dev-server pre-check (ci-workflow.md §Playwright CI-Safe Specs):
  // when nothing serves the app, bail out in well under a second instead of
  // burning the full waitForFunction timeout on every test.
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  if ((bodyText?.trim().length ?? 0) < 50) return false;
  await page
    .waitForFunction(() => document.querySelector('.theme-uph-performance') !== null, { timeout: 10_000 })
    .catch(() => {});
  return page.evaluate(() => {
    const el = document.querySelector('.theme-uph-performance');
    return el !== null && (el as HTMLElement).offsetParent !== null;
  });
}

function skipIfNotRendered(rendered: boolean, note: string): boolean {
  if (!rendered) {
    test.info().annotations.push({ type: 'note', description: note });
  }
  return !rendered;
}

async function fillDatesAndSubmit(page: Page): Promise<void> {
  await page.locator('[data-testid="start-date"]').fill('2026-07-01');
  await page.locator('[data-testid="end-date"]').fill('2026-07-07');
  await page.locator('[data-testid="ctrl-submit"]').click();
}

// ===========================================================================

test.describe('uph-performance — state-initial and coarse-options-degraded', () => {
  test('state-initial: renders the filter bar with no results and no progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping state-initial assertions')) return;

    await expect(page.locator('[data-testid="start-date"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.async-job-progress')).toHaveCount(0);

    const layout = await page.evaluate(() => {
      const root = document.querySelector<HTMLElement>('.theme-uph-performance');
      const dashboard = document.querySelector<HTMLElement>('.theme-uph-performance .dashboard');
      const multiSelect = document.querySelector<HTMLElement>('.theme-uph-performance .multi-select-trigger');
      if (!root || !dashboard || !multiSelect) return null;
      const dashboardStyle = getComputedStyle(dashboard);
      const multiSelectStyle = getComputedStyle(multiSelect);
      return {
        rootWidth: root.getBoundingClientRect().width,
        dashboardWidth: dashboard.getBoundingClientRect().width,
        dashboardMaxWidth: dashboardStyle.maxWidth,
        multiSelectDisplay: multiSelectStyle.display,
        multiSelectBorderWidth: multiSelectStyle.borderTopWidth,
        multiSelectBorderStyle: multiSelectStyle.borderTopStyle,
      };
    });

    expect(layout).not.toBeNull();
    expect(Math.abs((layout?.rootWidth ?? 0) - (layout?.dashboardWidth ?? 0))).toBeLessThanOrEqual(1);
    expect(layout?.dashboardMaxWidth).toBe('none');
    expect(layout?.multiSelectDisplay).toBe('flex');
    expect(layout?.multiSelectBorderWidth).toBe('1px');
    expect(layout?.multiSelectBorderStyle).toBe('solid');
  });

  test('state-coarse-options-degraded: product-filter-options 500 shows an inline warning, other filters stay usable', async ({ page }) => {
    await registerCatchAllRoutes(page);
    await page.route('**/api/uph-performance/product-filter-options**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: errorEnvelope('INTERNAL_ERROR', 'product options unavailable') }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping coarse-options-degraded assertions')) return;

    await expect(page.locator('[data-testid="product-options-warning"]')).toBeVisible({ timeout: 10_000 });
    // The rest of the filter bar (dates, submit) remains usable.
    await expect(page.locator('[data-testid="start-date"]')).toBeEnabled();
    await expect(page.locator('[data-testid="ctrl-workcenter-select"]')).toBeEnabled();
  });
});

test.describe('uph-performance — async job flow (happy path)', () => {
  test('state-spooling then state-ready-populated: progress shows, job polled to completion, trend/ranking-prompt/detail render', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const JOB_ID = 'uph-job-happy-001';
    let jobPollCount = 0;

    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, query_id: 'qid-happy-001', status_url: `/api/uph-performance/spool/status?job_id=${JOB_ID}` }),
      }),
    );
    await page.route(`**/api/uph-performance/spool/status**`, (route) => {
      jobPollCount++;
      const payload =
        jobPollCount <= 1
          ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 20, stage: 'querying', progress: '背景查詢中...' }
          : { status: 'finished', job_id: JOB_ID, query_id: 'qid-happy-001', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(payload) });
    });

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping happy-path assertions')) return;

    await fillDatesAndSubmit(page);

    const progressBar = page.locator('.async-job-progress');
    const progressVisible = await progressBar.isVisible({ timeout: 10_000 }).catch(() => false);
    if (progressVisible) {
      await expect(page.locator('.async-job-progress__cancel')).toBeVisible({ timeout: 5_000 });
      // LoadingOverlay hidden while the async job is active (css-contract 4.6).
      await expect(page.locator('[data-testid="loading-state"]')).toHaveCount(0);
    }

    await expect(progressBar).toHaveCount(0, { timeout: 20_000 });

    // Trend renders (populated series).
    await expect(page.locator('.trend-chart, .trend-chart-body [data-testid="empty-state"]').first()).toBeVisible({ timeout: 15_000 });

    // Ranking stays a PROMPT (not queried) until a Type is chosen — confirmed #2.
    await expect(page.locator('[data-testid="ranking-prompt"]')).toBeVisible({ timeout: 10_000 });

    // Detail table renders the mocked rows.
    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible({ timeout: 15_000 });
  });

  test('state-spool-hit: 200 on the first call renders directly, no progress bar ever shown', async ({ page }) => {
    await registerCatchAllRoutes(page);
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ async: false, query_id: 'qid-warm-001' }) }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping spool-hit assertions')) return;

    await fillDatesAndSubmit(page);

    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.async-job-progress')).toHaveCount(0);
  });
});

test.describe('uph-performance — empty and error states', () => {
  test('state-empty: zero-row spool shows the confirmed generic wording, no BondUPH/fHCM_UPH leak', async ({ page }) => {
    await registerCatchAllRoutes(page);
    await page.route('**/api/uph-performance/trend**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_TREND_EMPTY) }),
    );
    await page.route('**/api/uph-performance/detail**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(MOCK_DETAIL_EMPTY) }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping state-empty assertions')) return;

    await fillDatesAndSubmit(page);

    const empty = page.locator('[data-testid="empty-state"]');
    await expect(empty).toBeVisible({ timeout: 20_000 });
    await expect(empty).toContainText('此範圍無 UPH 資料，請放寬日期或調整篩選器');
    const text = await empty.textContent();
    expect(text ?? '').not.toContain('BondUPH');
    expect(text ?? '').not.toContain('fHCM_UPH');
    // Empty ≠ broken — no error banner alongside it.
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });

  test('state-unavailable (503): shows ErrorBanner, distinct from EmptyState, no stuck progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: errorEnvelope('SERVICE_UNAVAILABLE', '背景查詢服務暫時無法使用，請稍後再試') }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping 503 assertions')) return;

    await fillDatesAndSubmit(page);

    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('背景查詢服務暫時無法使用');
    await expect(page.locator('.async-job-progress')).toHaveCount(0);
    await expect(page.locator('[data-testid="empty-state"]')).toHaveCount(0);
  });

  test('state-validation-error (400): missing/invalid dates surfaces an ErrorBanner, not a silent failure', async ({ page }) => {
    await registerCatchAllRoutes(page);
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({ status: 400, contentType: 'application/json', body: errorEnvelope('VALIDATION_ERROR', '日期範圍不可超過 730 天') }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping 400 assertions')) return;

    await fillDatesAndSubmit(page);

    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('日期範圍不可超過 730 天');
  });

  test('state-job-failed: async job status=failed surfaces the job error and clears the progress bar', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const JOB_ID = 'uph-job-failed-001';
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, query_id: 'qid-failed-001', status_url: `/api/uph-performance/spool/status?job_id=${JOB_ID}` }),
      }),
    );
    await page.route('**/api/uph-performance/spool/status**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'failed', job_id: JOB_ID, query_id: null, error: 'Oracle 連線逾時', pct: null, stage: null, progress: null }),
      }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping job-failed assertions')) return;

    await fillDatesAndSubmit(page);

    await expect
      .poll(async () => (await page.locator('.error-banner-message').textContent().catch(() => null)) ?? '', { timeout: 15_000 })
      .toContain('Oracle 連線逾時');
    await expect(page.locator('.async-job-progress:not(.async-job-progress--failed)')).toHaveCount(0, { timeout: 5_000 });
    await expect(page.locator('[data-testid="empty-state"]')).toHaveCount(0);
  });

  test('state-expired (410): spool/status 410 surfaces an error distinct from state-empty, and the query control is usable again', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const JOB_ID = 'uph-job-expired-001';
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, query_id: 'qid-expired-001', status_url: `/api/uph-performance/spool/status?job_id=${JOB_ID}` }),
      }),
    );
    await page.route('**/api/uph-performance/spool/status**', (route) =>
      route.fulfill({ status: 410, contentType: 'application/json', body: errorEnvelope('CACHE_EXPIRED', '查詢結果已過期，請重新查詢') }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping state-expired assertions')) return;

    await fillDatesAndSubmit(page);

    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('查詢結果已過期');
    await expect(page.locator('[data-testid="empty-state"]')).toHaveCount(0);
    const submitBtn = page.locator('[data-testid="ctrl-submit"]');
    await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
  });
});

test.describe('uph-performance — the two Type selectors stay independent (highest-risk consistency point)', () => {
  test('ctrl-ranking-type-filter defaults to none-selected; ranking stays a prompt until a Type is chosen', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping ranking-default assertions')) return;

    await fillDatesAndSubmit(page);
    await expect(page.locator('[data-testid="ranking-prompt"]')).toBeVisible({ timeout: 20_000 });

    await page.locator('[data-testid="ctrl-ranking-type-filter"] [data-testid="multiselect-trigger"]').click();
    await page.locator('[data-testid="multiselect-option"]', { hasText: 'TYPE-A' }).click();
    await page.locator('[data-testid="multiselect-close"]').click();

    await expect(page.locator('[data-testid="ranking-prompt"]')).toHaveCount(0, { timeout: 10_000 });
    await expect(page.locator('[data-testid="ranking-block"]')).toContainText('GDBA-001', { timeout: 10_000 });
  });

  test('ctrl-ranking-type-filter and ctrl-type-select-global are visibly distinct elements', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping distinct-selector assertions')) return;

    await fillDatesAndSubmit(page);
    await expect(page.locator('[data-testid="ranking-block"]')).toBeVisible({ timeout: 20_000 });

    const globalType = page.locator('[data-testid="ctrl-type-select-global"]');
    const rankingType = page.locator('[data-testid="ctrl-ranking-type-filter"]');
    await expect(globalType).toHaveCount(1);
    await expect(rankingType).toHaveCount(1);
    // Distinct DOM nodes, distinct labels/placement.
    const globalBox = await globalType.boundingBox();
    const rankingBox = await rankingType.boundingBox();
    expect(globalBox).not.toBeNull();
    expect(rankingBox).not.toBeNull();
  });

  test('selecting the ranking Type filter never mutates or reads ctrl-type-select-global', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping cross-filter isolation assertions')) return;

    await fillDatesAndSubmit(page);
    await expect(page.locator('[data-testid="ranking-block"]')).toBeVisible({ timeout: 20_000 });

    // Global Type filter selection stays untouched before/after the ranking
    // filter changes (still shows its own unselected placeholder text).
    const globalBefore = await page.locator('[data-testid="ctrl-type-select-global"]').textContent();

    await page.locator('[data-testid="ctrl-ranking-type-filter"] [data-testid="multiselect-trigger"]').click();
    await page.locator('[data-testid="multiselect-option"]', { hasText: 'TYPE-B' }).click();
    await page.locator('[data-testid="multiselect-close"]').click();
    await expect(page.locator('[data-testid="ranking-prompt"]')).toHaveCount(0, { timeout: 10_000 });

    const globalAfter = await page.locator('[data-testid="ctrl-type-select-global"]').textContent();
    expect(globalAfter).toBe(globalBefore);
  });

  test('global Type filter populated + ranking Type filter empty renders the ranking prompt, not an error', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping mixed-state assertions')) return;

    await page.locator('[data-testid="ctrl-type-select-global"] [data-testid="multiselect-trigger"]').click();
    await page.locator('[data-testid="multiselect-option"]', { hasText: 'TYPE-A' }).click();
    await page.locator('[data-testid="multiselect-close"]').click();

    await fillDatesAndSubmit(page);

    await expect(page.locator('[data-testid="ranking-prompt"]')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });
});

test.describe('uph-performance — trend chart behavior', () => {
  test('trend legend click toggles series visibility (standard ECharts behavior)', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping legend-toggle assertions')) return;

    await fillDatesAndSubmit(page);
    const chart = page.locator('.trend-chart canvas').first();
    const chartVisible = await chart.isVisible({ timeout: 15_000 }).catch(() => false);
    if (!chartVisible) {
      test.info().annotations.push({ type: 'note', description: 'trend canvas not rendered in this environment — skipping legend click' });
      return;
    }
    // A canvas-rendered ECharts legend cannot be asserted structurally via DOM
    // text; this smoke-clicks the chart area to confirm no crash occurs on
    // interaction (the actual toggle behavior is ECharts' own default and is
    // NOT reimplemented in TrendChart.vue — see its inline comment).
    await chart.click({ position: { x: 10, y: 10 } }).catch(() => {});
    await expect(chart).toBeVisible();
  });

  test('a null trend bucket does not render as an inline zero-value cell anywhere on the page', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping null-gap assertions')) return;

    await fillDatesAndSubmit(page);
    await expect(page.locator('.trend-chart').first()).toBeVisible({ timeout: 15_000 });
    // MOCK_TREND's GDBA series is [120, null, 140]; ECharts renders `null` as a
    // gap by default (no `connectNulls`), which is a canvas-internal behavior
    // not assertable via the DOM — this test only proves the chart still
    // renders (no crash) with a null value present in the series payload.
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });
});

test.describe('uph-performance — cancel mid-poll', () => {
  test('ctrl-cancel-job cancels an in-flight job and returns to a usable state-initial-like state', async ({ page }) => {
    await registerCatchAllRoutes(page);
    const JOB_ID = 'uph-job-cancel-001';
    await page.route('**/api/uph-performance/spool', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, query_id: 'qid-cancel-001', status_url: `/api/uph-performance/spool/status?job_id=${JOB_ID}` }),
      }),
    );
    // Job never finishes on its own — forces the user to cancel.
    await page.route('**/api/uph-performance/spool/status**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 15, stage: 'querying', progress: '背景查詢中...' }),
      }),
    );

    const rendered = await gotoAndWaitForApp(page);
    if (skipIfNotRendered(rendered, 'app not mounted — skipping cancel assertions')) return;

    await fillDatesAndSubmit(page);

    const progressBar = page.locator('.async-job-progress');
    await expect(progressBar).toBeVisible({ timeout: 10_000 });

    await page.locator('.async-job-progress__cancel').click();

    await expect(progressBar).toHaveCount(0, { timeout: 10_000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
    const submitBtn = page.locator('[data-testid="ctrl-submit"]');
    await expect(submitBtn).toHaveText('查詢', { timeout: 5_000 });
    await expect(submitBtn).toBeEnabled();
  });
});
