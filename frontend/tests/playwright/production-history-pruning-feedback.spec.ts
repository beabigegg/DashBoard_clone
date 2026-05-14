/**
 * E2E spec: Production History — fail-open auto-pruning notice (UI-UX REC-02)
 *
 * Stubs filter-options to drop the user's BOP selection on the next response
 * (simulating a Package change that excludes the chosen BOP).  Verifies:
 *   - the `[data-testid="ph-first-tier-pruned-notice"]` element appears
 *   - the notice auto-clears after ~3 s
 */

import { test, expect, type Page } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

async function installPruningMock(page: Page) {
  let callCount = 0;
  await page.route('**/api/production-history/filter-options**', async (route) => {
    callCount += 1;
    const url = new URL(route.request().url());
    const raw = url.searchParams.get('selected') || '';
    // First two responses include BOP-A, BOP-B (so user can pick BOP-B).
    // Once Package is set, drop BOP-B from the response → triggers pruning.
    let bops = ['BOP-A', 'BOP-B'];
    if (raw && raw.includes('packages')) {
      bops = ['BOP-A'];
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          pj_types: ['A', 'B'],
          packages: ['PKG-1', 'PKG-2'],
          bops,
          pj_functions: ['FN-X'],
        },
        meta: {
          updated_at: '2026-05-14T00:00:00Z',
          schema_version: 2,
          timestamp: new Date().toISOString(),
          app_version: 'test',
        },
      }),
    });
  });
  return { getCallCount: () => callCount };
}

async function pickByTestidLabel(page: Page, testid: string, label: string) {
  const root = page.locator(`[data-testid="${testid}"]`);
  await root.locator('.multi-select-trigger, button, [role="combobox"]').first().click();
  const opt = page
    .locator('.multi-select-option, [role="option"], label')
    .filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) })
    .first();
  await expect(opt).toBeVisible({ timeout: 10_000 });
  await opt.click();
  await page.locator('body').click({ position: { x: 5, y: 5 } });
}

test.describe('Production History — pruning feedback', () => {
  test('Pruned notice appears, then auto-clears', async ({ page }) => {
    await installPruningMock(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-bop"]',
    });

    // Wait for initial fetch.
    await page.waitForResponse(
      (r) =>
        r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 15_000 },
    );

    // Pick BOP-B
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(400); // debounce

    // Now pick Package PKG-1 — backend mock will respond with bops=[BOP-A]
    // so BOP-B is no longer present → frontend prunes & shows the notice.
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/production-history/filter-options') &&
        decodeURIComponent(new URL(r.url()).searchParams.get('selected') || '').includes(
          'packages',
        ),
      { timeout: 10_000 },
    );
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    await responsePromise;

    // Pruning notice must appear.
    const notice = page.locator('[data-testid="ph-first-tier-pruned-notice"]');
    await expect(notice).toBeVisible({ timeout: 5_000 });

    // After ~3 s the notice should auto-clear (allow 4 s slack).
    await expect(notice).toBeHidden({ timeout: 5_000 });
  });
});
