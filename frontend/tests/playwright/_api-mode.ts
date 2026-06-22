/**
 * Dual-mode API helper for Playwright E2E specs.
 *
 * CI (USE_MOCKS=true):  all requests are intercepted via page.route(); no real
 *                       backend is needed — specs are self-contained.
 * Local (USE_MOCKS=false): requests reach the real dev server; real auth,
 *                          real data.  Assertions must be structural.
 *
 * Usage:
 *   import { USE_MOCKS, conditionalRoute, navigateMocked, navigateDual } from './_api-mode.js';
 *
 * Conventions:
 *   - Error / forced-scenario tests: always use navigateMocked() — they need
 *     specific mock API behaviour and work the same in CI and locally.
 *   - Happy-path / structural tests: use navigateDual() — mock in CI, real backend
 *     locally.  Assertions must not depend on specific data values.
 *
 * LIFO route rule (from playwright docs):
 *   Register catch-all ('**\/*') FIRST, specific patterns LAST.
 */

import { type Page } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, BASE_URL } from './_auth.js';

export { BASE_URL };

// ---------------------------------------------------------------------------
// Mode flag
// ---------------------------------------------------------------------------

/** True when running in CI or when USE_MOCK_API=1 is set locally. */
export const USE_MOCKS: boolean =
  Boolean(process.env.CI) || process.env.USE_MOCK_API === '1';

// ---------------------------------------------------------------------------
// Conditional route helper
// ---------------------------------------------------------------------------

/**
 * Register a route mock only in mock mode (CI / USE_MOCK_API=1).
 * In real mode, requests flow through to the actual backend unchanged.
 */
export async function conditionalRoute(
  page: Page,
  pattern: Parameters<Page['route']>[0],
  handler: Parameters<Page['route']>[1],
): Promise<void> {
  if (USE_MOCKS) {
    await page.route(pattern, handler);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function buildNavWith(route: string) {
  // route may be 'production-history' or '/production-history'; normalise to '/...'
  const normRoute = route.startsWith('/') ? route : `/${route}`;
  return {
    drawers: [
      {
        id: 'reports',
        name: '即時報表',
        order: 1,
        admin_only: false,
        pages: [{ route: normRoute, name: route, status: 'released', order: 1 }],
      },
    ],
    is_admin: false,
    admin_links: { logout: '/api/auth/logout' },
    portal_spa_enabled: false,
    features: { ai_query_enabled: false },
    diagnostics: {
      filtered_drawers: 0,
      filtered_pages: 0,
      invalid_drawers: 0,
      invalid_pages: 0,
      contract_mismatch_routes: [],
    },
  };
}

/** Register the portal-shell infrastructure mocks (auth, nav, WIP stub). */
export async function setupMockedShell(page: Page, targetRoute: string): Promise<void> {
  // Catch-all must be registered FIRST (LIFO — specific routes win)
  await page.route('**/*', (r) => r.continue());

  await page.route('**/api/auth/me**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { name: 'CI Tester', role: 'user', is_admin: false },
      }),
    }),
  );

  await page.route('**/api/auth/login**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { username: 'ci', displayName: 'CI Tester', csrf_token: 'ci-token' },
      }),
    }),
  );

  await page.route('**/api/portal/navigation**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildNavWith(targetRoute)),
    }),
  );

  await page.route('**/api/auth/heartbeat**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    }),
  );

  // Stub WIP APIs so the portal-shell default view clears its loading overlay
  // quickly without an Oracle connection.
  await page.route('**/api/wip/**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    }),
  );
}

/** Click the sidebar link for the given route after the shell is loaded. */
async function clickSidebarLink(page: Page, route: string): Promise<void> {
  const routeKey = route.startsWith('/') ? route.slice(1) : route;

  const toggle = page.locator('button.sidebar-toggle');
  await toggle.waitFor({ timeout: 10_000 });
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
    await toggle.click();
  }

  await page.waitForSelector(`a[href*="${routeKey}"]`, { timeout: 10_000 });
  await page.click(`a[href*="${routeKey}"]`);

  // Some sidebar implementations don't auto-close on route click.
  // Explicitly close it so the overlay doesn't intercept subsequent interactions.
  const isStillExpanded = await toggle.getAttribute('aria-expanded').catch(() => null);
  if (isStillExpanded === 'true') {
    await toggle.click();
  }

  // Wait for sidebar overlay to detach (CSS transition) before further clicks
  await page
    .locator('.sidebar-overlay')
    .waitFor({ state: 'detached', timeout: 3_000 })
    .catch(() => {});
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

export interface NavigateOpts {
  /** CSS selector to wait for after navigation (confirms page mounted). */
  waitForSelector?: string;
  /** Register feature-specific mocks BEFORE navigation starts. */
  extraMocks?: () => Promise<void>;
}

/**
 * Navigate to a portal-shell sub-page with FULL mocking.
 * No real backend is needed.  Use for error scenarios and tests that require
 * specific controlled API responses regardless of mode.
 */
export async function navigateMocked(
  page: Page,
  route: string,
  opts: NavigateOpts = {},
): Promise<void> {
  const { waitForSelector, extraMocks } = opts;

  await setupMockedShell(page, route);
  if (extraMocks) await extraMocks();

  await page.goto(`${BASE_URL}/portal-shell/`, { timeout: 30_000 }).catch(() => {});
  await page.waitForSelector('nav', { timeout: 20_000 });

  await clickSidebarLink(page, route);

  if (waitForSelector) {
    await page.waitForSelector(waitForSelector, { timeout: 20_000 });
  }
}

/**
 * Dual-mode navigation:
 * - Mock mode (CI / USE_MOCK_API=1): full mock via navigateMocked()
 * - Real mode (local dev): loginViaApi() + navigateViaSidebar()
 *
 * Use for happy-path and structural tests whose assertions don't rely on
 * specific data values.  Feature-specific mocks registered via extraMocks()
 * are only active in mock mode (they are ignored in real mode — real backend
 * APIs serve live data).
 */
export async function navigateDual(
  page: Page,
  route: string,
  opts: NavigateOpts = {},
): Promise<void> {
  const { waitForSelector, extraMocks } = opts;

  if (USE_MOCKS) {
    await navigateMocked(page, route, opts);
  } else {
    // Real mode: feature mocks are skipped; real backend serves live data
    await loginViaApi(page);
    await navigateViaSidebar(page, route, { waitForSelector });
  }
}
