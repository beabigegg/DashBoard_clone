import { test, expect } from '@playwright/test';

import { loginViaApi, navigateViaSidebar } from './_auth.js';

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

  test.fixme('preserves equipment and lot-equipment URL state across reload', async ({ page }) => {
    // PRODUCT_BUG T009: equipment tab does not restore aria-current state after hard reload.
    // Tracked in: openspec/changes/fix-query-tool-equipment-tab-url-state/
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

    await page.reload();
    await expect(page.getByRole('button', { name: '設備生產批次追蹤' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('button', { name: '維修紀錄' })).toHaveClass(/active/);
    await expect(page.locator('input[type="date"]:visible').nth(0)).toHaveValue('2026-03-01');
    await expect(page.locator('input[type="date"]:visible').nth(1)).toHaveValue('2026-03-07');

    const lotEquipmentTab = page.getByRole('button', { name: '批次追蹤生產設備' });
    await lotEquipmentTab.click();

    const workcenterTrigger = page.locator('.multi-select-trigger:visible').first();
    await workcenterTrigger.click();
    await page.getByRole('button', { name: /焊接_WB/ }).click();
    await page.getByRole('button', { name: '關閉' }).click();

    const lotEquipmentTextarea = page.locator('textarea.query-tool-textarea:visible');
    await lotEquipmentTextarea.fill('LOT-001');
    await page.getByRole('button', { name: '報廢紀錄' }).click();

    await expect.poll(() => page.url()).toContain('tab=lot_equipment');
    const lotEquipmentUrl = new URL(page.url());
    expect(lotEquipmentUrl.searchParams.get('le_input_text')).toBe('LOT-001');
    expect(lotEquipmentUrl.searchParams.get('le_sub_tab')).toBe('rejects');
    expect(lotEquipmentUrl.searchParams.getAll('le_workcenter_groups')).toContain('焊接_WB');

    await page.reload();
    await expect(page.getByRole('button', { name: '批次追蹤生產設備' })).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('textarea.query-tool-textarea:visible')).toHaveValue('LOT-001');
    await expect(page.getByRole('button', { name: '報廢紀錄' })).toHaveClass(/active/);
    await expect(page.locator('.multi-select-trigger:visible .multi-select-text')).toContainText('焊接_WB');
  });
});
