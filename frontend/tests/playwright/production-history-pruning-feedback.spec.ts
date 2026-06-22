/**
 * E2E spec: Production History — fail-open auto-pruning notice (UI-UX REC-02)
 *
 * All tests in this file are CONTROLLED MOCK tests: they always use
 * navigateMocked() regardless of USE_MOCKS mode, because they depend on
 * specific mock API behaviour (a BOP being dropped from a filter-options
 * response) that cannot be reproduced with a real backend.
 *
 * Scenarios covered:
 *   1. Pruned notice appears, then auto-clears (baseline: existing test)
 *   2. Pruning does not block subsequent query submission
 *   3. Pruning of multiple fields (BOP + Function) still shows notice once
 *   4. Consecutive pruning events reset the auto-clear timer
 */

import { test, expect, type Page } from '@playwright/test';
import { navigateMocked } from './_api-mode.js';

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

/**
 * Install the standard single-field pruning mock.
 *
 * Initial responses (no Package selected): bops = ['BOP-A', 'BOP-B'].
 * Once a Package appears in the `selected` param: bops = ['BOP-A'] only.
 * BOP-B disappears → frontend prunes the user's BOP-B selection and shows
 * the pruned notice.
 */
async function installPruningMock(page: Page): Promise<{ getCallCount: () => number }> {
  let callCount = 0;
  await page.route('**/api/production-history/filter-options**', async (route) => {
    callCount += 1;
    const url = new URL(route.request().url());
    const raw = url.searchParams.get('selected') || '';
    // First responses include BOP-A, BOP-B (so user can pick BOP-B).
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

/**
 * Install a pruning mock that drops BOTH BOP-B and FN-Y when any Package is
 * selected.  Used by the multi-field pruning test.
 */
async function installMultiFieldPruningMock(page: Page): Promise<void> {
  await page.route('**/api/production-history/filter-options**', async (route) => {
    const url = new URL(route.request().url());
    const raw = url.searchParams.get('selected') || '';
    const hasPackage = raw && raw.includes('packages');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          pj_types: ['A', 'B'],
          packages: ['PKG-1', 'PKG-2'],
          bops: hasPackage ? ['BOP-A'] : ['BOP-A', 'BOP-B'],
          pj_functions: hasPackage ? ['FN-X'] : ['FN-X', 'FN-Y'],
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
}

/**
 * Install a pruning mock keyed to which Package is selected.
 *
 * PKG-1 or PKG-2 → bops = ['BOP-A']  (drops BOP-B)
 * No Package     → bops = ['BOP-A', 'BOP-B']
 *
 * Used by the consecutive-pruning test so each Package choice triggers a fresh
 * pruning event even though the pruned field (BOP-B) is the same.
 */
async function installConsecutivePruningMock(page: Page): Promise<void> {
  await page.route('**/api/production-history/filter-options**', async (route) => {
    const url = new URL(route.request().url());
    const raw = url.searchParams.get('selected') || '';
    let selected: Record<string, string[]> = {};
    try {
      selected = JSON.parse(decodeURIComponent(raw));
    } catch {
      selected = {};
    }
    const hasPkg = (selected.packages ?? []).length > 0;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          pj_types: ['A', 'B'],
          packages: ['PKG-1', 'PKG-2'],
          bops: hasPkg ? ['BOP-A'] : ['BOP-A', 'BOP-B'],
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
}

/**
 * Open a MultiSelect by test-id and click the option whose label exactly
 * matches `label`, then close the dropdown by clicking outside.
 */
async function pickByTestidLabel(page: Page, testid: string, label: string): Promise<void> {
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

/**
 * Wait for the filter-options response that includes a `packages` key in the
 * `selected` query param (i.e. the cross-filter request fired after picking a
 * Package).
 */
async function waitForPackageFilterResponse(page: Page, timeout = 10_000): Promise<void> {
  await page.waitForResponse(
    (r) =>
      r.url().includes('/api/production-history/filter-options') &&
      decodeURIComponent(new URL(r.url()).searchParams.get('selected') || '').includes(
        'packages',
      ),
    { timeout },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Production History — pruning feedback', () => {
  // -------------------------------------------------------------------------
  // Test 1 (baseline): Pruned notice appears, then auto-clears
  // -------------------------------------------------------------------------
  test('Pruned notice appears, then auto-clears', async ({ page }) => {
    await navigateMocked(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-bop"]',
      extraMocks: async () => {
        await installPruningMock(page);
      },
    });

    // navigateMocked waits until [data-testid="ph-first-tier-bop"] is visible,
    // which means the filter-options response has already completed and populated
    // the MultiSelects.  No extra waitForResponse needed here.

    // Pick BOP-B so it becomes part of the user's selection.
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(400); // allow debounce to settle

    // Pick Package PKG-1 — the mock responds with bops=['BOP-A'] only,
    // so BOP-B is no longer valid → frontend prunes BOP-B and shows the notice.
    const responsePromise = waitForPackageFilterResponse(page);
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    await responsePromise;

    // Pruning notice must appear.
    const notice = page.locator('[data-testid="ph-first-tier-pruned-notice"]');
    await expect(notice).toBeVisible({ timeout: 5_000 });

    // After ~3 s the notice should auto-clear (allow 4 s slack on top).
    await expect(notice).toBeHidden({ timeout: 7_000 });
  });

  // -------------------------------------------------------------------------
  // Test 2: Pruning does not block subsequent query submission
  // -------------------------------------------------------------------------
  test('Pruned notice does not block query submission', async ({ page }) => {
    await navigateMocked(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-bop"]',
      extraMocks: async () => {
        await installPruningMock(page);

        // Also stub the query endpoint so the request completes inside CI.
        await page.route('**/api/production-history/query**', (route) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: {
                dataset_id: 'mock-ds',
                rows: [],
                pagination: { total: 0, page: 1, page_size: 50 },
                matrix: { tree: [], month_columns: [] },
              },
              meta: { timestamp: new Date().toISOString(), app_version: 'test' },
            }),
          }),
        );
      },
    });

    // Select BOP-B, then pick a Package to trigger the prune.
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(400);

    const pruneResponseP = waitForPackageFilterResponse(page);
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    await pruneResponseP;

    // Notice appears — do NOT wait for it to clear; proceed immediately.
    const notice = page.locator('[data-testid="ph-first-tier-pruned-notice"]');
    await expect(notice).toBeVisible({ timeout: 5_000 });

    // Switch to identifier tab and fill a LOT ID.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });
    await page.locator('[data-testid="ph-first-tier-lot-ids"]').fill('GA250101001');

    // Query button must be enabled and the request must fire.
    const queryBtn = page.locator('[data-testid="ph-query-btn"]');
    await expect(queryBtn).toBeEnabled({ timeout: 10_000 });

    const queryReqP = page.waitForRequest('**/api/production-history/query**', {
      timeout: 10_000,
    });
    await queryBtn.click();
    const queryReq = await queryReqP;

    // The query reached the server — pruning notice did not lock the UI.
    expect(queryReq.url()).toContain('/api/production-history/query');
  });

  // -------------------------------------------------------------------------
  // Test 3: Pruning of multiple fields still shows notice exactly once
  // -------------------------------------------------------------------------
  test('Multi-field pruning (BOP + Function) still shows notice once', async ({ page }) => {
    await navigateMocked(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-bop"]',
      extraMocks: async () => {
        await installMultiFieldPruningMock(page);
      },
    });

    // Select BOP-B and FN-Y so both are in the user's selection.
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(300);
    await pickByTestidLabel(page, 'ph-first-tier-function', 'FN-Y');
    await page.waitForTimeout(400);

    // Pick a Package — mock drops BOTH BOP-B and FN-Y simultaneously.
    const pruneResponseP = waitForPackageFilterResponse(page);
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    await pruneResponseP;

    // Exactly one pruned notice must appear (not two separate banners).
    const notices = page.locator('[data-testid="ph-first-tier-pruned-notice"]');
    await expect(notices.first()).toBeVisible({ timeout: 5_000 });
    // Count rendered notice elements — should be exactly 1 in the DOM.
    const count = await notices.count();
    expect(count).toBe(1);

    // Notice auto-clears after its timer.
    await expect(notices.first()).toBeHidden({ timeout: 7_000 });
  });

  // -------------------------------------------------------------------------
  // Test 4: Consecutive pruning events reset the auto-clear timer
  // -------------------------------------------------------------------------
  test('Consecutive pruning events reset the auto-clear timer', async ({ page }) => {
    await navigateMocked(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-bop"]',
      extraMocks: async () => {
        await installConsecutivePruningMock(page);
      },
    });

    // Select BOP-B so it is in the selection.
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(400);

    // First prune: pick PKG-1 → BOP-B dropped → notice appears.
    const firstPruneP = waitForPackageFilterResponse(page);
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    await firstPruneP;

    const notice = page.locator('[data-testid="ph-first-tier-pruned-notice"]');
    await expect(notice).toBeVisible({ timeout: 5_000 });

    // Wait 1.5 s into the ~3 s auto-clear window (notice is still visible).
    await page.waitForTimeout(1_500);
    await expect(notice).toBeVisible();

    // Deselect PKG-1 so BOP-B is available again in options.
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-1');
    // Wait for filter-options response that has no Package selected (BOP-B back).
    await page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await page.waitForTimeout(300);

    // Re-add BOP-B to the selection now that it is available again.
    await pickByTestidLabel(page, 'ph-first-tier-bop', 'BOP-B');
    await page.waitForTimeout(300);

    // Second prune: pick PKG-2 → BOP-B dropped again → timer resets.
    const secondPruneP = waitForPackageFilterResponse(page);
    await pickByTestidLabel(page, 'ph-first-tier-package', 'PKG-2');
    await secondPruneP;

    // Notice must be visible again (re-shown or persisted) within timeout.
    await expect(notice).toBeVisible({ timeout: 5_000 });

    // And it auto-clears again.
    await expect(notice).toBeHidden({ timeout: 7_000 });
  });
});
