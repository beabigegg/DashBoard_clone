import { test, expect } from '@playwright/test';

import { loginViaApi, navigateViaSidebar } from './_auth.js';

async function openQueryToolUrlWithRetry(page, fullUrl) {
  const tabNavSelector = 'nav[aria-label="query-tool tabs"]';
  await page.goto(fullUrl);
  const hasTabNav = await page
    .waitForSelector(tabNavSelector, { timeout: 5_000 })
    .then(() => true)
    .catch(() => false);

  if (hasTabNav) {
    return;
  }

  await navigateViaSidebar(page, 'query-tool', { waitForSelector: tabNavSelector });
  const parsed = new URL(fullUrl, 'http://127.0.0.1:8080');
  await page.evaluate((search) => {
    const url = new URL(window.location.href);
    url.search = search;
    window.history.replaceState({}, '', url.toString());
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, parsed.search);
  await page.waitForSelector(tabNavSelector, { timeout: 15_000 });
}

test.describe('Query Tool URL state persistence', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/query-tool/workcenter-groups**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            data: [
              { name: '焊接_WB' },
              { name: '焊接_DB' },
            ],
          },
        }),
      });
    });

    await page.route('**/api/query-tool/equipment-list**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            data: [
              { RESOURCEID: 'EQ-01', RESOURCENAME: 'Wire Bonder 01' },
              { RESOURCEID: 'EQ-02', RESOURCENAME: 'Die Bonder 02' },
            ],
          },
        }),
      });
    });

    await loginViaApi(page);
    await navigateViaSidebar(page, 'query-tool', {
      waitForSelector: 'textarea.query-tool-textarea, input[type="date"]',
    });
  });

  test('preserves equipment URL state across reload', async ({ page }) => {
    const equipmentTab = page.getByRole('button', { name: '設備生產批次追蹤' });
    await equipmentTab.click();

    const dateInputs = page.locator('input[type="date"]:visible');
    await expect(dateInputs.first()).toBeVisible({ timeout: 10_000 });
    await dateInputs.nth(0).fill('2026-03-01');
    await dateInputs.nth(1).fill('2026-03-07');

    await page.getByRole('button', { name: '維修紀錄' }).click();

    await expect.poll(() => page.url()).toContain('tab=equipment');
    const equipmentUrl = new URL(page.url());
    expect(equipmentUrl.searchParams.get('start_date')).toBe('2026-03-01');
    expect(equipmentUrl.searchParams.get('end_date')).toBe('2026-03-07');
    expect(equipmentUrl.searchParams.get('equipment_sub_tab')).toBe('jobs');

    await openQueryToolUrlWithRetry(page, `/portal-shell/query-tool?${equipmentUrl.searchParams.toString()}`);
    await expect(page.getByRole('button', { name: '設備生產批次追蹤' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('button', { name: '維修紀錄', exact: true })).toHaveClass(/active/);
    await expect(page.locator('input[type="date"]:visible').nth(0)).toHaveValue('2026-03-01');
    await expect(page.locator('input[type="date"]:visible').nth(1)).toHaveValue('2026-03-07');

  });
});
