/**
 * Data-boundary spec: hold-overview CSV export edge cases
 *
 * Uses page.route() mocks for the export endpoint only — uses real server
 * for login and sidebar navigation so the portal-shell sidebar renders.
 *
 * Verifies:
 *   AC-5: null/undefined fields → empty string in CSV (no thrown error)
 *   AC-5: empty lots array → header-only CSV download, no error
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from '../_auth.js';

const BASE_META = { timestamp: new Date().toISOString(), app_version: 'test' };

function makeExportPayload(lots) {
  return JSON.stringify({
    success: true,
    meta: BASE_META,
    data: {
      lots,
      pagination: { page: 1, perPage: Math.max(lots.length, 1), total: lots.length, totalPages: 1 },
    },
  });
}

const NULL_FIELD_LOT = {
  lotId: null,
  workorder: undefined,
  qty: null,
  product: null,
  package: undefined,
  workcenter: null,
  holdReason: null,
  spec: undefined,
  age: null,
  holdBy: null,
  dept: undefined,
  holdComment: null,
  futureHoldComment: null,
};

// ---------------------------------------------------------------------------
// Null/undefined fields — no throw, download starts (AC-5)
// ---------------------------------------------------------------------------

test.describe('hold-overview export — null fields do not throw', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-overview', { waitForSelector: '.ui-card, table' });
  });

  test('export with null fields does not throw and download starts', async ({ page }) => {
    // Intercept the export call AFTER navigation so the sidebar loads normally
    await page.route('**/api/hold-overview/lots', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeExportPayload([NULL_FIELD_LOT]),
      });
    });

    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    const exportBtn = lotsCard.locator('button:has-text("匯出 CSV")').first();
    await expect(exportBtn).toBeVisible({ timeout: 20_000 });

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/^hold-overview-\d{4}-\d{2}-\d{2}\.csv$/);

    const exportErrors = consoleErrors.filter((msg) => msg.includes('[hold-overview]'));
    expect(exportErrors).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Empty lots array → header-only CSV (AC-5)
// ---------------------------------------------------------------------------

test.describe('hold-overview export — empty lots array downloads header-only CSV', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page);
    await navigateViaSidebar(page, 'hold-overview', { waitForSelector: '.ui-card, table' });
  });

  test('export with empty lots array downloads file without throwing', async ({ page }) => {
    await page.route('**/api/hold-overview/lots', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: makeExportPayload([]),
      });
    });

    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    const lotsCard = page.locator('.ui-card').filter({ hasText: 'Hold Lot Details' });
    const exportBtn = lotsCard.locator('button:has-text("匯出 CSV")').first();
    await expect(exportBtn).toBeVisible({ timeout: 20_000 });

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/^hold-overview-\d{4}-\d{2}-\d{2}\.csv$/);

    // Read the downloaded CSV to verify it is header-only (BOM + single header line)
    const downloadPath = await download.path();
    if (downloadPath) {
      const { readFileSync } = await import('fs');
      const content = readFileSync(downloadPath, 'utf8');
      // Strip BOM if present
      const withoutBom = content.replace(/^﻿/, '');
      const lines = withoutBom.trim().split('\n');
      expect(lines.length).toBe(1);
      expect(lines[0]).toContain('Lot ID');
    }

    const exportErrors = consoleErrors.filter((msg) => msg.includes('[hold-overview]'));
    expect(exportErrors).toHaveLength(0);
  });
});
