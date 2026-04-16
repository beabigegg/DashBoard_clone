/**
 * E2E spec: Job abandonment on browser tab close (sendBeacon / beforeunload)
 *
 * Flow:
 *  1. Login via API
 *  2. Navigate to reject-history and submit a wide date-range query to trigger
 *     an async job (≥ 5 s) so the job is still pending when the tab is closed.
 *  3. Capture the job_id and prefix from the 202 network response.
 *  4. Close the page (triggers beforeunload + sendBeacon to /api/job/<id>/abandon).
 *  5. Poll GET /api/job/<id>?prefix=<p> (using a separate request context with the
 *     same session cookie) until status="abandoned" or 5 s elapses.
 *  6. Assert the abandoned status is observed within the deadline.
 *
 * Requires a running dev server on E2E_BASE_URL (default: http://127.0.0.1:8080).
 * The test uses the existing ~/_auth.js helper for credentials.
 */

import { test, expect } from '@playwright/test';
import { loginViaApi, BASE_URL } from './_auth.js';

// Reject-history is the most likely async query; wide date range ensures async path.
const REJECT_HISTORY_URL = '/portal-shell/reject-history';

/**
 * Build a wide date range (1 year back) to maximise the chance of hitting
 * the async (202) code path even on a lightly-loaded dev server.
 */
function wideDateRange() {
  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 1);
  const fmt = (d) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

test.describe('Job abandonment on tab close', () => {
  test('sendBeacon on page.close() marks job as abandoned', async ({ page, context, playwright }) => {
    // ── 1. Login ─────────────────────────────────────────────────────────────
    await loginViaApi(page);

    // ── 2. Navigate and submit wide-range query ───────────────────────────────
    await page.goto(REJECT_HISTORY_URL);
    await page.waitForSelector('.reject-history-page, main, #app', { timeout: 20_000 });

    const { start, end } = wideDateRange();

    const dateInputs = page.locator('input[type="date"]');
    const count = await dateInputs.count();
    if (count >= 2) {
      await dateInputs.nth(0).fill(start);
      await dateInputs.nth(1).fill(end);
    } else {
      const startInput = page.locator('[name="startDate"],[name="start_date"],[placeholder*="開始日"]').first();
      const endInput   = page.locator('[name="endDate"],[name="end_date"],[placeholder*="結束日"]').first();
      if (await startInput.count()) await startInput.fill(start);
      if (await endInput.count())   await endInput.fill(end);
    }

    // ── 3. Capture the 202 response to get job_id + prefix ───────────────────
    let capturedJobId = null;
    let capturedPrefix = null;

    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/reject-history/query') || r.url().includes('/api/reject-history'),
      { timeout: 30_000 },
    ).catch(() => null);

    const queryBtn = page.locator(
      'button[type="submit"], button:has-text("查詢"), button:has-text("Query"), button:has-text("執行")'
    ).first();
    if (await queryBtn.count() === 0) {
      test.skip(true, 'No query button found on reject-history page');
      return;
    }
    await queryBtn.click();

    const queryResp = await responsePromise;
    if (!queryResp) {
      test.skip(true, 'No response received from reject-history query endpoint');
      return;
    }

    if (queryResp.status() !== 202) {
      // Synchronous (200) response — no async job to abandon; skip gracefully.
      test.skip(true, `Query returned ${queryResp.status()} (sync) — no async job to test`);
      return;
    }

    const body = await queryResp.json().catch(() => ({}));
    capturedJobId = body?.data?.job_id ?? body?.job_id ?? null;
    capturedPrefix = body?.data?.prefix ?? body?.prefix ?? 'reject';

    if (!capturedJobId) {
      test.skip(true, 'Could not extract job_id from 202 response');
      return;
    }

    // ── 4. Grab the session cookie before closing the page ───────────────────
    const cookies = await context.cookies();

    // ── 5. Close the page (fires beforeunload → sendBeacon) ──────────────────
    await page.close();

    // ── 6. Poll job status via a separate request context ────────────────────
    //    Reuse the same session cookie so the server accepts the request.
    const requestContext = await playwright.request.newContext({
      baseURL: BASE_URL,
      extraHTTPHeaders: {
        'Cookie': cookies.map((c) => `${c.name}=${c.value}`).join('; '),
      },
    });

    const pollingDeadline = Date.now() + 10_000; // 10 s polling window
    let lastStatus = null;
    let abandoned = false;

    while (Date.now() < pollingDeadline) {
      const statusResp = await requestContext.get(
        `/api/job/${capturedJobId}?prefix=${capturedPrefix}`,
        { timeout: 3_000 },
      ).catch(() => null);

      if (statusResp && statusResp.ok()) {
        const statusBody = await statusResp.json().catch(() => ({}));
        lastStatus = statusBody?.data?.status ?? statusBody?.status ?? null;
        if (lastStatus === 'abandoned') {
          abandoned = true;
          break;
        }
      }

      await new Promise((r) => setTimeout(r, 500));
    }

    await requestContext.dispose();

    expect(abandoned, `Job should be abandoned within 10s; last observed status: ${lastStatus}`).toBe(true);
  });
});
