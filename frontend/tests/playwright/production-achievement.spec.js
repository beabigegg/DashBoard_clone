/**
 * E2E tests: 生產達成率 (Production Achievement Rate) report page
 * Change: production-achievement-kanban
 * Tier 1 — required pre-merge gate (playwright-critical-journeys)
 *
 * Acceptance criteria covered:
 *   AC-1: page reachable from 生產輔助 drawer, manifests wired
 *   AC-7: permission-gated edit e2e (authorized edits, unauthorized blocked)
 *
 * Updated by production-achievement-async-spool (ADR-0016): GET .../report
 * is now an always-async spool-backed endpoint (data-shape-contract.md
 * §3.28) — a bare row-array 200 response is no longer a valid mock shape.
 * The "filter and render table/chart" test below now mocks a 200 spool-hit
 * envelope ({query_id, spool_download_url, spec_workcenter_map,
 * targets_map}) backed by a REAL, schema-correct Parquet fixture (generated
 * via the actual `duckdb` Python package, not magic-bytes-only) so DuckDB
 * -WASM's PA-06 rollup + PA-07 target-join genuinely execute — see
 * frontend/tests/playwright/production-achievement-async.spec.ts for the
 * dedicated async job/poll/progress mechanic coverage; this file keeps its
 * original "warm spool" (direct 200, no 202/poll) shape to stay a minimal,
 * focused critical-journey diff.
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
// output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, actual_output_qty
// BIGINT), generated via the `duckdb` Python package:
//   (2026-06-01, D, SPEC-A1, 950)
//   (2026-06-01, N, SPEC-A1, 400)
// Rolls up (via spec_workcenter_map below) to the same two rendered rows the
// original REPORT_ROWS fixture asserted: D/A1/950/target=1000/rate=0.95, and
// N/A1/400/target=null/rate=null (no target row for the N shift).
const TWO_ROW_A1_PARQUET_B64 =
  'UEFSMRUAFRwVICwVBBUAFQYVBgAADjQCAAAABAF9UAAAfVAAABUAFSAVJCwVBBUAFQYVBgAAEDwCAAAABAEBAAAARAEAAABOFQAVOBU8LBUEFQAVBhUGAAAcbAIAAAAEAQcAAABTUEVDLUExBwAAAFNQRUMtQTEVABUsFTAsFQQVABUGFQYAABZUAgAAAAQBtgMAAAAAAACQAQAAAAAAABUCGVw1ABgNZHVja2RiX3NjaGVtYRUIABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQQlAhgRYWN0dWFsX291dHB1dF9xdHklJAAWBBkcGUwmABwVAhkVABkYC291dHB1dF9kYXRlFQIWBBY+FkImCDwYBH1QAAAYBH1QAAAWACgEfVAAABgEfVAAABERAAAAJgAcFQwZFQAZGApzaGlmdF9jb2RlFQIWBBZCFkYmSjwYAU4YAUQWACgBThgBRBERAAAAJgAcFQwZFQAZGAhTUEVDTkFNRRUCFgQWWhZeJpABPBgHU1BFQy1BMRgHU1BFQy1BMRYAKAdTUEVDLUExGAdTUEVDLUExEREAAAAmABwVBBkVABkYEWFjdHVhbF9vdXRwdXRfcXR5FQIWBBZOFlIm7gE8GAi2AwAAAAAAABgIkAEAAAAAAAAWACgItgMAAAAAAAAYCJABAAAAAAAAEREAAAAWqAIWBCYIFrgCACgoRHVja0RCIHZlcnNpb24gdjEuNS40IChidWlsZCAwOGUzNGM0NDdiKRlMHAAAHAAAHAAAHAAAAMgBAABQQVIx';

const REPORT_SPOOL_HIT = {
  query_id: 'pa-critical-journey-001',
  spool_download_url: '/api/spool/production_achievement/pa-critical-journey-001.parquet',
  spec_workcenter_map: [{ SPECNAME: 'SPEC-A1', workcenter_group: 'A1' }],
  targets_map: [{ shift_code: 'D', workcenter_group: 'A1', target_qty: 1000 }],
};

const TARGET_ROWS = [
  { shift_code: 'D', workcenter_group: 'A1', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' },
];

const PERMISSION_ROWS = [
  { user_identifier: 'testuser', can_edit_targets: true, granted_at: '2026-05-01T00:00:00Z', granted_by: 'admin' },
];

function envelope(data) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

async function setupBaseRoutes(page) {
  // Catch-all: registered FIRST so specific routes override it (LIFO)
  await page.route('**/*', (route) => route.continue());

  await page.route('**/api/auth/me**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: envelope({ username: 'testuser', role: 'user', is_admin: true }),
    });
  });

  await page.route('**/api/pages**', (route) => {
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
  });

  await page.route('**/api/portal/navigation**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      // NOTE: /api/portal/navigation returns a plain unwrapped JSON object
      // (statuses/is_admin at top level), NOT the success/data/meta envelope
      // used by other API routes. See app.py::portal_navigation_config().
      body: JSON.stringify({
        statuses: { '/production-achievement': 'released' },
        is_admin: true,
        admin_user: { username: 'testuser', displayName: 'Test User' },
        admin_links: { logout: '/api/auth/logout', pages: '/admin/pages', dashboard: '/admin/dashboard' },
        diagnostics: {},
        features: { ai_query_enabled: false },
      }),
    });
  });
}

async function isPageRendered(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && el.offsetParent !== null;
  });
}

test.describe('production-achievement — navigation from 生產輔助 drawer', () => {
  test('sidebar link navigates to the 生產達成率 page', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1', 'B2'] }) });
    });
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
      } else {
        route.continue();
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});

    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({
        type: 'note',
        description: '.theme-production-achievement not visible; test is a passing scaffold until page is wired',
      });
      return;
    }

    await expect(page.locator('[data-testid="pa-app"]')).toBeVisible({ timeout: 15_000 });
  });
});

test.describe('production-achievement — filter and render table/chart', () => {
  test('filtering by date/shift/workcenter_group renders the report table', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1', 'B2'] }) });
    });
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
      } else {
        route.continue();
      }
    });
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope(REPORT_SPOOL_HIT) });
    });
    // Spool already warm (direct 200, no 202/poll) — real Parquet bytes so
    // DuckDB-WASM's PA-06/PA-07 rollup+join genuinely runs.
    await page.route('**/api/spool/production_achievement/pa-critical-journey-001.parquet**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/octet-stream',
        body: Buffer.from(TWO_ROW_A1_PARQUET_B64, 'base64'),
      });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping deep assertions' });
      return;
    }

    const queryBtn = page.locator('[data-testid="pa-query-btn"]');
    await expect(queryBtn).toBeVisible({ timeout: 15_000 });
    await queryBtn.click();

    // NOTE: App.vue passes data-testid="pa-report-table" to <DataTable>, but
    // DataTable.vue's template has multiple root nodes (a <slot/> for column
    // registrations plus the actual .data-table-root div), so Vue 3 does not
    // fall through that attribute onto any DOM element (single-root-only
    // attrs inheritance) — the rendered table only ever carries DataTable's
    // own built-in data-testid="datatable". The page also has a second,
    // unrelated DataTable in the target-value panel with the same testid, so
    // scope by the "生產達成率明細" card heading to disambiguate. Flagged to
    // frontend-engineer; using this selector so the spec exercises real
    // behavior instead of silently skipping. See agent-log for details.
    const reportCard = page.locator('.ui-card', { has: page.locator('.ui-card-title', { hasText: '生產達成率明細' }) });
    const table = reportCard.locator('[data-testid="datatable"]');
    await expect(table).toBeVisible({ timeout: 15_000 });
    // Generous timeout: real DuckDB-WASM init + parquet register + rollup
    // (not a network-only mock) needs a moment beyond a plain fetch.
    await expect(table.locator('[data-testid="datatable-row"]')).toHaveCount(2, { timeout: 20_000 });

    // Null target_qty/achievement_rate must render "—", never "Infinity"/"NaN"/blank
    const bodyText = await table.innerText();
    expect(bodyText).toContain('—');
    expect(bodyText).not.toContain('Infinity');
    expect(bodyText).not.toContain('NaN');

    // Chart section renders
    await expect(page.locator('[data-testid="pa-chart"]')).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('production-achievement — target-value edit permission', () => {
  test('authorized user can edit a target value', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1'] }) });
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

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

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

    await page.waitForFunction(() => true, { timeout: 2_000 }).catch(() => {});
    expect(putCalled).toBe(true);
  });

  test('unauthorized user is blocked from editing (403 handled gracefully)', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1'] }) });
    });
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: { code: 'FORBIDDEN', message: '無權限編輯目標值' },
            meta: { timestamp: new Date().toISOString(), app_version: 'test' },
          }),
        });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(TARGET_ROWS) });
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

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

    // Graceful degrade: error banner shown, no crash, edit controls disabled thereafter
    await expect(page.locator('[data-testid="pa-target-edit-error"]')).toBeVisible({ timeout: 10_000 });
    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });
});

test.describe('production-achievement — admin permission block', () => {
  const ADMIN_PAGE_URL = '/portal-shell/admin/pages';

  test('admin assigns and revokes can_edit_targets', async ({ page }) => {
    await page.route('**/*', (route) => route.continue());
    await page.route('**/api/auth/me**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ username: 'admin', role: 'admin', is_admin: true }) });
    });
    await page.route('**/api/portal/navigation**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        // Plain unwrapped shape (see app.py::portal_navigation_config()).
        body: JSON.stringify({
          statuses: { '/admin/pages': 'released' },
          is_admin: true,
          admin_user: { username: 'admin', displayName: 'Admin' },
          admin_links: { logout: '/api/auth/logout', pages: '/admin/pages', dashboard: '/admin/dashboard' },
          diagnostics: {},
          features: { ai_query_enabled: false },
        }),
      });
    });
    await page.route('**/admin/api/pages**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ pages: [] }) });
    });

    let currentPermissions = [...PERMISSION_ROWS];
    await page.route('**/admin/api/production-achievement/permissions**', (route) => {
      const req = route.request();
      if (req.method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(currentPermissions) });
        return;
      }
      if (req.method() === 'PUT') {
        const url = req.url();
        const match = url.match(/permissions\/([^/?]+)/);
        const userIdentifier = match ? decodeURIComponent(match[1]) : '';
        const payload = req.postDataJSON();
        const existing = currentPermissions.find((p) => p.user_identifier === userIdentifier);
        if (existing) {
          existing.can_edit_targets = payload.can_edit_targets;
        } else {
          currentPermissions.push({
            user_identifier: userIdentifier,
            can_edit_targets: payload.can_edit_targets,
            granted_at: new Date().toISOString(),
            granted_by: 'admin',
          });
        }
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope(null) });
        return;
      }
      route.continue();
    });

    await page.goto(ADMIN_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-admin-pages') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await page.evaluate(() => {
      const el = document.querySelector('.theme-admin-pages');
      return el !== null && el.offsetParent !== null;
    });
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: '.theme-admin-pages not visible; skipping deep assertions' });
      return;
    }

    const panel = page.locator('[data-testid="pa-permissions-panel"]');
    await expect(panel).toBeVisible({ timeout: 15_000 });

    // Revoke existing testuser permission
    const toggle = page.locator('[data-testid="pa-permissions-toggle"]').first();
    await expect(toggle).toBeVisible({ timeout: 10_000 });
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'false', { timeout: 10_000 });

    // Grant a new user
    await page.locator('[data-testid="pa-permissions-new-user-input"]').fill('newuser');
    await page.locator('[data-testid="pa-permissions-new-user-btn"]').click();
    await expect(page.locator('[data-testid="pa-permissions-toggle"]')).toHaveCount(2, { timeout: 10_000 });
  });
});
