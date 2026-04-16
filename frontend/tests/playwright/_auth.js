/**
 * Shared authentication helper for Playwright E2E specs.
 *
 * Credentials are read from environment variables (populated from .env by
 * the test runner).  Fall back to the LOCAL_AUTH values that are always
 * present in the development .env.
 *
 * Usage:
 *   import { loginViaUI, loginViaApi } from './_auth.js';
 */

export const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
export const USERNAME =
  process.env.E2E_USERNAME ||
  process.env.LOCAL_AUTH_USERNAME ||
  '92367';
export const PASSWORD =
  process.env.E2E_PASSWORD ||
  process.env.LOCAL_AUTH_PASSWORD ||
  '1QAZ2wsx3edc';

/**
 * Login through the portal-shell login page form.
 * After a successful login the page will be on the shell home ("/").
 *
 * @param {import('@playwright/test').Page} page
 */
export async function loginViaUI(page) {
  await page.goto('/portal-shell.html');

  // The router guard redirects unauthenticated users to /login.
  // Wait until the login form is visible (it may already be there or we
  // might need to follow the redirect).
  await page.waitForSelector('#username', { timeout: 15_000 });

  await page.fill('#username', USERNAME);
  await page.fill('#password', PASSWORD);
  await page.click('button[type="submit"]');

  // Wait until the URL no longer contains /login (successful redirect to
  // the shell home or the originally requested page).
  await page.waitForURL((url) => !url.pathname.includes('/login'), {
    timeout: 20_000,
  });
}

/**
 * Login via the REST API and store the session cookie.
 * Faster than UI login and preferred for tests that don't need to exercise
 * the login form itself.
 *
 * @param {import('@playwright/test').Page} page
 */
export async function loginViaApi(page) {
  const response = await page.request.post(`${BASE_URL}/api/auth/login`, {
    data: { username: USERNAME, password: PASSWORD },
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok()) {
    // Fall back to UI login if the API path returns an error
    await loginViaUI(page);
    return;
  }

  // Cookies are stored automatically in the browser context; navigate to
  // the shell to initialise the Vue router.
  await page.goto('/portal-shell.html');
  await page.waitForURL((url) => !url.pathname.includes('/login'), {
    timeout: 20_000,
  });
}

/**
 * Navigate to a portal-shell sub-page via sidebar link click.
 *
 * Direct `page.goto('/portal-shell/<route>')` does NOT trigger Vue SPA
 * routing — the shell mounts but the child view stays on the default
 * (wip-overview).  Clicking the sidebar <a> fires the Vue router properly.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} route  The route segment, e.g. "reject-history", "hold-overview"
 * @param {object} [opts]
 * @param {string} [opts.waitForSelector]  Optional selector to wait for after navigation
 * @param {number} [opts.timeout]  Timeout in ms (default 20_000)
 */
export async function navigateViaSidebar(page, route, opts = {}) {
  const { waitForSelector, timeout = 20_000 } = opts;

  // Navigate to portal-shell SPA base (not portal-shell.html which is a
  // different entry point without sidebar navigation).
  await page.goto('/portal-shell/');
  await page.waitForTimeout(2_000);

  await page.waitForSelector(`a[href*="${route}"]`, { timeout });
  await page.click(`a[href*="${route}"]`);

  if (waitForSelector) {
    await page.waitForSelector(waitForSelector, { timeout });
  } else {
    await page.waitForTimeout(3_000);
  }
}
