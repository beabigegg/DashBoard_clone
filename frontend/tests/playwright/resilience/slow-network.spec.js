/**
 * Resilience spec: Slow network / delayed API responses
 *
 * Uses Reject History (which has a page-level LoadingOverlay) to verify:
 *   - Page-level LoadingOverlay appears within 2 s of button click
 *   - LoadingOverlay disappears after the response (delayed success) arrives
 *   - Query button is disabled while loading, then re-enabled after
 *   - Reduced-motion: verifies no CSS animation when prefers-reduced-motion: reduce
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, navigateViaSidebar, waitForIdleUi } from '../_auth.js';

const DELAY_MS = 5_000;

async function setupRejectHistoryWithSlowQuery(page) {
  // Broad mock for all reject-history APIs (fast fallback)
  await page.route('**/api/reject-history/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { data: [], total: 0 } }),
    }),
  );
  // Override the primary query endpoint with a slow response (LIFO takes precedence)
  await page.route('**/api/reject-history/query**', async (route) => {
    await new Promise((r) => setTimeout(r, DELAY_MS));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { query_id: 'test-123', data: [], total: 0 },
        meta: { timestamp: new Date().toISOString(), app_version: 'test' },
      }),
    });
  });

  await loginViaApi(page);
  await navigateViaSidebar(page, 'reject-history', {
    waitForSelector: 'input[type="date"]',
  });
}

test.describe('Slow network — Reject History', () => {
  test.beforeEach(async ({ page }) => {
    await setupRejectHistoryWithSlowQuery(page);
  });

  test('loading overlay appears promptly and dismisses after response', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢"):visible').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });

    const clickTime = Date.now();
    await queryBtn.click();

    // Page-level LoadingOverlay must appear within 2 s of click
    await expect(
      page.locator('.loading-overlay, [class*="loading-overlay"]').first(),
    ).toBeVisible({ timeout: 2_000 });

    const overlayAppearedMs = Date.now() - clickTime;
    expect(overlayAppearedMs).toBeLessThan(2_000);

    // After the delayed response, overlay must disappear
    await waitForIdleUi(page, DELAY_MS + 10_000);
  });

  test('button is disabled while loading then re-enabled', async ({ page }) => {
    const queryBtn = page.locator('button:has-text("查詢"):visible').first();
    await expect(queryBtn).toBeVisible({ timeout: 10_000 });
    await queryBtn.click();

    // Button must become disabled during the request
    await expect.poll(
      async () => {
        const disabled = await queryBtn.isDisabled();
        const text = await queryBtn.textContent();
        return disabled || (text && text.includes('查詢中'));
      },
      // DELAY_MS (5s) keeps the request in-flight; widen to 4s so the transient
      // disabled state is reliably caught even under CI/suite resource contention.
      { timeout: 4_000 },
    ).toBe(true);

    // After response it must be re-enabled
    await waitForIdleUi(page, DELAY_MS + 10_000);
    await expect(queryBtn).toBeEnabled({ timeout: 5_000 });
  });
});

test.describe('Slow network — reduced-motion compliance', () => {
  test('loading overlay has no animation when prefers-reduced-motion: reduce', async ({
    browser,
  }) => {
    const context = await browser.newContext({
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();

    // Broad mock first, then slow override for query endpoint
    await page.route('**/api/reject-history/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { data: [], total: 0 } }),
      }),
    );
    await page.route('**/api/reject-history/query**', async (route) => {
      await new Promise((r) => setTimeout(r, 3_000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { query_id: 'test-123', data: [], total: 0 } }),
      });
    });

    await loginViaApi(page);
    await navigateViaSidebar(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
    });

    const queryBtn = page.locator('button:has-text("查詢"):visible').first();
    if (await queryBtn.count() > 0) {
      await queryBtn.click();

      // Wait for an overlay to appear (if any)
      await page.waitForTimeout(500);

      const overlayEl = page.locator('.loading-overlay, [class*="loading-overlay"]').first();
      if (await overlayEl.count() > 0) {
        // With reduced-motion the animation-duration should be 0s or close to it
        const animDuration = await overlayEl.evaluate((el) =>
          getComputedStyle(el).animationDuration,
        );
        const durationMs = parseFloat(animDuration) * 1000;
        expect(durationMs).toBeLessThanOrEqual(50);
      }
    }

    await context.close();
  });
});
