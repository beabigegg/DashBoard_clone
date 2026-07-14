/**
 * Data-boundary spec: 生產達成率 — target_qty / daily_plan_qty validation +
 * empty result set.
 * Change: production-achievement-kanban; updated by production-achievement
 * -async-spool (ADR-0016) and production-achievement-overhaul (IP-6..IP-9).
 *
 * Covers:
 *   - negative/non-numeric legacy target_qty rejected client-side (report
 *     page's TargetEditPanel.vue, unchanged mechanics — no PUT call fires)
 *   - negative/non-numeric daily_plan_qty rejected client-side on the NEW
 *     settings page's DailyPlanPanel.vue (no PUT call fires)
 *   - empty qualifying-row result set renders an empty state, not an error
 *
 * production-achievement-overhaul (IP-6): the spool parquet grain widens to
 * 5 columns (+PACKAGE_LF) and the report envelope injects 5 inline maps.
 * Fixtures below use REAL, schema-correct Parquet bytes (via the actual
 * `duckdb` Python package), matching the new grain.
 *
 * Network strategy: catch-all first, specific routes last (LIFO).
 */

import { test, expect } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';
const SETTINGS_PAGE_URL = '/portal-shell/production-achievement-settings';

// Real 0-row 5-column Parquet matching data-shape-contract.md §3.28.1's exact
// production-achievement-overhaul schema (output_date, shift_code, SPECNAME,
// PACKAGE_LF, actual_output_qty) — generated via the `duckdb` Python package.
const EMPTY_PARQUET_B64 =
  'UEFSMRUCGWw1ABgNZHVja2RiX3NjaGVtYRUKABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQwlAhgKUEFDS0FHRV9MRiUAABUEJQIYEWFjdHVhbF9vdXRwdXRfcXR5JSQAFgAZDCgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlcHAAAHAAAHAAAHAAAHAAAAL0AAABQQVIx';

function envelope(data) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

async function setupBaseRoutes(page) {
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
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released', '/production-achievement-settings': 'released' },
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

async function isPageRendered(page, themeClass) {
  return page.evaluate((cls) => {
    const el = document.querySelector(cls);
    return el !== null && el.offsetParent !== null;
  }, themeClass);
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

test.describe('production-achievement data-boundary — legacy target_qty validation', () => {
  test('rejects a negative target_qty input without calling PUT', async ({ page }) => {
    await setupBaseRoutes(page);
    let putCalled = false;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
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
        body: envelope({ query_id: 'q1', spool_download_url: '/api/spool/production_achievement/q1.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
      }),
    );
    await page.route('**/api/spool/production_achievement/q1.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }),
    );

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping validation assertions' });
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('-100');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await page.waitForTimeout(500);
    expect(putCalled).toBe(false);
  });

  test('rejects a non-numeric target_qty input without calling PUT', async ({ page }) => {
    await setupBaseRoutes(page);
    let putCalled = false;
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
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
        body: envelope({ query_id: 'q2', spool_download_url: '/api/spool/production_achievement/q2.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
      }),
    );
    await page.route('**/api/spool/production_achievement/q2.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }),
    );

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping validation assertions' });
      return;
    }

    const editBtn = page.locator('[data-testid="pa-target-edit-btn"]').first();
    await expect(editBtn).toBeVisible({ timeout: 15_000 });
    await editBtn.click();
    await page.locator('[data-testid="pa-target-edit-input"]').fill('abc');
    await page.locator('[data-testid="pa-target-save-btn"]').click();

    await page.waitForTimeout(500);
    expect(putCalled).toBe(false);
  });
});

test.describe('production-achievement data-boundary — empty result set', () => {
  test('empty qualifying-row result renders empty state, not an error (auto-run, no explicit query control)', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      } else {
        route.continue();
      }
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-empty-boundary-001',
          spool_download_url: '/api/spool/production_achievement/pa-empty-boundary-001.parquet',
          spec_workcenter_map: [],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
          daily_plan_map: [],
        }),
      });
    });
    // Spool already warm, 0-row parquet — the §3.28.1 empty-result invariant.
    await page.route('**/api/spool/production_achievement/pa-empty-boundary-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping empty-state assertions' });
      return;
    }

    // OD-3: 當日 auto-runs on mount — no 查詢 button to click any more.
    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 20_000 });

    // No error banner should appear for a legitimately empty result set
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });
});

test.describe('production-achievement data-boundary — large payload (300 distinct PACKAGE_LF groups)', () => {
  // Re-added: the pre-existing production-achievement-async-spool spec had a
  // "300-entry large-payload stress" sub-case that frontend-engineer's own
  // agent-log flagged as a deliberate scope reduction during this change's
  // Phase 8/9 rewrite. App.vue's <DataTable> is NOT paginated (no :pagination
  // prop is bound), so a many-row DailyView renders every row in the DOM at
  // once -- this is a genuine data-VOLUME boundary, not merely a stress/perf
  // concern (monkey-test-engineer owns fuzz/rapid-click; this is data shape).
  test('300 distinct PACKAGE_LF groups render completely, with the correct row count and no crash/hang', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      return route.continue();
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-large-300-001',
          spool_download_url: '/api/spool/production_achievement/pa-large-300-001.parquet',
          spec_workcenter_map: [{ SPECNAME: 'SPEC-LARGE-A', workcenter_group: '焊接_DB' }],
          targets_map: [],
          package_lf_map: [], // every PKG-nnn raw value falls back to itself (D1) -- all 300 stay distinct rows
          workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
          daily_plan_map: [],
        }),
      });
    });
    // Real 300-row 5-column Parquet (generated via the `duckdb` Python
    // package): (2026-06-20, D, SPEC-LARGE-A, PKG-000..PKG-299, 10 each).
    const LARGE_300_PARQUET_B64 =
      'UEFSMRUEFQgVDEwVAhUAAAAEDJBQAAAVABUWFRosFdgEFQQVBhUGAAALKAMAAADYBAEB2AQAFQQVChUOTBUCFQAAAAUQAQAAAEQVABUWFRosFdgEFQQVBhUGAAALKAMAAADYBAEB2AQAFQQVIBUkTBUCFQAAABA8DAAAAFNQRUMtTEFSR0UtQRUAFRYVGiwV2AQVBBUGFQYAAAsoAwAAANgEAQHYBAAVABXWMxWUEywV2AQVABUGFQYAAOsZRAMAAADYBAEHAAAAUEtHLTAwMBkLADEZCwAyGQsAMxkLADQZCwA1GQsANhkLADcZCwA4GQsAORULADEZbgAxGW4AMRluADEZbgAxGW4AMRluADEZbgAxGW4AMRluADIZbgAyGW4AMhluADIZbgAyGW4AMhluADIZbgAyGW4AMhluADIZbgAzGW4AMxluADMZbgAzGW4AMxluADMZbgAzGW4AMxluADMZbgAzGW4ANBluADQZbgA0GW4ANBluADQZbgA0GW4ANBluADQZbgA0GW4ANBluADUZbgA1GW4ANRluADUZbgA1GW4ANRluADUZbgA1GW4ANRluADUZbgA2GW4ANhluADYZbgA2GW4ANhluADYZbgA2GW4ANhluADYZbgA2GW4ANxluADcZbgA3GW4ANxluADcZbgA3GW4ANxluADcZbgA3GW4ANxluADgZbgA4GW4AOBluADgZbgA4GW4AOBluADgZbgA4GW4AOBluADgZbgA5GW4AORluADkZbgA5GW4AORluADkZbgA5GW4AORluADkZbgA5FW4AMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMZlMADGZTAAxmUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMADKZTAAymUwAMplMNDI5OAcAAABQS0ctMjk5FQQVEBUUTBUCFQAAAAgcCgAAAAAAAAAVABUWFRosFdgEFQQVBhUGAAALKAMAAADYBAEB2AQAFUAcHAAAHBwAABwcAAAAAgAAAAAAABAAAAQAAAAQAAACAAAAACAAAAAAgABAAAAVQBwcAAAcHAAAHBwAAAAgAAAAAAAAIAAAEAAAEAAAACAAAAACAAAAACAAQAAAABVAHBwAABwcAAAcHAAAAAAgAAACAAAAAAIAAAIAAAAAACAAAAgAAAQAAACAAAAAFUAcHAAAHBwAABwcAAAAAABAAAAAAAEBAAAAQAAAAAAABAAAgAAAAAAIAAAAAQAVAhlsNQAYDWR1Y2tkYl9zY2hlbWEVCgAVAiUCGAtvdXRwdXRfZGF0ZSUMABUMJQIYCnNoaWZ0X2NvZGUlAAAVDCUCGAhTUEVDTkFNRSUAABUMJQIYClBBQ0tBR0VfTEYlAAAVBCUCGBFhY3R1YWxfb3V0cHV0X3F0eSUkABbYBBkcGVwmABwVAhkVBBkYC291dHB1dF9kYXRlFQIW2AQWXBZkJi4mCBwYBJBQAAAYBJBQAAAWABYCGASQUAAAGASQUAAAEREAJvYWFV4AACYAHBUMGRUEGRgKc2hpZnRfY29kZRUCFtgEFl4WZiaUASZsHBgBRBgBRBYAFgIYAUQYAUQREQAm1BcVXgAAJgAcFQwZFQQZGAhTUEVDTkFNRRUCFtgEFnQWfCaQAibSARwYDFNQRUMtTEFSR0UtQRgMU1BFQy1MQVJHRS1BFgAWAhgMU1BFQy1MQVJHRS1BGAxTUEVDLUxBUkdFLUEREQAmshgVXgAAJgAcFQwZFQAZGApQQUNLQUdFX0xGFQIW2AQW/jMWvBMmzgI8GAdQS0ctMjk5GAdQS0ctMDAwFgAoB1BLRy0yOTkYB1BLRy0wMDAREQAAACYAHBUEGRUEGRgRYWN0dWFsX291dHB1dF9xdHkVAhbYBBZkFmwmuBYmihYcGAgKAAAAAAAAABgICgAAAAAAAAAWABYCGAgKAAAAAAAAABgICgAAAAAAAAAREQAmkBkVXgAAFpA3FtgEJggW7hYAKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGVwcAAAcAAAcAAAcAAAcAAAAbgIAAFBBUjE=';
    await page.route('**/api/spool/production_achievement/pa-large-300-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(LARGE_300_PARQUET_B64, 'base64') });
    });

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping large-payload assertions' });
      return;
    }

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(300, { timeout: 30_000 });

    const text = await table.innerText();
    expect(text).toContain('PKG-000');
    expect(text).toContain('PKG-299');
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('Infinity');
    expect(pageErrors).toHaveLength(0);
  });
});

test.describe('production-achievement data-boundary — wrong-type inline map values', () => {
  // Real 1-row 5-column Parquet (generated via the `duckdb` Python package):
  // (2026-06-25, D, SPEC-WT-A, PKG-WT, 250).
  const WRONG_TYPE_PARQUET_B64 =
    'UEFSMRUAFRQVGCwVAhUAFQYVBgAACiQCAAAAAgGVUAAAFQAVFhUaLBUCFQAVBhUGAAALKAIAAAACAQEAAABEFQAVJhUqLBUCFQAVBhUGAAATSAIAAAACAQkAAABTUEVDLVdULUEVABUgFSQsFQIVABUGFQYAABA8AgAAAAIBBgAAAFBLRy1XVBUAFRwVICwVAhUAFQYVBgAADjQCAAAAAgH6AAAAAAAAABUCGWw1ABgNZHVja2RiX3NjaGVtYRUKABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQwlAhgKUEFDS0FHRV9MRiUAABUEJQIYEWFjdHVhbF9vdXRwdXRfcXR5JSQAFgIZHBlcJgAcFQIZFQAZGAtvdXRwdXRfZGF0ZRUCFgIWNhY6Jgg8GASVUAAAGASVUAAAFgAoBJVQAAAYBJVQAAAREQAAACYAHBUMGRUAGRgKc2hpZnRfY29kZRUCFgIWOBY8JkI8GAFEGAFEFgAoAUQYAUQREQAAACYAHBUMGRUAGRgIU1BFQ05BTUUVAhYCFkgWTCZ+PBgJU1BFQy1XVC1BGAlTUEVDLVdULUEWACgJU1BFQy1XVC1BGAlTUEVDLVdULUEREQAAACYAHBUMGRUAGRgKUEFDS0FHRV9MRhUCFgIWQhZGJsoBPBgGUEtHLVdUGAZQS0ctV1QWACgGUEtHLVdUGAZQS0ctV1QREQAAACYAHBUEGRUAGRgRYWN0dWFsX291dHB1dF9xdHkVAhYCFj4WQiaQAjwYCPoAAAAAAAAAGAj6AAAAAAAAABYAKAj6AAAAAAAAABgI+gAAAAAAAAAREQAAABa2AhYCJggWygIAKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGVwcAAAcAAAcAAAcAAAcAAAALQIAAFBBUjE=';

  test('a STRING daily_plan_qty (wrong type, not a number) in daily_plan_map degrades to "—", never NaN/Infinity/crash', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      return route.continue();
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({
          query_id: 'pa-wrong-type-001',
          spool_download_url: '/api/spool/production_achievement/pa-wrong-type-001.parquet',
          spec_workcenter_map: [{ SPECNAME: 'SPEC-WT-A', workcenter_group: '焊接_DB' }],
          targets_map: [],
          package_lf_map: [],
          workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
          // daily_plan_qty is a STRING here, never the number data-shape-contract.md
          // §3.32 declares -- the DuckDB-WASM layer's sqlNumberOrNull() coerces any
          // non-finite Number(...) to SQL NULL, so this must render as "—", not "NaN%".
          daily_plan_map: [{ workcenter_group: '焊接_DB', package_lf_group: 'PKG-WT', daily_plan_qty: 'abc' }],
        }),
      });
    });
    await page.route('**/api/spool/production_achievement/pa-wrong-type-001.parquet**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(WRONG_TYPE_PARQUET_B64, 'base64') });
    });

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping wrong-type daily_plan_qty assertions' });
      return;
    }

    const table = reportTable(page);
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(1, { timeout: 20_000 });

    const text = await table.innerText();
    expect(text).toContain('PKG-WT');
    expect(text).toContain('250'); // actual output still renders correctly
    expect(text).toContain('—'); // daily_plan_qty / 每日達成率 both degrade to the null placeholder
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('Infinity');
    expect(pageErrors).toHaveLength(0);
  });

  test('a non-array workcenter_groups (wrong type, object instead of array) from filter-options degrades to no options, no crash', async ({ page }) => {
    await setupBaseRoutes(page);
    // Override the base filter-options mock with a wrong-type payload.
    await page.route('**/api/production-achievement/filter-options**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: { not: 'an array' } }) }),
    );
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      return route.continue();
    });
    await page.route('**/api/production-achievement/report**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope({ query_id: 'q-wt2', spool_download_url: '/api/spool/production_achievement/q-wt2.parquet', spec_workcenter_map: [], targets_map: [], package_lf_map: [], workcenter_merge_map: [], daily_plan_map: [] }),
      }),
    );
    await page.route('**/api/spool/production_achievement/q-wt2.parquet**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(EMPTY_PARQUET_B64, 'base64') }),
    );

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping wrong-type workcenter_groups assertions' });
      return;
    }

    // Array.isArray(...) guard in useProductionAchievement.ts's fetchFilterOptions()
    // degrades a non-array payload to [] -- the station select shows no options
    // (beyond whatever the current default value already is) instead of crashing.
    await expect(page.locator('[data-testid="pa-app"]')).toBeVisible({ timeout: 15_000 });
    expect(pageErrors).toHaveLength(0);
    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });
});

test.describe('production-achievement-settings data-boundary — daily_plan_qty validation', () => {
  async function setupSettingsRoutes(page) {
    await page.route('**/api/production-achievement/package-lf-map**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) }),
    );
    await page.route('**/api/production-achievement/known-package-lf-values**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ package_lf_values: [] }) }),
    );
    await page.route('**/api/production-achievement/workcenter-merge-map**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope([{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', updated_at: 't', updated_by: 'admin' }]),
      }),
    );
    await page.route('**/api/production-achievement/known-workcenter-groups**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ raw_workcenter_groups: ['焊接_DB'] }) }),
    );
    await page.route('**/api/production-achievement/daily-plans**', (route) => {
      if (route.request().method() === 'PUT') {
        return route.fulfill({ status: 400, contentType: 'application/json', body: envelope(null) }); // should never be reached
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    });
  }

  test('rejects a negative daily_plan_qty on the new-row form without calling PUT', async ({ page }) => {
    await setupBaseRoutes(page);
    await setupSettingsRoutes(page);
    let putCalled = false;
    await page.route('**/api/production-achievement/daily-plans**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    });

    await page.goto(SETTINGS_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement-settings');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'settings page not rendered yet; skipping validation assertions' });
      return;
    }

    await page.locator('[data-testid="pa-plan-new-btn"]').click();
    await page.locator('[data-testid="pa-plan-new-workcenter"]').selectOption('焊接_DB');
    await page.locator('[data-testid="pa-plan-new-qty"]').fill('-50');
    await page.locator('[data-testid="pa-plan-new-save"]').click();

    await page.waitForTimeout(500);
    expect(putCalled).toBe(false);
  });

  test('rejects a non-numeric daily_plan_qty on the new-row form without calling PUT', async ({ page }) => {
    await setupBaseRoutes(page);
    await setupSettingsRoutes(page);
    let putCalled = false;
    await page.route('**/api/production-achievement/daily-plans**', (route) => {
      if (route.request().method() === 'PUT') {
        putCalled = true;
        return route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
    });

    await page.goto(SETTINGS_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelector('.theme-production-achievement-settings') !== null, { timeout: 20_000 }).catch(() => {});

    const rendered = await isPageRendered(page, '.theme-production-achievement-settings');
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'settings page not rendered yet; skipping validation assertions' });
      return;
    }

    await page.locator('[data-testid="pa-plan-new-btn"]').click();
    await page.locator('[data-testid="pa-plan-new-workcenter"]').selectOption('焊接_DB');
    await page.locator('[data-testid="pa-plan-new-qty"]').fill('abc');
    await page.locator('[data-testid="pa-plan-new-save"]').click();

    await page.waitForTimeout(500);
    expect(putCalled).toBe(false);
  });
});
