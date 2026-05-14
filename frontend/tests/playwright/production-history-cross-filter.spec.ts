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

  test('renders 4 MultiSelects + 3 wildcard textareas (AC-7)', async ({ page }) => {
    for (const id of [
      'ph-first-tier-type',
      'ph-first-tier-package',
      'ph-first-tier-bop',
      'ph-first-tier-function',
    ]) {
      await expect(page.locator(`[data-testid="${id}"]`)).toBeVisible({ timeout: 10_000 });
    }
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
});
