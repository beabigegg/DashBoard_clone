/**
 * E2E tests: portal-shell login page & auth guard
 *
 * Scenarios covered:
 *   page renders     — /portal-shell/login shows form, username, password, submit
 *   auth guard       — unauthenticated access to protected route → redirect to /login
 *   validation       — empty submit shows "請輸入帳號和密碼"
 *   bad credentials  — /api/auth/login 失敗 → .login-error visible
 *   successful login — /api/auth/login 成功 → redirect away from /login
 *
 * Network strategy:
 *   All API calls mocked. The router's beforeEach guard calls /api/auth/me;
 *   mocking it to 401 triggers the auth-guard redirect to /login.
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const LOGIN_URL = `${BASE_URL}/portal-shell/login`;
const SHELL_URL = `${BASE_URL}/portal-shell`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function gotoLoginPageDirectly(page: Page): Promise<void> {
  // /login path is always accessible (bypasses auth guard)
  await page.route('**/*', (route) => route.continue());
  await page.goto(LOGIN_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  await expect(page.locator('#username')).toBeVisible({ timeout: 15_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('test_login_page_renders_form', async ({ page }) => {
  await gotoLoginPageDirectly(page);

  await expect(page.locator('#username')).toBeVisible();
  await expect(page.locator('#password')).toBeVisible();
  await expect(page.locator('button.login-btn')).toBeVisible();

  // Branding text
  const cardText = await page.locator('.login-card').textContent();
  expect(cardText).toContain('MES 報表系統');
  expect(cardText).toContain('帳號（工號）');
  expect(cardText).toContain('密碼');
});

test('test_auth_guard_redirects_unauthenticated_to_login', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  // 401 from /api/auth/me → guard sets isAuthenticated=false → redirect /login
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json',
      body: JSON.stringify({ success: false }) }),
  );

  await page.goto(SHELL_URL, { timeout: 30_000 }).catch(() => {});
  // URL should contain /login (with ?next=... query)
  await page.waitForURL((url) => url.pathname.includes('/login'), { timeout: 15_000 });
  expect(page.url()).toContain('/login');
});

test('test_empty_submit_shows_validation_error', async ({ page }) => {
  await gotoLoginPageDirectly(page);

  // Click submit without filling fields
  await page.locator('button.login-btn').click();

  const errorEl = page.locator('.login-error');
  await expect(errorEl).toBeVisible({ timeout: 5_000 });
  expect(await errorEl.textContent()).toContain('請輸入帳號和密碼');
});

test('test_bad_credentials_shows_error', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/login**', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ success: false, error: { message: '帳號或密碼錯誤' } }),
    }),
  );

  await page.goto(LOGIN_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  await expect(page.locator('#username')).toBeVisible({ timeout: 15_000 });

  await page.locator('#username').fill('wrong_user');
  await page.locator('#password').fill('wrong_pass');
  await page.locator('button.login-btn').click();

  const errorEl = page.locator('.login-error');
  await expect(errorEl).toBeVisible({ timeout: 10_000 });
  expect(await errorEl.textContent()).toContain('帳號或密碼錯誤');
});

test('test_successful_login_redirects_away_from_login', async ({ page }) => {
  await page.route('**/*', (route) => route.continue());

  // Mock successful login
  await page.route('**/api/auth/login**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { username: 'testuser', displayName: 'Test User', csrf_token: 'token-123' },
      }),
    }),
  );

  // Mock /api/auth/me (called on subsequent nav guard checks)
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { username: 'testuser', role: 'user', is_admin: false } }),
    }),
  );

  // Mock portal navigation so the shell doesn't hang after redirect
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        drawers: [],
        is_admin: false,
        admin_links: {},
        portal_spa_enabled: false,
        features: { ai_query_enabled: false },
        diagnostics: { filtered_drawers: 0, filtered_pages: 0, invalid_drawers: 0, invalid_pages: 0, contract_mismatch_routes: [] },
      }),
    }),
  );

  await page.goto(LOGIN_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {});
  await expect(page.locator('#username')).toBeVisible({ timeout: 15_000 });

  await page.locator('#username').fill('testuser');
  await page.locator('#password').fill('testpass');
  await page.locator('button.login-btn').click();

  // After successful login, router.push('/') is called — URL should leave /login
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 15_000 });
  expect(page.url()).not.toContain('/login');
});
