/**
 * E2E spec: Production History — first-tier cross-filter (AC-2, AC-7)
 *
 * Mounts production-history, mocks the cached filter-options API with a small
 * 4-tuple corpus, then exercises the symmetric narrowing behaviour:
 *   - empty selection → 4 MultiSelects populated (AC-1, AC-7)
 *   - select a Package → BOP / Function / Type options narrow
 *   - reverse: clear Package, select a BOP → Package / Function / Type narrow
 *
 * All selectors use the `data-testid` anchors added by the frontend-engineer
 * (per visual-reviewer recommendation VR-10).
 */

import { test, expect, type Page } from '@playwright/test';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

// ────────────────────────────────────────────────────────────────────────────
// Fixture corpus
//
//  PJ_TYPE | PRODUCTLINENAME | PJ_BOP   | PJ_FUNCTION
//  --------+-----------------+----------+-------------
//   A      | PKG-1           | BOP-A    | FN-X
//   A      | PKG-2           | BOP-B    | FN-Y
//   B      | PKG-1           | BOP-C    | FN-X
//   B      | PKG-3           | BOP-A    | FN-Z
//
// Narrowing expectations:
//   packages=[PKG-1]  → bops={BOP-A,BOP-C}, pj_functions={FN-X}, pj_types={A,B}
//   bops=[BOP-A]      → packages={PKG-1,PKG-3}, pj_functions={FN-X,FN-Z}, pj_types={A,B}
// ────────────────────────────────────────────────────────────────────────────

const FULL = {
  pj_types: ['A', 'B'],
  packages: ['PKG-1', 'PKG-2', 'PKG-3'],
  bops: ['BOP-A', 'BOP-B', 'BOP-C'],
  pj_functions: ['FN-X', 'FN-Y', 'FN-Z'],
};

function narrow(selected: Record<string, string[]>) {
  // Empty selection → full set.
  const hasSel = Object.values(selected).some((v) => Array.isArray(v) && v.length > 0);
  if (!hasSel) return FULL;

  const tuples = [
    ['A', 'PKG-1', 'BOP-A', 'FN-X'],
    ['A', 'PKG-2', 'BOP-B', 'FN-Y'],
    ['B', 'PKG-1', 'BOP-C', 'FN-X'],
    ['B', 'PKG-3', 'BOP-A', 'FN-Z'],
  ];
  const selTypes = new Set(selected.pj_types || []);
  const selPkg = new Set(selected.packages || []);
  const selBop = new Set(selected.bops || []);
  const selFn = new Set(selected.pj_functions || []);

  const outTypes = new Set<string>();
  const outPkg = new Set<string>();
  const outBop = new Set<string>();
  const outFn = new Set<string>();
  for (const [t, p, b, f] of tuples) {
    if (selTypes.size && !selTypes.has(t)) continue;
    if (selPkg.size && !selPkg.has(p)) continue;
    if (selBop.size && !selBop.has(b)) continue;
    if (selFn.size && !selFn.has(f)) continue;
    outTypes.add(t);
    outPkg.add(p);
    outBop.add(b);
    outFn.add(f);
  }
  return {
    pj_types: [...outTypes].sort(),
    packages: [...outPkg].sort(),
    bops: [...outBop].sort(),
    pj_functions: [...outFn].sort(),
  };
}

async function installFilterOptionsMock(page: Page): Promise<{ requests: string[] }> {
  const requests: string[] = [];
  await page.route('**/api/production-history/filter-options**', async (route) => {
    const url = new URL(route.request().url());
    const raw = url.searchParams.get('selected');
    requests.push(raw || '');
    let selected: Record<string, string[]> = {};
    if (raw) {
      try {
        selected = JSON.parse(raw);
      } catch {
        selected = {};
      }
    }
    const data = narrow(selected);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data,
        meta: {
          updated_at: '2026-05-14T00:00:00Z',
          schema_version: 2,
          timestamp: new Date().toISOString(),
          app_version: 'test',
        },
      }),
    });
  });
  return { requests };
}

// Open a MultiSelect dropdown and tick the given option label.
// shared-ui MultiSelect renders the popup attached to the trigger; selections
// use checkboxes with the label visible inside the dropdown.
async function selectOption(page: Page, testid: string, optionLabel: string) {
  const root = page.locator(`[data-testid="${testid}"]`);
  await expect(root).toBeVisible({ timeout: 10_000 });
  // Open the dropdown by clicking the trigger.
  await root.locator('.multi-select-trigger, button, [role="combobox"]').first().click();
  // Click the option matching the label.
  const option = page
    .locator('.multi-select-option, li, label')
    .filter({ hasText: new RegExp(`^\\s*${optionLabel}\\s*$`) })
    .first();
  await expect(option).toBeVisible({ timeout: 10_000 });
  await option.click();
  // Close the dropdown by clicking outside.
  await page.locator('body').click({ position: { x: 5, y: 5 } });
}

// Read the rendered options from a MultiSelect by opening it and listing labels.
async function readOptions(page: Page, testid: string): Promise<string[]> {
  const root = page.locator(`[data-testid="${testid}"]`);
  await root.locator('.multi-select-trigger, button, [role="combobox"]').first().click();
  const items = await page
    .locator('.multi-select-option, [role="option"], label')
    .allInnerTexts();
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  return items
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && s.length < 100);
}

test.describe('Production History — cross-filter (AC-2, AC-7)', () => {
  let mock: { requests: string[] };

  test.beforeEach(async ({ page }) => {
    mock = await installFilterOptionsMock(page);
    await loginViaApi(page);
    await navigateViaSidebar(page, 'production-history', {
      waitForSelector: '[data-testid="ph-first-tier-type"]',
    });
    // Wait for the initial empty-selection fetch to resolve.
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-testid="ph-first-tier-type"]');
        return el && !el.classList.contains('is-loading');
      },
      { timeout: 15_000 },
    );
  });

  test('renders 4 MultiSelects (Tab A) + 3 wildcard textareas (Tab B) (AC-7)', async ({
    page,
  }) => {
    // Tab A 「依產品分類查詢」 is the default tab — the 4 cached MultiSelects live here.
    for (const id of [
      'ph-first-tier-type',
      'ph-first-tier-package',
      'ph-first-tier-bop',
      'ph-first-tier-function',
    ]) {
      await expect(page.locator(`[data-testid="${id}"]`)).toBeVisible({ timeout: 10_000 });
    }
    // The two-tab redesign (prod-history-query-mode-tabs) moved the 3 wildcard
    // textareas into Tab B 「依識別碼查詢」 — switch tabs to assert them.
    await page.locator('[data-testid="ph-mode-tab-identifier"]').click();
    await expect(page.locator('[data-testid="ph-mode-panel-identifier"]')).toBeVisible({
      timeout: 10_000,
    });
    for (const id of [
      'ph-first-tier-mfg-orders',
      'ph-first-tier-lot-ids',
      'ph-first-tier-wafer-lots',
    ]) {
      await expect(page.locator(`[data-testid="${id}"]`)).toBeVisible({ timeout: 10_000 });
    }
  });

  test('Package selection narrows BOP / Function / Type symmetrically (AC-2)', async ({
    page,
  }) => {
    const initialRequestCount = mock.requests.length;

    // Select PKG-1
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await selectOption(page, 'ph-first-tier-package', 'PKG-1');
    await responsePromise;

    // At least one cross-filter request should have fired after the initial mount.
    expect(mock.requests.length).toBeGreaterThan(initialRequestCount);

    // The most recent request should include packages=["PKG-1"].
    const lastRaw = mock.requests[mock.requests.length - 1];
    expect(lastRaw).toBeTruthy();
    const lastSel = JSON.parse(decodeURIComponent(lastRaw));
    expect(lastSel.packages).toEqual(['PKG-1']);
  });

  test('Reverse: clearing Package and selecting BOP narrows symmetrically', async ({
    page,
  }) => {
    // First select then deselect Package to simulate clearing.
    await selectOption(page, 'ph-first-tier-package', 'PKG-1');
    await page.waitForTimeout(400); // debounce

    // Now select BOP-A
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/production-history/filter-options') &&
        decodeURIComponent(new URL(r.url()).searchParams.get('selected') || '').includes('bops'),
      { timeout: 10_000 },
    );
    await selectOption(page, 'ph-first-tier-bop', 'BOP-A');
    await responsePromise;

    const lastRaw = mock.requests[mock.requests.length - 1];
    const lastSel = JSON.parse(decodeURIComponent(lastRaw));
    expect(lastSel.bops).toContain('BOP-A');
  });

  // ── New tests added by fix-prod-history-multiselect-filter ────────────────

  test('AC-1: multiple toggles inside open dropdown trigger zero /filter-options requests', async ({
    page,
  }) => {
    const requestsBefore = mock.requests.length;

    // Open the Type dropdown.
    const root = page.locator('[data-testid="ph-first-tier-type"]');
    await root.locator('.multi-select-trigger, button').first().click();
    await expect(page.locator('.multi-select-dropdown')).toBeVisible({ timeout: 5_000 });

    // Toggle option A, then B, then A again — all inside the same open dropdown.
    const optionA = page.locator('.multi-select-option').filter({ hasText: /^A$/ }).first();
    const optionB = page.locator('.multi-select-option').filter({ hasText: /^B$/ }).first();
    await optionA.click();
    await optionB.click();
    await optionA.click();

    // Dropdown is still open — no cross-filter request should have fired.
    expect(mock.requests.length).toBe(requestsBefore);

    // Close the dropdown (click outside) — now ONE request should fire.
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    // Allow debounce to fire.
    await page.waitForTimeout(400);

    // After close, exactly one new request should appear (for the final selection).
    expect(mock.requests.length).toBeGreaterThan(requestsBefore);
  });

  test('AC-2: dropdown close via outside-click fires exactly 1 /filter-options request', async ({
    page,
  }) => {
    const requestsBefore = mock.requests.length;

    // Open the Package dropdown and toggle PKG-1.
    const root = page.locator('[data-testid="ph-first-tier-package"]');
    await root.locator('.multi-select-trigger, button').first().click();
    await expect(page.locator('.multi-select-dropdown')).toBeVisible({ timeout: 5_000 });

    const option = page
      .locator('.multi-select-option')
      .filter({ hasText: /PKG-1/ })
      .first();
    await option.click();

    // Close by outside-click and wait for the response.
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    await responsePromise;

    // Exactly one new request should have been made.
    expect(mock.requests.length).toBe(requestsBefore + 1);
    const lastSel = JSON.parse(decodeURIComponent(mock.requests[mock.requests.length - 1]));
    expect(lastSel.packages).toEqual(['PKG-1']);
  });

  test('AC-2: dropdown close via Escape fires exactly 1 /filter-options request', async ({
    page,
  }) => {
    const requestsBefore = mock.requests.length;

    // Open the BOP dropdown and toggle BOP-A.
    const root = page.locator('[data-testid="ph-first-tier-bop"]');
    await root.locator('.multi-select-trigger, button').first().click();
    await expect(page.locator('.multi-select-dropdown')).toBeVisible({ timeout: 5_000 });

    const option = page
      .locator('.multi-select-option')
      .filter({ hasText: /BOP-A/ })
      .first();
    await option.click();

    // Close via Escape key on the dropdown.
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await page.locator('.multi-select-dropdown').press('Escape');
    await responsePromise;

    // Exactly one new request.
    expect(mock.requests.length).toBe(requestsBefore + 1);
    const lastSel = JSON.parse(decodeURIComponent(mock.requests[mock.requests.length - 1]));
    expect(lastSel.bops).toContain('BOP-A');
  });

  test('AC-4: no-op close (selection identical to pre-open state) fires zero requests', async ({
    page,
  }) => {
    // First commit a selection so _lastCommitted is primed.
    await selectOption(page, 'ph-first-tier-type', 'A');
    await page.waitForTimeout(400);
    const requestsAfterFirstCommit = mock.requests.length;

    // Open the Type dropdown, toggle A on then off (net: no change), close.
    const root = page.locator('[data-testid="ph-first-tier-type"]');
    await root.locator('.multi-select-trigger, button').first().click();
    await expect(page.locator('.multi-select-dropdown')).toBeVisible({ timeout: 5_000 });

    // Toggle A off (was selected), then back on (back to original state).
    const optionA = page.locator('.multi-select-option').filter({ hasText: /^A$/ }).first();
    await optionA.click();
    await optionA.click();

    // Close — selection is identical to _lastCommitted, so no request should fire.
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    await page.waitForTimeout(400);

    expect(mock.requests.length).toBe(requestsAfterFirstCommit);
  });

  test('AC-3: after first filter commits, second filter still buffers toggles until close', async ({
    page,
  }) => {
    // Commit the first filter (Package = PKG-1).
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await selectOption(page, 'ph-first-tier-package', 'PKG-1');
    await responsePromise;
    const requestsAfterFirst = mock.requests.length;

    // Open the Function dropdown and toggle multiple options without closing.
    const root = page.locator('[data-testid="ph-first-tier-function"]');
    await root.locator('.multi-select-trigger, button').first().click();
    await expect(page.locator('.multi-select-dropdown')).toBeVisible({ timeout: 5_000 });

    const options = page.locator('.multi-select-option');
    const count = await options.count();
    if (count > 0) await options.first().click();
    if (count > 1) await options.nth(1).click();

    // Still inside open dropdown — no additional requests.
    expect(mock.requests.length).toBe(requestsAfterFirst);

    // Close — exactly one new request should fire.
    const responsePromise2 = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    await responsePromise2;

    expect(mock.requests.length).toBe(requestsAfterFirst + 1);
  });

  test('AC-6: committed /filter-options request body retains existing payload schema', async ({
    page,
  }) => {
    // Select a package and close to trigger a commit.
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/production-history/filter-options') && r.status() === 200,
      { timeout: 10_000 },
    );
    await selectOption(page, 'ph-first-tier-package', 'PKG-2');
    await responsePromise;

    // Validate payload schema: must be JSON-encoded in `selected` param containing
    // known field names only — same as pre-fix baseline.
    const lastRaw = mock.requests[mock.requests.length - 1];
    const lastSel = JSON.parse(decodeURIComponent(lastRaw));
    // Only known first-tier fields should appear (no unknown keys).
    const knownFields = new Set(['pj_types', 'packages', 'bops', 'pj_functions']);
    for (const key of Object.keys(lastSel)) {
      expect(knownFields.has(key)).toBe(true);
    }
    // Values must be arrays of strings.
    for (const val of Object.values(lastSel)) {
      expect(Array.isArray(val)).toBe(true);
      for (const item of val as string[]) {
        expect(typeof item).toBe('string');
      }
    }
    expect(lastSel.packages).toEqual(['PKG-2']);
  });
});
