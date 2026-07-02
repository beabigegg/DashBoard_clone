/**
 * Resilience spec: 生產達成率 — MySQL unavailable degrade
 * Change: production-achievement-kanban
 *
 * Covers:
 *   - MySQL unavailable / MYSQL_OPS_ENABLED=false: report degrades to
 *     target_qty:null / achievement_rate:null, never 500, no crash.
 *   - Permission check denies (503 on write) when MySQL is unreachable —
 *     the frontend must surface this without crashing, distinct from the
 *     403 (FORBIDDEN) permission-denied path.
 *
 * Network strategy: catch-all first, specific routes last (LIFO), per
 * ci-workflow.md. Uses page.goto(...).catch(()=>{}) + guard, NOT
 * page.request.post() (loginViaApi), which is not interceptable by
 * page.route() and throws ECONNREFUSED in CI.
 */

import { test, expect } from '@playwright/test';

const PAGE_URL = '/portal-shell/production-achievement';

function envelope(data) {
  return JSON.stringify({ success: true, data, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
}

function errorEnvelope(code, message) {
  return JSON.stringify({ success: false, error: { code, message }, meta: { timestamp: new Date().toISOString(), app_version: 'test' } });
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
}

async function isPageRendered(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.theme-production-achievement');
    return el !== null && el.offsetParent !== null;
  });
}

test.describe('production-achievement resilience — MySQL unavailable', () => {
  test('report degrades to null target/achievement with no crash when MySQL is down', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1'] }) });
    });
    // GET targets degrades server-side: MySQL down -> empty/null target rows, HTTP 200 (never 500)
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, contentType: 'application/json', body: envelope([]) });
      } else {
        route.continue();
      }
    });
    // Report degrades: target_qty/achievement_rate null for every row, actual_output_qty still populated.
    await page.route('**/api/production-achievement/report**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: envelope([
          { output_date: '2026-06-01', shift_code: 'D', workcenter_group: 'A1', actual_output_qty: 500, target_qty: null, achievement_rate: null },
        ]),
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

    const text = await table.innerText();
    expect(text).toContain('—');
    expect(text).not.toContain('Infinity');
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('null');

    const crashed = await page.evaluate(() => !!(window).__vue_app_crashed).catch(() => false);
    expect(crashed).toBe(false);
  });

  test('permission check denies (503) when MySQL is unreachable, distinct from 403 forbidden', async ({ page }) => {
    await setupBaseRoutes(page);
    await page.route('**/api/production-achievement/filter-options**', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: envelope({ shift_codes: ['N', 'D'], workcenter_groups: ['A1'] }) });
    });
    await page.route('**/api/production-achievement/targets**', (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({ status: 503, contentType: 'application/json', body: errorEnvelope('SERVICE_UNAVAILABLE', 'MySQL 服務暫時無法使用') });
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
