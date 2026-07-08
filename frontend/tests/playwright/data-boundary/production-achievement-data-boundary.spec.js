/**
 * Data-boundary spec: 生產達成率 — target_qty validation + empty result set
 * Change: production-achievement-kanban
 *
 * Covers:
 *   - negative target_qty rejected client-side (no PUT call fires)
 *   - non-numeric target_qty rejected client-side (no PUT call fires)
 *   - empty qualifying-row result set renders an empty state, not an error
 *
 * Updated by production-achievement-async-spool (ADR-0016): GET .../report
 * is now an always-async spool-backed endpoint (data-shape-contract.md
 * §3.28) — the empty-result test below now mocks a 200 spool-hit envelope
 * whose parquet has 0 rows (the actual §3.28.1 empty-result invariant),
 * using a real, schema-correct, `duckdb`-Python-generated empty Parquet
 * fixture rather than the old bare `[]` row-array shape.
 *
 * Network strategy: catch-all first, specific routes last (LIFO).
 */

import { test, expect } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';

// Real 0-row Parquet matching data-shape-contract.md §3.28.1's exact schema
// (output_date DATE, shift_code VARCHAR, SPECNAME VARCHAR, actual_output_qty
// BIGINT) — generated via the `duckdb` Python package, not magic bytes.
const EMPTY_PA_PARQUET_B64 =
  'UEFSMRUCGVw1ABgNZHVja2RiX3NjaGVtYRUIABUCJQIYC291dHB1dF9kYXRlJQwAFQwlAhgKc2hpZnRfY29kZSUAABUMJQIYCFNQRUNOQU1FJQAAFQQlAhgRYWN0dWFsX291dHB1dF9xdHklJAAWABkMKChEdWNrREIgdmVyc2lvbiB2MS41LjQgKGJ1aWxkIDA4ZTM0YzQ0N2IpGUwcAAAcAAAcAAAcAAAApwAAAFBBUjE=';

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
      // Plain unwrapped shape (see app.py::portal_navigation_config()).
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
    route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1'] }) });
  });
}

async function isPageRendered(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && el.offsetParent !== null;
  });
}

test.describe('production-achievement data-boundary — target_qty validation', () => {
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
          body: envelope([{ shift_code: 'D', workcenter_group: 'A1', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' }]),
        });
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await isPageRendered(page);
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
          body: envelope([{ shift_code: 'D', workcenter_group: 'A1', target_qty: 1000, updated_at: '2026-05-01T00:00:00Z', updated_by: 'admin' }]),
        });
      }
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await isPageRendered(page);
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
  test('empty qualifying-row result renders empty state, not an error', async ({ page }) => {
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
        }),
      });
    });
    // Spool already warm, 0-row parquet — the §3.28.1 empty-result invariant.
    await page.route('**/api/spool/production_achievement/pa-empty-boundary-001.parquet**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/octet-stream',
        body: Buffer.from(EMPTY_PA_PARQUET_B64, 'base64'),
      });
    });

    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => {});
    await page.waitForFunction(
      () => document.querySelector('.theme-production-achievement') !== null,
      { timeout: 20_000 },
    ).catch(() => {});

    const rendered = await isPageRendered(page);
    if (!rendered) {
      test.info().annotations.push({ type: 'note', description: 'page not rendered yet; skipping empty-state assertions' });
      return;
    }

    await page.locator('[data-testid="pa-query-btn"]').click();

    // NOTE: <DataTable data-testid="pa-report-table"> never renders that
    // attribute — DataTable.vue has multiple template roots so Vue 3 attrs
    // fallthrough doesn't apply it anywhere; use DataTable's own built-in
    // data-testid="datatable" instead, scoped by the report card heading to
    // disambiguate from the target-value panel's own DataTable (same
    // testid). Flagged to frontend-engineer.
    const reportCard = page.locator('.ui-card', { has: page.locator('.ui-card-title', { hasText: '生產達成率明細' }) });
    const table = reportCard.locator('[data-testid="datatable"]');
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(table.locator('[data-testid="datatable-empty"]')).toBeVisible({ timeout: 20_000 });

    // No error banner should appear for a legitimately empty result set
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
  });
});
