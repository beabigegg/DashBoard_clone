/**
 * E2E spec: EAP ALARM Analysis page
 *
 * Pattern: catch-all routes FIRST (lowest LIFO priority), specific routes LAST.
 * pageRendered guard: checks .theme-eap-alarm presence (not bodyText.length > 100).
 * DetailTable only renders after queryId is set — always submit before asserting.
 * Uses page.goto(...).catch(()=>{}) + early-return guard (ci-workflow.md).
 *
 * All API calls are mocked (no Oracle dependency).
 */

import { test, expect } from '@playwright/test';
import { navigateViaSidebar } from './_auth.js';

const MOCK_QUERY_ID = 'test-eap-alarm-query-001';

const MOCK_SPOOL_202 = {
  success: true,
  data: {
    async: true,
    job_id: 'eap-job-001',
    query_id: MOCK_QUERY_ID,
    status_url: '/api/eap-alarm/spool/status?query_id=' + MOCK_QUERY_ID,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_SPOOL_STATUS_FINISHED = {
  success: true,
  data: {
    status: 'finished',
    pct: 100,
    progress: '查詢完成',
    elapsed_seconds: 5,
    query_id: MOCK_QUERY_ID,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_FILTER_OPTIONS = {
  success: true,
  data: {
    alarm_text_options: ['ALARM_TEST_A', 'ALARM_TEST_B'],
    alarm_category_options: [
      { code: 1, label: '設備警告' },
      { code: 2, label: '通訊錯誤' },
    ],
    equipment_id_options: ['GDBA-001', 'GCBA-002'],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_SUMMARY = {
  success: true,
  data: {
    total_alarm_count: 250,
    affected_equipment_count: 12,
    affected_lot_count: 8,
    top_equipment: { eqp_id: 'GDBA-001', alarm_count: 80 },
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_PARETO = {
  success: true,
  data: {
    items: [
      { alarm_text: 'ALARM_TEST_A', count: 150, cumulative_pct: 60.0 },
      { alarm_text: 'ALARM_TEST_B', count: 100, cumulative_pct: 100.0 },
    ],
    total: 250,
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_TREND = {
  success: true,
  data: {
    labels: ['2026-06-12', '2026-06-13', '2026-06-14'],
    series: [
      { eqp_type: 'GDBA', data: [50, 60, 40] },
      { eqp_type: 'GCBA', data: [30, 20, 50] },
    ],
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

const MOCK_DETAIL = {
  success: true,
  data: {
    rows: [
      {
        event_id: 'EV-001',
        eqp_id: 'GDBA-001',
        eqp_type: 'GDBA',
        lot_id: 'LOT-001',
        alarm_text: 'ALARM_TEST_A',
        alarm_category: '設備警告',
        alarm_time: '2026-06-12 10:30:00',
        detail_params: { param_key: 'param_value', threshold: 95.5 },
      },
      {
        event_id: 'EV-002',
        eqp_id: 'GCBA-002',
        eqp_type: 'GCBA',
        lot_id: null,
        alarm_text: 'ALARM_TEST_B',
        alarm_category: '通訊錯誤',
        alarm_time: '2026-06-12 11:00:00',
        detail_params: null,
      },
    ],
    meta: {
      page: 1,
      per_page: 20,
      total_count: 2,
      total_pages: 1,
    },
  },
  meta: { timestamp: new Date().toISOString(), app_version: 'test' },
};

/**
 * Register API mocks.
 * LIFO rule: catch-all registered FIRST (lowest priority),
 * specific routes registered LAST (highest priority).
 */
async function setupEapAlarmMocks(page) {
  // Catch-all for all eap-alarm endpoints (lowest LIFO priority)
  await page.route('**/api/eap-alarm/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    })
  );

  // Job status polling endpoint (catch-all for job status)
  await page.route('**/api/eap-alarm/spool/status**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SPOOL_STATUS_FINISHED),
    })
  );

  // Specific data endpoints (highest LIFO priority)
  await page.route('**/api/eap-alarm/detail**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DETAIL),
    })
  );

  await page.route('**/api/eap-alarm/trend**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_TREND),
    })
  );

  await page.route('**/api/eap-alarm/pareto**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PARETO),
    })
  );

  await page.route('**/api/eap-alarm/summary**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUMMARY),
    })
  );

  await page.route('**/api/eap-alarm/filter-options**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    })
  );

  // Spool POST endpoint (returns 202 async) — registered last for highest priority
  await page.route('**/api/eap-alarm/spool', (route) =>
    route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SPOOL_202),
    })
  );
}

/**
 * Submit the coarse filter form and wait for spool + fine filter panel.
 * DetailTable only renders after queryId is set (ci-workflow.md).
 */
async function submitAndWaitForResults(page) {
  // Fill in dates if not already set
  const dateFrom = page.locator('input[type="date"]').first();
  const dateTo = page.locator('input[type="date"]').nth(1);
  if (await dateFrom.count() > 0) {
    const fromVal = await dateFrom.inputValue();
    if (!fromVal) await dateFrom.fill('2026-06-12');
  }
  if (await dateTo.count() > 0) {
    const toVal = await dateTo.inputValue();
    if (!toVal) await dateTo.fill('2026-06-18');
  }

  const submitBtn = page.locator('button:has-text("查詢")').first();
  await expect(submitBtn).toBeVisible({ timeout: 10_000 });
  await submitBtn.click();

  // Wait for async job progress to complete and fine filter panel to appear
  await page.waitForFunction(
    () => {
      const progressBar = document.querySelector('.async-job-progress');
      if (progressBar) return false;
      // Fine filter panel should appear after spool completes
      return Boolean(
        document.querySelector('.fine-filter-panel') ||
        document.querySelector('.fine-filter-body') ||
        document.querySelector('.eap-alarm-filter-fine')
      ) || Boolean(
        // Or summary cards visible
        document.querySelector('.summary-card-group') ||
        document.querySelector('[class*="summary"]')
      );
    },
    { timeout: 30_000, polling: 500 },
  );
}

test.describe('EAP ALARM Analysis page', () => {
  test.beforeEach(async ({ page }) => {
    await setupEapAlarmMocks(page);

    // Use page.goto().catch(()=>{}) pattern + early-return guard (ci-workflow.md)
    let navigationFailed = false;
    await page.goto('/portal-shell/').catch(() => { navigationFailed = true; });
    if (navigationFailed) return;

    // pageRendered guard: check .theme-eap-alarm in body (not bodyText.length > 100)
    const body = await page.locator('body').textContent({ timeout: 5_000 }).catch(() => '');
    if (!body) return;

    // Navigate to EAP ALARM via sidebar
    await navigateViaSidebar(page, 'eap-alarm', {
      waitForSelector: 'input[type="date"]',
    }).catch(() => {});
  });

  test('page loads with coarse filter panel visible', async ({ page }) => {
    // Check theme class is present (pageRendered guard pattern)
    const hasTheme = await page.evaluate(() =>
      Boolean(document.querySelector('.theme-eap-alarm'))
    );
    if (!hasTheme) {
      test.skip(true, 'EAP ALARM page not reachable in this environment');
      return;
    }

    const dateInput = page.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible({ timeout: 15_000 });
  });

  test('coarse filter submit triggers async spool and shows fine filter panel', async ({ page }) => {
    const hasTheme = await page.evaluate(() =>
      Boolean(document.querySelector('.theme-eap-alarm'))
    );
    if (!hasTheme) {
      test.skip(true, 'EAP ALARM page not reachable in this environment');
      return;
    }

    await submitAndWaitForResults(page);

    // Fine filter section should be visible after spool completes
    const fineFilter = page.locator('.fine-filter-body, .fine-filter-panel, [class*="fine-filter"]');
    const resultArea = page.locator('.ui-card, .summary-card-group, table');
    await expect(fineFilter.or(resultArea).first()).toBeVisible({ timeout: 15_000 });
  });

  test('Pareto chart renders after spool completes', async ({ page }) => {
    const hasTheme = await page.evaluate(() =>
      Boolean(document.querySelector('.theme-eap-alarm'))
    );
    if (!hasTheme) {
      test.skip(true, 'EAP ALARM page not reachable in this environment');
      return;
    }

    // Submit first (DetailTable + charts only render after queryId is set)
    await submitAndWaitForResults(page);

    await page.waitForFunction(
      () => {
        const canvas = document.querySelector('.pareto-chart canvas, [class*="pareto"] canvas');
        const emptyState = document.querySelector('[class*="pareto-empty"]');
        return Boolean(canvas || emptyState);
      },
      { timeout: 20_000, polling: 500 },
    );

    // Either chart canvas or empty state should be present
    const chartOrEmpty = page.locator(
      '.pareto-chart canvas, [class*="pareto"] canvas, [class*="pareto-empty"]'
    );
    await expect(chartOrEmpty.first()).toBeVisible({ timeout: 10_000 });
  });

  test('Detail table row expansion shows detail_params JSON', async ({ page }) => {
    const hasTheme = await page.evaluate(() =>
      Boolean(document.querySelector('.theme-eap-alarm'))
    );
    if (!hasTheme) {
      test.skip(true, 'EAP ALARM page not reachable in this environment');
      return;
    }

    // Always submit before asserting table content (ci-workflow.md)
    await submitAndWaitForResults(page);

    // Wait for detail table to appear
    await page.waitForFunction(
      () => Boolean(document.querySelector('table tbody tr, .data-table-row')),
      { timeout: 20_000, polling: 500 },
    );

    // Click expand button on first expandable row
    const expandBtn = page.locator(
      '.data-table-expand-btn, button[aria-expanded]'
    ).first();

    if (await expandBtn.count() === 0) {
      // No expandable rows in test environment — skip
      return;
    }

    await expandBtn.click();

    // Wait for expanded content containing detail_params JSON
    await page.waitForFunction(
      () => Boolean(
        document.querySelector('.detail-params-pre, .detail-params-expand, .data-table-expand-td')
      ),
      { timeout: 10_000, polling: 300 },
    );

    const expandedContent = page.locator(
      '.detail-params-pre, .detail-params-expand, .data-table-expand-td'
    ).first();
    await expect(expandedContent).toBeVisible({ timeout: 5_000 });

    // Content should contain JSON-like text (param_key or threshold)
    const text = await expandedContent.textContent({ timeout: 5_000 });
    expect(text).toMatch(/param_key|threshold|param_value/i);
  });

  test('summary cards display alarm count after spool', async ({ page }) => {
    const hasTheme = await page.evaluate(() =>
      Boolean(document.querySelector('.theme-eap-alarm'))
    );
    if (!hasTheme) {
      test.skip(true, 'EAP ALARM page not reachable in this environment');
      return;
    }

    await submitAndWaitForResults(page);

    // Wait for summary data (250 alarms from mock)
    await page.waitForFunction(
      () => {
        const text = document.body.textContent || '';
        return text.includes('250') || text.includes('總 ALARM') || text.includes('ALARM 數');
      },
      { timeout: 15_000, polling: 500 },
    );

    const summaryArea = page.locator('[class*="summary"], .summary-card-group');
    await expect(summaryArea.first()).toBeVisible({ timeout: 10_000 });
  });
});
