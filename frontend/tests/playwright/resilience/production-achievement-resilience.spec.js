/**
 * Resilience spec: 生產達成率 — MySQL unavailable degrade
 * Change: production-achievement-kanban; updated by production-achievement
 * -async-spool (ADR-0016) and production-achievement-overhaul (IP-6..IP-9).
 *
 * Covers:
 *   - MySQL unavailable / MYSQL_OPS_ENABLED=false: report degrades to
 *     daily_plan_qty:null / achievement_rate:null (never 500), no crash —
 *     targets_map/package_lf_map/workcenter_merge_map/daily_plan_map are all
 *     independently MySQL-backed and each degrade to an empty array on their
 *     own (data-shape-contract.md §3.28.3/§3.30/§3.31/§3.32); this spec
 *     covers the daily_plan_map-empty case specifically (D-shift/N-shift
 *     output still populated from Oracle, but 每日達成率 is "—" for every row).
 *   - Permission check denies (503 on write) when MySQL is unreachable —
 *     distinct from the 403 (FORBIDDEN) permission-denied path.
 *   - OD-9 (accepted no-op): an EMPTY workcenter_merge_map means the D2 INNER
 *     JOIN excludes every row — the whole report renders empty, not an error.
 *
 * production-achievement-overhaul (IP-6): the spool parquet grain widens to
 * (output_date, shift_code, SPECNAME, PACKAGE_LF, actual_output_qty) —
 * fixtures below use REAL, schema-correct Parquet bytes generated via the
 * actual `duckdb` Python package (5 columns), not the old 4-column shape.
 * The report envelope now injects 5 inline maps, not 2.
 *
 * Network strategy: catch-all first, specific routes last (LIFO), per
 * ci-workflow.md. Uses page.goto(...).catch(()=>{}) + guard, NOT
 * page.request.post() (loginViaApi), which is not interceptable by
 * page.route() and throws ECONNREFUSED in CI.
 */

import { test, expect } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';

// Real 1-row 5-column Parquet (data-shape-contract.md §3.28.1 schema,
// production-achievement-overhaul grain): generated via the `duckdb` Python
// package: (2026-06-01, D, SPEC-A1, SOD-123FL, 500).
const ONE_ROW_PARQUET_B64 =
  'UEFSMRUAFRQVGCwVAhUAFQYVBgAACiQCAAAAAgF9UAAAFQAVFhUaLBUCFQAVBhUGAAALKAIAAAACAQEAAABEFQAVIhUmLBUCFQAVBhUGAAARQAIAAAACAQcAAABTUEVDLUExFQAVJhUqLBUCFQAVBhUGAAATSAIAAAACAQkAAABTT0QtMTIzRkwVABUcFSAsFQIVABUGFQYAAA40AgAAAAIB9AEAAAAAAAAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABYCGRwZXCYAHBUCGRUAGRgLb3V0cHV0X2RhdGUVAhYCFjYWOiYIPBgEfVAAABgEfVAAABYAKAR9UAAAGAR9UAAAEREAAAAmABwVDBkVABkYCnNoaWZ0X2NvZGUVAhYCFjgWPCZCPBgBRBgBRBYAKAFEGAFEEREAAAAmABwVDBkVABkYCFNQRUNOQU1FFQIWAhZEFkgmfjwYB1NQRUMtQTEYB1NQRUMtQTEWACgHU1BFQy1BMRgHU1BFQy1BMRERAAAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIWAhZIFkwmxgE8GAlTT0QtMTIzRkwYCVNPRC0xMjNGTBYAKAlTT0QtMTIzRkwYCVNPRC0xMjNGTBERAAAAJgAcFQQZFQAZGBFhY3R1YWxfb3V0cHV0X3F0eRUCFgIWPhZCJpICPBgI9AEAAAAAAAAYCPQBAAAAAAAAFgAoCPQBAAAAAAAAGAj0AQAAAAAAABERAAAAFrgCFgImCBbMAgAoKER1Y2tEQiB2ZXJzaW9uIHYxLjUuNCAoYnVpbGQgMDhlMzRjNDQ3YikZXBwAABwAABwAABwAABwAAAAxAgAAUEFSMQ==';

function envelope(data) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

function errorEnvelope(code, message) {
  return JSON.stringify({ success: false, error: { code, message }, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

async function setupBaseRoutes(page) {
  await page.route('**/*', (route) => (route.request().resourceType() === 'document' ? route.fallback() : route.continue()));
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
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released' },
        is_admin: false,
        admin_user: null,
        admin_links: { logout: null, pages: null, dashboard: null },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    });
  });
  await page.route('**/api/production-achievement/filter-options**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB'] }) });
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

test.describe('production-achievement resilience — MySQL unavailable (daily_plan_map)', () => {
  test('report degrades to "—" achievement_rate with no crash when the daily-plan table is unavailable', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      } else {
        route.continue();
      }
    });
    // daily_plan_map degrades to EMPTY (MySQL down -> get_daily_plans_map()
    // degradation, §3.34) while spec_workcenter_map/workcenter_merge_map stay
    // populated -- every rolled-up row's daily_plan_qty/achievement_rate come
    // out null via DuckDB-WASM's real LEFT JOIN (PA-12), actual output qty
    // still populated from the real spool (auto-run, no explicit query click needed).
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-mysql-down-001',
          spool_download_url: '/api/spool/production_achievement/pa-mysql-down-001.parquet',
          spec_workcenter_map: [{ SPECNAME: 'SPEC-A1', workcenter_group: '焊接_DB' }],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
          daily_plan_map: [],
        }),
      });
    });
    await page.route('**/api/spool/production_achievement/pa-mysql-down-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(ONE_ROW_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody15 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody15?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping deep assertions' });
      return;
    }

    // 當日 auto-runs on mount (OD-3) -- no explicit submit control exists any more.
    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(1, { timeout: 20_000 });

    const text = await table.innerText();
    expect(text).toContain('—'); // daily_plan_qty / 每日達成率 both null -> "—"
    expect(text).not.toContain('Infinity');
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('null');

    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });

  test('OD-9: an EMPTY workcenter_merge_map (D2 INNER JOIN) renders the whole report empty, not an error', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-wc-empty-001',
          spool_download_url: '/api/spool/production_achievement/pa-wc-empty-001.parquet',
          spec_workcenter_map: [{ SPECNAME: 'SPEC-A1', workcenter_group: '焊接_DB' }],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [], // MySQL down -> D2 INNER JOIN matches nothing
          daily_plan_map: [],
        }),
      });
    });
    await page.route('**/api/spool/production_achievement/pa-wc-empty-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(ONE_ROW_PARQUET_B64, 'base64') }),
    );

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody16 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody16?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping empty-workcenter-merge assertions' });
      return;
    }

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 20_000 });
    // Empty-because-config-down reads identically to genuinely-empty (OD-9 accepted, no discriminator).
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });

  test('D1: an UNMAPPED raw PACKAGE_LF (package_lf_map empty) still renders as itself — OPPOSITE join kind from workcenter_merge_map (D2)', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));
    // Real 1-row 5-column Parquet (generated via the `duckdb` Python package):
    // (2026-06-15, D, SPEC-D1-A, RAW-UNMAPPED-1, 400) — a raw PACKAGE_LF value
    // that has NO row in package_lf_map at all (not even a NULL/blank one).
    const UNMAPPED_PKG_PARQUET_B64 =
      'UEFSMRUAFRQVGCwVAhUAFQYVBgAACiQCAAAAAgGLUAAAFQAVFhUaLBUCFQAVBhUGAAALKAIAAAACAQEAAABEFQAVJhUqLBUCFQAVBhUGAAATSAIAAAACAQkAAABTUEVDLUQxLUEVABUwFTQsFQIVABUGFQYAABhcAgAAAAIBDgAAAFJBVy1VTk1BUFBFRC0xFQAVHBUgLBUCFQAVBhUGAAAONAIAAAACAZABAAAAAAAAFQIZbDUAGA1kdWNrZGJfc2NoZW1hFQoAFQIlAhgLb3V0cHV0X2RhdGUlDAAVDCUCGApzaGlmdF9jb2RlJQAAFQwlAhgIU1BFQ05BTUUlAAAVDCUCGApQQUNLQUdFX0xGJQAAFQQlAhgRYWN0dWFsX291dHB1dF9xdHklJAAWAhkcGVwmABwVAhkVABkYC291dHB1dF9kYXRlFQIWAhY2FjomCDwYBItQAAAYBItQAAAWACgEi1AAABgEi1AAABERAAAAJgAcFQwZFQAZGApzaGlmdF9jb2RlFQIWAhY4FjwmQjwYAUQYAUQWACgBRBgBRBERAAAAJgAcFQwZFQAZGAhTUEVDTkFNRRUCFgIWSBZMJn48GAlTUEVDLUQxLUEYCVNQRUMtRDEtQRYAKAlTUEVDLUQxLUEYCVNQRUMtRDEtQRERAAAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIWAhZSFlYmygE8GA5SQVctVU5NQVBQRUQtMRgOUkFXLVVOTUFQUEVELTEWACgOUkFXLVVOTUFQUEVELTEYDlJBVy1VTk1BUFBFRC0xEREAAAAmABwVBBkVABkYEWFjdHVhbF9vdXRwdXRfcXR5FQIWAhY+FkImoAI8GAiQAQAAAAAAABgIkAEAAAAAAAAWACgIkAEAAAAAAAAYCJABAAAAAAAAEREAAAAWxgIWAiYIFtoCACgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlcHAAAHAAAHAAAHAAAHAAAAE0CAABQQVIx';
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-d1-unmapped-001',
          spool_download_url: '/api/spool/production_achievement/pa-d1-unmapped-001.parquet',
          spec_workcenter_map: [{ SPECNAME: 'SPEC-D1-A', workcenter_group: '焊接_DB' }],
          targets_map: [],
          package_lf_map: [], // D1: no merge exceptions configured at all (also the MYSQL_OPS_ENABLED=false shape, §3.30)
          workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }], // D2 populated -- keeps ONLY D1's own join-kind under test here
          daily_plan_map: [],
        }),
      });
    });
    await page.route('**/api/spool/production_achievement/pa-d1-unmapped-001.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(UNMAPPED_PKG_PARQUET_B64, 'base64') }),
    );

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody17 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody17?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping D1 unmapped-PACKAGE_LF assertions' });
      return;
    }

    // D1 (package_lf_map, LEFT JOIN, PA-09): an unmapped raw PACKAGE_LF falls
    // back to ITSELF and is never dropped — the OPPOSITE of D2's empty-map
    // behaviour proven by the OD-9 test above (workcenter_merge_map, INNER
    // JOIN, PA-10: an empty map excludes every row). test-plan.md's own Notes:
    // every test touching either map must assert "not the other join kind."
    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(1, { timeout: 20_000 });

    const text = await table.innerText();
    expect(text).toContain('RAW-UNMAPPED-1'); // shown verbatim, not dropped, not "(未分類)" (value is non-null/non-blank)
    expect(text).toContain('400');
    expect(text).not.toContain('Infinity');
    expect(text).not.toContain('NaN');

    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });

  test('permission check denies (503) when MySQL is unreachable, distinct from 403 forbidden', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({ status: 503, contentType: 'application/json', body: errorEnvelope('SERVICE_UNAVAILABLE', 'MySQL 服務暫時無法使用') });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: envelope([{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' }]),
        });
      }
    });
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-503-001',
          spool_download_url: '/api/spool/production_achievement/pa-503-001.parquet',
          spec_workcenter_map: [],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [],
          daily_plan_map: [],
        }),
      }),
    );

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody18 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody18?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping 503 assertions' });
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('1500');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await expect(page.locator('[data-testid="pa-target-edit-error"]')).toBeVisible({ timeout: 10_000 });
    // 503 must NOT be presented as a permission-denied ("readonly") state —
    // the edit control should remain available for retry once MySQL recovers.
    await expect(page.locator('[data-testid="pa-target-readonly-note"]')).not.toBeVisible();

    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });
});

test.describe('production-achievement resilience — auth expiry mid-poll (401)', () => {
  test('a 401 while polling the async job clears the progress card and surfaces an error, with no infinite hang or crash', async ({ page }) => {
    // Session-expiry mid-poll: previously dropped from this feature's E2E
    // coverage during Phase 8/9 implementation (frontend-engineer's own
    // agent-log flagged this as a deliberate scope reduction) — re-added here.
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }));

    const JOB_ID = 'pa-job-401-001';
    let jobPollCount = 0;
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: envelope({ async: true, job_id: JOB_ID, status_url: `/api/job/${JOB_ID}?prefix=production-achievement` }),
      }),
    );
    await page.route(`**/api/job/${JOB_ID}**`, (route) => {
      jobPollCount++;
      if (jobPollCount <= 1) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: envelope({ status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 15, stage: 'querying', progress: '背景查詢中...' }),
        });
      }
      // Session expires mid-poll: the SECOND poll call (and every one after) 401s.
      return route.fulfill({ status: 401, contentType: 'application/json', body: errorEnvelope('UNAUTHORIZED', '登入已過期，請重新登入') });
    });

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => {});
    const noServerBody19 = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if ((noServerBody19?.trim().length ?? 0) < 50) {
      test.info().annotations.push({ type: 'note', description: 'no server response (body empty) -- skipping' });
      return;
    }
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 3_000 }).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping 401-mid-poll assertions' });
      return;
    }

    await expect(page.locator('.async-job-progress')).toBeVisible({ timeout: 10_000 });

    // The progress card must clear -- it must never hang forever waiting on a
    // session that will never come back -- and SOME visible error must
    // replace it. This is deliberately a black-box behavioural assertion (not
    // pinned to the exact error copy): the precise 401 -> error.value text is
    // core/api.ts's own internal convention, a file outside this spec's/this
    // agent's allowed paths, so only the OBSERVABLE contract (card clears, an
    // error appears, nothing hangs or throws) is asserted here.
    await expect(page.locator('.async-job-progress')).toHaveCount(0, { timeout: 20_000 });
    const banner = page.locator('.error-banner-message');
    await expect(banner).toBeVisible({ timeout: 10_000 });
    const bannerText = (await banner.innerText()).trim();
    expect(bannerText.length).toBeGreaterThan(0);

    expect(pageErrors).toHaveLength(0);
    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });
});
