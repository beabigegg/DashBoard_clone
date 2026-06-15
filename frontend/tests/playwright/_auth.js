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
  await page.goto('/portal-shell/');

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
  await page.goto('/portal-shell/');
  await page.waitForURL((url) => !url.pathname.includes('/login'), {
    timeout: 20_000,
  });
}

/**
 * Inject a mock API error for a URL pattern.
 *
 * The default body conforms to the MES Dashboard error envelope defined in
 * `src/mes_dashboard/core/response.py` (success=false, error.code, error.message).
 *
 * @param {import('@playwright/test').Page} page
 * @param {string|RegExp} urlPattern  Passed to page.route()
 * @param {number} status  HTTP status code (e.g. 500, 503)
 * @param {object} [options]
 * @param {object} [options.body]    Override response body (must match envelope schema)
 * @param {number} [options.delay]   Milliseconds to delay before fulfilling
 * @param {object} [options.headers] Extra response headers (e.g. { 'Retry-After': '30' })
 * @returns {Promise<void>} Resolves once the route handler is registered
 */
export async function mockApiError(page, urlPattern, status, options = {}) {
  const { body, delay, headers = {} } = options;

  const codeMap = {
    400: 'VALIDATION_ERROR',
    401: 'UNAUTHORIZED',
    403: 'FORBIDDEN',
    404: 'NOT_FOUND',
    429: 'TOO_MANY_REQUESTS',
    500: 'INTERNAL_ERROR',
    503: 'SERVICE_UNAVAILABLE',
    504: 'DB_QUERY_TIMEOUT',
  };
  const defaultBody = {
    success: false,
    error: {
      code: codeMap[status] || 'INTERNAL_ERROR',
      message: `Mock error (status ${status})`,
    },
    meta: { timestamp: new Date().toISOString(), app_version: 'test' },
  };

  await page.route(urlPattern, async (route) => {
    if (delay) {
      await new Promise((r) => setTimeout(r, delay));
    }
    await route.fulfill({
      status,
      contentType: 'application/json',
      headers,
      body: JSON.stringify(body ?? defaultBody),
    });
  });
}

/**
 * Wait until the UI reaches an idle state:
 *   - no `.loading-overlay` visible
 *   - no button with `aria-busy="true"` or class `is-loading`
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} [timeout=20_000]
 */
export async function waitForIdleUi(page, timeout = 20_000) {
  await page.waitForFunction(
    () => {
      const overlay = document.querySelector(
        '.loading-overlay:not([style*="display: none"]):not([style*="display:none"])'
      );
      if (overlay) return false;
      const busyBtn = document.querySelector(
        'button[aria-busy="true"], button.is-loading'
      );
      return !busyBtn;
    },
    { timeout },
  );
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

  // Intercept the heavy WIP filter-options payload (400KB) that keeps the
  // loading-overlay alive long enough to block sidebar clicks.  We return a
  // minimal success response so the overlay clears immediately, then
  // un-route after the sidebar click so the target page hits the real API.
  const WIP_ROUTE = '**/api/wip/**';
  await page.route(WIP_ROUTE, (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, meta: {} }),
    })
  );

  await page.goto('/portal-shell/');
  await waitForIdleUi(page);

  await page.waitForSelector(`a[href*="${route}"]`, { timeout });
  await page.click(`a[href*="${route}"]`);

  // Un-route so the destination page can make real API calls.
  await page.unroute(WIP_ROUTE);

  if (waitForSelector) {
    await page.waitForSelector(waitForSelector, { timeout });
  } else {
    await page.waitForTimeout(3_000);
  }
}
