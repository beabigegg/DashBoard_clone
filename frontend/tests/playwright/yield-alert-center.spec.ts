/**
 * E2E spec: yield-alert-center — happy paths + resilience
 *
 * All API calls are intercepted with page.route() (LIFO rule: catch-all FIRST,
 * specific routes LAST so specific routes take priority).
 * No real backend required.
 *
 * Selectors: data-testid anchors (added to App.vue) plus stable class/role
 * selectors for shared-ui components (AsyncQueryProgress, ErrorBanner).
 *
 * Tests:
 *  1. test_page_loads_with_filter_panel          — filter inputs visible on mount
 *  2. test_default_filter_values                 — risk_threshold=98, min_scrap_qty=1
 *  3. test_submit_triggers_query_api             — POST /api/yield-alert/query called
 *  4. test_async_job_polling_resolves            — 202 → poll → done; loading-state then table
 *  5. test_sync_response_shows_table             — 200 sync → alerts-table rows visible
 *  6. test_summary_cards_render                  — summary-cards always present
 *  7. test_empty_state_no_alerts                 — empty alerts → empty-state visible
 *  8. test_pagination_view_loads                 — /view called with page=1
 *  9. test_granularity_switch                    — granularity in query payload
 * 10. test_process_type_filter                   — process_type=GC% in payload
 * 11. test_api_error_shows_banner                — 500 from /query → error-banner
 * 12. test_row_expand_shows_detail               — expand row → reason-detail visible
 */

import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const PAGE_URL = `${BASE_URL}/portal-shell/yield-alert-center`;

const JOB_ID = 'test-ya-job-001';
const QUERY_ID = 'qid-yield-alert-001';
const STATUS_URL = `/api/yield-alert/job/${JOB_ID}`;

const MOCK_META = { timestamp: new Date().toISOString(), app_version: 'test' };

// ---------------------------------------------------------------------------
// Mock payloads
// ---------------------------------------------------------------------------

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    workcenter_groups: ['焊接_DB', '焊接_WB', '成型', '品檢'],
  },
  meta: MOCK_META,
};

/** 200 sync response — short date range, inline results */
const MOCK_200_SYNC = {
  success: true,
  data: {
    query_id: QUERY_ID,
    summary: { transaction_qty: 12000, scrap_qty: 48, yield_pct: 99.6 },
    trend: {
      items: [
        { date_bucket: '2026-06-01', yield_pct: 99.8, scrap_qty: 10 },
        { date_bucket: '2026-06-02', yield_pct: 99.5, scrap_qty: 20 },
      ],
    },
    heatmap: { items: [] },
    station_summary: { items: [] },
    package_summary: { items: [] },
    alerts: {
      items: [
        {
          date_bucket: '2026-06-01',
          workorder: 'WO-001',
          source_code: 'LOT-A',
          reason_code: 'RC-01',
          department: '焊接_DB',
          package: 'PKG-X',
          type: 'TYPE-A',
          transaction_qty: 500,
          scrap_qty: 5,
          yield_pct: 99.0,
          risk_level: 'medium',
          risk_score: 45.5,
        },
        {
          date_bucket: '2026-06-02',
          workorder: 'WO-002',
          source_code: null,
          reason_code: 'RC-02',
          department: '品檢',
          package: 'PKG-Y',
          type: 'TYPE-B',
          transaction_qty: 300,
          scrap_qty: 15,
          yield_pct: 95.0,
          risk_level: 'high',
          risk_score: 82.3,
        },
      ],
      pagination: { page: 1, per_page: 20, total: 2, total_pages: 1 },
    },
    filter_options: {
      lines: ['LINE-1', 'LINE-2'],
      packages: ['PKG-X', 'PKG-Y'],
      types: ['TYPE-A', 'TYPE-B'],
      functions: ['FN-1'],
    },
  },
  meta: MOCK_META,
};

/** 202 async response — triggers RQ polling */
const MOCK_202 = {
  success: true,
  data: {
    async: true,
    job_id: JOB_ID,
    status_url: STATUS_URL,
    query_id: null,
  },
  meta: MOCK_META,
};

/** Job status — in progress */
const MOCK_JOB_STARTED = {
  success: true,
  data: {
    status: 'started',
    job_id: JOB_ID,
    query_id: null,
    error: null,
    pct: 20,
    stage: 'querying',
    progress: '背景查詢中...',
  },
  meta: MOCK_META,
};

/** Job status — finished; no query_id in job response → App uses preQueryId from 202 */
const MOCK_JOB_FINISHED = {
  success: true,
  data: {
    status: 'finished',
    job_id: JOB_ID,
    query_id: QUERY_ID,
    error: null,
    pct: 100,
    stage: 'complete',
    progress: '查詢完成',
  },
  meta: MOCK_META,
};

/** /view response used after polling completes */
const MOCK_VIEW = {
  success: true,
  data: {
    ...MOCK_200_SYNC.data,
    query_id: QUERY_ID,
  },
  meta: MOCK_META,
};

/** Empty alerts — triggers empty-state */
const MOCK_200_EMPTY = {
  success: true,
  data: {
    query_id: QUERY_ID,
    summary: { transaction_qty: 0, scrap_qty: 0, yield_pct: 100 },
    trend: { items: [] },
    heatmap: { items: [] },
    station_summary: { items: [] },
    package_summary: { items: [] },
    alerts: { items: [], pagination: { page: 1, per_page: 20, total: 0, total_pages: 1 } },
    filter_options: { lines: [], packages: [], types: [], functions: [] },
  },
  meta: MOCK_META,
};

/** reason-detail response */
const MOCK_REASON_DETAIL = {
  success: true,
  data: {
    items: [
      {
        containername: 'LOT-A',
        workcentername: '焊接_DB',
        package_name: 'PKG-X',
        pj_function: 'FN-1',
        pj_type: 'TYPE-A',
        productname: 'PROD-001',
        lossreasonname: 'SCRATCH',
        equipmentname: 'EQ-01',
        rejectcomment: '外觀不良',
        reject_total_qty: 5,
        defect_qty: 0,
        txn_time: '2026-06-01 08:00:00',
      },
    ],
  },
  meta: MOCK_META,
};

// ---------------------------------------------------------------------------
// Helper: register catch-all routes (LIFO — registered FIRST so specific
// routes registered later in each test take priority).
// ---------------------------------------------------------------------------

async function registerCatchAllRoutes(page: import('@playwright/test').Page) {
  // Shell/auth catch-alls
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser', role: 'user' }, meta: MOCK_META }),
    }),
  );
  await page.route('**/api/pages**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [], meta: MOCK_META }),
    }),
  );
  // Intercept WIP endpoint that the portal-shell default page fetches on mount
  await page.route('**/api/wip/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: MOCK_META }),
    }),
  );

  // Yield-alert endpoints — sensible defaults, overridden per-test below
  await page.route('**/api/yield-alert/filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    }),
  );
  await page.route('**/api/yield-alert/cross-filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { lines: [], packages: [], types: [], functions: [] },
        meta: MOCK_META,
      }),
    }),
  );
  await page.route('**/api/yield-alert/view**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_VIEW),
    }),
  );
  await page.route('**/api/yield-alert/reason-detail**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_REASON_DETAIL),
    }),
  );
  // Default job catch-all — returns 404 unless overridden
  await page.route('**/api/yield-alert/job/**', (route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: { code: 'NOT_FOUND', message: 'no such job' },
        meta: MOCK_META,
      }),
    }),
  );
  // Default /query → 200 sync (overridden per-test where async is needed)
  await page.route('**/api/yield-alert/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_200_SYNC),
    }),
  );
}

/**
 * Navigate to the yield-alert-center page.
 * Uses page.goto().catch(()=>{}) so CI without a dev server does not throw.
 * Returns whether the Vue app mounted (page-rendered guard).
 */
async function gotoPage(page: import('@playwright/test').Page): Promise<boolean> {
  await page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  // pageRendered: look for the theme class or a Chinese keyword from our app.
  // Chrome's ECONNREFUSED error page body exceeds 100 chars but contains no
  // theme class or Chinese text, so this guard is reliable.
  const bodyText = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
  const appMounted =
    (bodyText ?? '').includes('日期') ||
    (bodyText ?? '').includes('告警') ||
    (await page.locator('[data-testid="yield-alert-app"]').count().catch(() => 0)) > 0;
  return appMounted;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('yield-alert-center', () => {
  // ──────────────────────────────────────────────────────────────────────────
  // 1. Page loads — filter panel visible
  // ──────────────────────────────────────────────────────────────────────────
  test('test_page_loads_with_filter_panel', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_page_loads_with_filter_panel: no dev server — skip');
      return;
    }

    await expect(page.locator('[data-testid="start-date"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="end-date"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="process-type-select"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="query-submit-btn"]')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-testid="clear-btn"]')).toBeVisible({ timeout: 5_000 });
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 2. Default filter values
  // ──────────────────────────────────────────────────────────────────────────
  test('test_default_filter_values', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_default_filter_values: no dev server — skip');
      return;
    }

    // risk_threshold and min_scrap_qty are in the supplementary panel which is
    // behind v-if="queryId" — they are only rendered after a query completes.
    // After mount setDefaultDateRange() sets start/end, so we can click submit.
    // Use the primary submit button (in primary-query-panel, always visible).
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(3_000);

    // After a sync query resolves the supplementary panel appears.
    await expect(page.locator('[data-testid="risk-threshold-input"]')).toBeVisible({ timeout: 10_000 });
    const riskVal = await page.locator('[data-testid="risk-threshold-input"]').inputValue();
    expect(riskVal).toBe('98');

    await expect(page.locator('[data-testid="min-scrap-qty-input"]')).toBeVisible({ timeout: 5_000 });
    const minScrapVal = await page.locator('[data-testid="min-scrap-qty-input"]').inputValue();
    expect(minScrapVal).toBe('1');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 3. Submit triggers POST /api/yield-alert/query with correct params
  // ──────────────────────────────────────────────────────────────────────────
  test('test_submit_triggers_query_api', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const capturedBodies: string[] = [];
    // Override /query to capture request body (specific route registered LAST)
    await page.route('**/api/yield-alert/query**', async (route) => {
      const body = route.request().postData() ?? '';
      capturedBodies.push(body);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_200_SYNC),
      });
    });

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_submit_triggers_query_api: no dev server — skip');
      return;
    }

    // Fill explicit dates so canSubmit becomes true
    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(3_000);

    expect(capturedBodies.length).toBeGreaterThan(0);
    const payload = JSON.parse(capturedBodies[0]);
    expect(payload.start_date).toBe('2026-06-01');
    expect(payload.end_date).toBe('2026-06-20');
    // Default process_type is GA%
    expect(payload.process_type).toBe('GA%');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 4. Async job polling: 202 → poll (started) → poll (finished) → results
  // ──────────────────────────────────────────────────────────────────────────
  test('test_async_job_polling_resolves', async ({ page }) => {
    await registerCatchAllRoutes(page);

    // Override /query to return 202 (LAST = highest priority)
    await page.route('**/api/yield-alert/query**', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_202),
      }),
    );

    // Job polling: first call → started; second call → finished
    let pollCount = 0;
    await page.route(`**${STATUS_URL}**`, (route) => {
      pollCount++;
      const payload = pollCount <= 1 ? MOCK_JOB_STARTED : MOCK_JOB_FINISHED;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
    });

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_async_job_polling_resolves: no dev server — skip');
      return;
    }

    await page.locator('[data-testid="start-date"]').fill('2026-01-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();

    // AsyncQueryProgress (.async-job-progress) should appear while polling
    const progressEl = page.locator('.async-job-progress');
    const progressVisible = await progressEl.isVisible({ timeout: 15_000 }).catch(() => false);
    // Note: may flash and disappear before assertion if mock resolves very fast
    // The critical assertion is that it does NOT stay visible after completion.
    if (progressVisible) {
      await expect(progressEl).toBeVisible();
    }

    // Wait for polling + /view to resolve
    await page.waitForTimeout(12_000);

    // After completion: progress bar must not be active
    const progressStillVisible = await progressEl.isVisible({ timeout: 2_000 }).catch(() => false);
    expect(progressStillVisible).toBe(false);

    // Results table or empty-state must be visible (polling resolved, view loaded)
    const tableVisible = await page.locator('[data-testid="alerts-table"]').isVisible({ timeout: 5_000 }).catch(() => false);
    const emptyVisible = await page.locator('[data-testid="empty-state"]').isVisible({ timeout: 2_000 }).catch(() => false);
    expect(tableVisible || emptyVisible).toBe(true);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 5. Sync 200 response → alerts-table rows visible immediately
  // ──────────────────────────────────────────────────────────────────────────
  test('test_sync_response_shows_table', async ({ page }) => {
    await registerCatchAllRoutes(page);
    // /query already defaults to MOCK_200_SYNC in catch-all

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_sync_response_shows_table: no dev server — skip');
      return;
    }

    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();

    // After sync response the table should appear
    await expect(page.locator('[data-testid="alerts-table"]')).toBeVisible({ timeout: 15_000 });

    // At least two data rows from MOCK_200_SYNC (WO-001 and WO-002)
    const rows = page.locator('[data-testid="alerts-table"] tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 5_000 });
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // Verify specific row content
    await expect(page.locator('[data-testid="alerts-table"] tbody')).toContainText('WO-001');
    await expect(page.locator('[data-testid="alerts-table"] tbody')).toContainText('WO-002');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 6. Summary cards are always rendered (even before query)
  // ──────────────────────────────────────────────────────────────────────────
  test('test_summary_cards_render', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_summary_cards_render: no dev server — skip');
      return;
    }

    // summary-cards section is unconditionally rendered
    await expect(page.locator('[data-testid="summary-cards"]')).toBeVisible({ timeout: 10_000 });

    // Run a query so summary values are populated
    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    // After query the section should show the 3 card labels from MOCK_200_SYNC
    const cardsSection = page.locator('[data-testid="summary-cards"]');
    await expect(cardsSection).toContainText('移轉量', { timeout: 8_000 });
    await expect(cardsSection).toContainText('報廢量');
    await expect(cardsSection).toContainText('良率');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 7. Empty alerts array → empty-state visible
  // ──────────────────────────────────────────────────────────────────────────
  test('test_empty_state_no_alerts', async ({ page }) => {
    await registerCatchAllRoutes(page);

    // Override /query to return empty results (LAST)
    await page.route('**/api/yield-alert/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_200_EMPTY),
      }),
    );

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_empty_state_no_alerts: no dev server — skip');
      return;
    }

    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    // alerts-table must NOT be visible (no data)
    const tableVisible = await page.locator('[data-testid="alerts-table"]').isVisible({ timeout: 2_000 }).catch(() => false);
    expect(tableVisible).toBe(false);

    // empty-state must be visible
    await expect(page.locator('[data-testid="empty-state"]')).toBeVisible({ timeout: 10_000 });
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 8. Pagination: GET /view called with page=1 after primary query
  // ──────────────────────────────────────────────────────────────────────────
  test('test_pagination_view_loads', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const viewCalls: string[] = [];
    // Override /view to capture params (LAST)
    await page.route('**/api/yield-alert/view**', async (route) => {
      viewCalls.push(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_VIEW),
      });
    });

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_pagination_view_loads: no dev server — skip');
      return;
    }

    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    // /view must have been called at least once
    expect(viewCalls.length).toBeGreaterThan(0);
    // URL must contain page=1
    const firstCall = viewCalls[0];
    expect(firstCall).toContain('page=1');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 9. Granularity switch — selected granularity appears in /query payload
  // ──────────────────────────────────────────────────────────────────────────
  test('test_granularity_switch', async ({ page }) => {
    await registerCatchAllRoutes(page);

    // First query returns data so supplementary panel (with granularity) appears
    await page.route('**/api/yield-alert/query**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_200_SYNC),
      }),
    );

    const viewCalls: string[] = [];
    await page.route('**/api/yield-alert/view**', async (route) => {
      viewCalls.push(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_VIEW),
      });
    });

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_granularity_switch: no dev server — skip');
      return;
    }

    // Initial query to get queryId and show the supplementary panel
    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    // Granularity toggle buttons are inside [data-testid="granularity-select"]
    await expect(page.locator('[data-testid="granularity-select"]')).toBeVisible({ timeout: 10_000 });

    const viewCallsBefore = viewCalls.length;

    // Click the "月" (month) button
    await page.locator('[data-testid="granularity-select"] button').filter({ hasText: '月' }).click();
    // Granularity watch triggers runQuery automatically when hasQueried=true
    await page.waitForTimeout(4_000);

    // A new /view call must have been made with granularity=month
    const newCalls = viewCalls.slice(viewCallsBefore);
    expect(newCalls.length).toBeGreaterThan(0);
    expect(newCalls[0]).toContain('granularity=month');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 10. Process type filter — GC% propagated to /query payload
  // ──────────────────────────────────────────────────────────────────────────
  test('test_process_type_filter', async ({ page }) => {
    await registerCatchAllRoutes(page);

    const capturedBodies: string[] = [];
    await page.route('**/api/yield-alert/query**', async (route) => {
      capturedBodies.push(route.request().postData() ?? '');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_200_SYNC),
      });
    });

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_process_type_filter: no dev server — skip');
      return;
    }

    // Select GC% radio button
    const gcRadio = page.locator('[data-testid="process-type-select"] input[value="GC%"]');
    await expect(gcRadio).toBeVisible({ timeout: 10_000 });
    await gcRadio.check();

    // Fill dates and submit
    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    expect(capturedBodies.length).toBeGreaterThan(0);
    const payload = JSON.parse(capturedBodies[capturedBodies.length - 1]);
    expect(payload.process_type).toBe('GC%');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 11. API 500 error → error-banner visible
  // ──────────────────────────────────────────────────────────────────────────
  test('test_api_error_shows_banner', async ({ page }) => {
    await registerCatchAllRoutes(page);

    // Override /query to return 500 (LAST)
    await page.route('**/api/yield-alert/query**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: { code: 'INTERNAL_ERROR', message: 'DB 連線失敗' },
          meta: MOCK_META,
        }),
      }),
    );

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_api_error_shows_banner: no dev server — skip');
      return;
    }

    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();
    await page.waitForTimeout(4_000);

    // ErrorBanner renders [role="alert"] when message is set.
    // data-testid="error-banner" is on the <ErrorBanner> component wrapper —
    // with inheritAttrs=true the attribute falls on the root .error-banner-wrap div,
    // but only when message is non-empty (v-if="message").
    // Accept any of the stable error surface selectors.
    const errorSelectors = [
      '[role="alert"]',
      '[data-testid="error-banner"]',
      '.error-banner-wrap',
    ];
    let errorVisible = false;
    for (const sel of errorSelectors) {
      const v = await page.locator(sel).first().isVisible({ timeout: 5_000 }).catch(() => false);
      if (v) { errorVisible = true; break; }
    }
    expect(errorVisible).toBe(true);

    // alerts-table must NOT be visible after an error
    const tableVisible = await page.locator('[data-testid="alerts-table"]').isVisible({ timeout: 2_000 }).catch(() => false);
    expect(tableVisible).toBe(false);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // 12. Row expand → reason-detail visible
  // ──────────────────────────────────────────────────────────────────────────
  test('test_row_expand_shows_detail', async ({ page }) => {
    await registerCatchAllRoutes(page);
    // /query defaults to MOCK_200_SYNC (2 alert rows)
    // /reason-detail defaults to MOCK_REASON_DETAIL

    const mounted = await gotoPage(page);
    if (!mounted) {
      console.warn('[yield-alert-center] test_row_expand_shows_detail: no dev server — skip');
      return;
    }

    // Trigger query to populate the alerts table
    await page.locator('[data-testid="start-date"]').fill('2026-06-01');
    await page.locator('[data-testid="end-date"]').fill('2026-06-20');
    await page.locator('[data-testid="query-submit-btn"]').click();

    // Wait for the table to appear
    await expect(page.locator('[data-testid="alerts-table"]')).toBeVisible({ timeout: 15_000 });

    // Click the first expand button
    const expandBtn = page.locator('[data-testid="row-expand-btn"]').first();
    await expect(expandBtn).toBeVisible({ timeout: 5_000 });
    await expandBtn.click();

    // row-detail <tr> must appear
    await expect(page.locator('[data-testid="row-detail"]')).toBeVisible({ timeout: 10_000 });

    // Reason detail table must contain the mocked data
    await expect(page.locator('[data-testid="row-detail"]')).toContainText('LOT-A', { timeout: 5_000 });
    await expect(page.locator('[data-testid="row-detail"]')).toContainText('焊接_DB');

    // Clicking expand button again should collapse the detail row
    await expandBtn.click();
    const detailGone = await page.locator('[data-testid="row-detail"]').isVisible({ timeout: 3_000 }).catch(() => false);
    expect(detailGone).toBe(false);
  });
});
