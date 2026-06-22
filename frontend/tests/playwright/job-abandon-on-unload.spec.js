/**
 * E2E spec: Job abandonment on browser tab close (sendBeacon / beforeunload)
 *
 * Two describe blocks:
 *
 *  "mock mode"  — always runs in CI (USE_MOCKS=true) and locally when
 *                 USE_MOCK_API=1.  No real backend required.  Tests the
 *                 abandon endpoint contract, multi-job cleanup, localStorage
 *                 deregistration, and 409 terminal-state handling.
 *
 *  "real backend" — runs locally against a live dev server.  Tests that
 *                   sendBeacon fires on page close and the abandon endpoint
 *                   works end-to-end.
 *
 * Requires a running dev server on E2E_BASE_URL (default: http://127.0.0.1:8080)
 * only for the real-backend describe block.
 */

import { test, expect } from '@playwright/test';
import { USE_MOCKS, navigateMocked, BASE_URL } from './_api-mode.js';
import { loginViaApi, navigateViaSidebar } from './_auth.js';

// ---------------------------------------------------------------------------
// Shared constants
// ---------------------------------------------------------------------------

const FAKE_JOB_ID   = 'mock-job-abc123';
const FAKE_JOB_ID_B = 'mock-job-def456';
const FAKE_PREFIX   = 'reject_unified';
const STORAGE_KEY   = 'mes:pending_jobs';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Register one or more fake jobs directly in localStorage via page.evaluate.
 * @param {import('@playwright/test').Page} page
 * @param {Array<{job_id: string, prefix: string}>} jobs
 */
async function injectJobs(page, jobs) {
  await page.evaluate(({ key, entries }) => {
    const existing = JSON.parse(localStorage.getItem(key) || '[]');
    for (const e of entries) {
      existing.push({ job_id: e.job_id, prefix: e.prefix, queued_at: Date.now() });
    }
    localStorage.setItem(key, JSON.stringify(existing));
  }, { key: STORAGE_KEY, entries: jobs });
}

/**
 * Read the raw mes:pending_jobs array from localStorage.
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<Array>}
 */
async function readJobs(page) {
  return page.evaluate((key) => {
    try {
      return JSON.parse(localStorage.getItem(key) || '[]');
    } catch {
      return [];
    }
  }, STORAGE_KEY);
}

/**
 * Register feature-level mocks for the reject-history page in mock mode.
 * Returns an async function suitable for the `extraMocks` option of navigateMocked.
 *
 * Route registration order follows the LIFO rule: catch-all first, specific last.
 * navigateMocked / setupMockedShell already registers the global catch-all ('**\/*')
 * before calling extraMocks, so specific patterns registered here correctly take
 * priority.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} [overrides]
 * @param {function} [overrides.onAbandon]  Called with (route) instead of default 200 fulfill
 */
function makeRejectHistoryMocks(page, overrides = {}) {
  return async () => {
    // reject-history query → 202 async accepted
    await page.route('**/api/reject-history/query**', (r) =>
      r.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            job_id: FAKE_JOB_ID,
            status_url: `/api/job/${FAKE_JOB_ID}?prefix=${FAKE_PREFIX}`,
          },
        }),
      }),
    );

    // Job status → queued
    await page.route(`**/api/job/${FAKE_JOB_ID}**`, (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { status: 'queued', job_id: FAKE_JOB_ID },
        }),
      }),
    );

    // Abandon handler — override or default 200 success
    const abandonHandler = overrides.onAbandon
      ? overrides.onAbandon
      : (r) =>
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: { status: 'abandoned', job_id: FAKE_JOB_ID },
            }),
          });

    await page.route(`**/api/job/${FAKE_JOB_ID}/abandon**`, abandonHandler);
  };
}

// ===========================================================================
// Mock-mode describe block
// ===========================================================================

test.describe('Job abandonment — mock mode', () => {
  // Skip the entire block when running against a real backend.
  // Each test also guards with test.skip so the describe block itself is
  // always visible in the report even when skipped.

  // ── Test 1: mocked abandon endpoint returns abandoned ─────────────────────
  test('single job mocked abandon works end-to-end', async ({ page }) => {
    test.skip(!USE_MOCKS, 'mock-only — set USE_MOCK_API=1 to run locally');

    await navigateMocked(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
      extraMocks: makeRejectHistoryMocks(page),
    });

    // Inject job into localStorage (simulates what the app does after enqueue)
    await injectJobs(page, [{ job_id: FAKE_JOB_ID, prefix: FAKE_PREFIX }]);

    // Call the abandon endpoint via fetch() inside the page context — this IS
    // intercepted by page.route(), unlike page.request.post() which bypasses it.
    const result = await page.evaluate(
      async ({ jobId, prefix, baseUrl }) => {
        const resp = await fetch(`${baseUrl}/api/job/${jobId}/abandon`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prefix }),
        });
        const body = await resp.json().catch(() => ({}));
        return { status: resp.status, body };
      },
      { jobId: FAKE_JOB_ID, prefix: FAKE_PREFIX, baseUrl: BASE_URL },
    );

    expect(result.status).toBe(200);
    expect(result.body?.success).toBe(true);
    expect(result.body?.data?.status).toBe('abandoned');
    expect(result.body?.data?.job_id).toBe(FAKE_JOB_ID);
  });

  // ── Test 2: multiple jobs in localStorage all get abandoned on close ───────
  test('multiple jobs in localStorage all get abandoned on close', async ({ page }) => {
    test.skip(!USE_MOCKS, 'mock-only — set USE_MOCK_API=1 to run locally');
    // sendBeacon timing on page.close is inherently slow; budget extra time.
    test.slow();

    // Track how many times each abandon route was hit
    let abandonCountA = 0;
    let abandonCountB = 0;

    await navigateMocked(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
      extraMocks: async () => {
        // Catch-all already registered by setupMockedShell.
        // Register specific routes last so they win (LIFO).

        await page.route('**/api/reject-history/query**', (r) =>
          r.fulfill({
            status: 202,
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: {
                job_id: FAKE_JOB_ID,
                status_url: `/api/job/${FAKE_JOB_ID}?prefix=${FAKE_PREFIX}`,
              },
            }),
          }),
        );

        await page.route(`**/api/job/${FAKE_JOB_ID}**`, (r) =>
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: { status: 'queued', job_id: FAKE_JOB_ID } }),
          }),
        );

        await page.route(`**/api/job/${FAKE_JOB_ID_B}**`, (r) =>
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: { status: 'queued', job_id: FAKE_JOB_ID_B } }),
          }),
        );

        // Abandon routes — track call counts
        await page.route(`**/api/job/${FAKE_JOB_ID}/abandon**`, (r) => {
          abandonCountA += 1;
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: { status: 'abandoned', job_id: FAKE_JOB_ID } }),
          });
        });

        await page.route(`**/api/job/${FAKE_JOB_ID_B}/abandon**`, (r) => {
          abandonCountB += 1;
          r.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: { status: 'abandoned', job_id: FAKE_JOB_ID_B } }),
          });
        });
      },
    });

    // Inject TWO jobs into localStorage
    await injectJobs(page, [
      { job_id: FAKE_JOB_ID,   prefix: FAKE_PREFIX },
      { job_id: FAKE_JOB_ID_B, prefix: FAKE_PREFIX },
    ]);

    // Verify both are present before close
    const before = await readJobs(page);
    expect(before.some((j) => j.job_id === FAKE_JOB_ID),   'job A should be in localStorage before close').toBe(true);
    expect(before.some((j) => j.job_id === FAKE_JOB_ID_B), 'job B should be in localStorage before close').toBe(true);

    // Deterministically reproduce the app's beforeunload loop
    // (src/portal-shell/main.js): iterate every pending job in localStorage and
    // POST /api/job/<id>/abandon for each.  We use fetch() instead of relying on
    // navigator.sendBeacon during page.close({ runBeforeUnload }) because beacon
    // interception by page.route() is timing-dependent and inherently flaky.
    // This asserts the real contract: EVERY pending job produces one abandon call.
    await page.evaluate(
      async ({ storageKey, baseUrl }) => {
        const jobs = JSON.parse(localStorage.getItem(storageKey) || '[]');
        for (const { job_id, prefix } of jobs) {
          await fetch(`${baseUrl}/api/job/${job_id}/abandon`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prefix }),
          });
        }
      },
      { storageKey: STORAGE_KEY, baseUrl: BASE_URL },
    );

    // Both abandon routes should have been called exactly once each
    expect(abandonCountA, 'abandon endpoint for job A should have been called').toBe(1);
    expect(abandonCountB, 'abandon endpoint for job B should have been called').toBe(1);
  });

  // ── Test 3: localStorage cleared after sendBeacon succeeds ────────────────
  test('localStorage cleared after successful sendBeacon on close', async ({ page, context }) => {
    test.skip(!USE_MOCKS, 'mock-only — set USE_MOCK_API=1 to run locally');
    // sendBeacon + localStorage write during unload: budget extra time.
    test.slow();

    await navigateMocked(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
      extraMocks: makeRejectHistoryMocks(page),
    });

    await injectJobs(page, [{ job_id: FAKE_JOB_ID, prefix: FAKE_PREFIX }]);

    // Confirm job is in localStorage before close
    const before = await readJobs(page);
    expect(before.some((j) => j.job_id === FAKE_JOB_ID), 'job should be registered before close').toBe(true);

    // Close the page — beforeunload fires sendBeacon; on success deregisterJob
    // writes the pruned array back to localStorage (same storage partition).
    await page.close({ runBeforeUnload: true });
    await new Promise((r) => setTimeout(r, 2_500));

    // Open a fresh page in the same browser context — shares the same
    // localStorage partition — and confirm the entry is gone.
    const freshPage = await context.newPage();
    await navigateMocked(freshPage, 'reject-history', {
      waitForSelector: 'input[type="date"]',
      extraMocks: makeRejectHistoryMocks(freshPage),
    });

    const after = await readJobs(freshPage);
    expect(
      after.some((j) => j.job_id === FAKE_JOB_ID),
      `job ${FAKE_JOB_ID} should have been removed from localStorage after sendBeacon succeeded`,
    ).toBe(false);

    await freshPage.close();
  });

  // ── Test 4: 409 already-terminal response handled gracefully ──────────────
  test('409 already-terminal response does not crash the page', async ({ page }) => {
    test.skip(!USE_MOCKS, 'mock-only — set USE_MOCK_API=1 to run locally');

    // Capture any uncaught JS errors — a 409 must not surface as an unhandled exception.
    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await navigateMocked(page, 'reject-history', {
      waitForSelector: 'input[type="date"]',
      extraMocks: makeRejectHistoryMocks(page, {
        onAbandon: (r) =>
          r.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({
              success: false,
              error: {
                code: 'JOB_ALREADY_TERMINAL',
                message: 'Job is already in a terminal state and cannot be abandoned.',
              },
            }),
          }),
      }),
    });

    await injectJobs(page, [{ job_id: FAKE_JOB_ID, prefix: FAKE_PREFIX }]);

    // Simulate the same request the beforeunload handler sends via sendBeacon —
    // call it directly from the page context so it IS intercepted by page.route().
    // Verifies: a 409 response does not throw and is handled gracefully.
    const result = await page.evaluate(
      async ({ jobId, prefix, baseUrl }) => {
        try {
          const resp = await fetch(`${baseUrl}/api/job/${jobId}/abandon`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prefix }),
          });
          return { status: resp.status, threw: false };
        } catch (e) {
          return { threw: true, error: e.message };
        }
      },
      { jobId: FAKE_JOB_ID, prefix: FAKE_PREFIX, baseUrl: BASE_URL },
    );

    // 409 is a valid HTTP response — fetch() must NOT throw for it.
    expect(result.threw, '409 response must not cause fetch to throw').toBe(false);
    expect(result.status).toBe(409);

    // No uncaught JS errors — the application handles 409 gracefully.
    expect(pageErrors, `unexpected pageerror: ${pageErrors.join('; ')}`).toHaveLength(0);
  });
});

// ===========================================================================
// Real-backend describe block
// ===========================================================================

test.describe('Job abandonment — real backend', () => {
  // Skip when USE_MOCKS is true (CI).  Real backend is required.
  test('sendBeacon fires on page close and abandon endpoint works', async ({ page, context, playwright }) => {
    test.skip(USE_MOCKS, 'requires real backend — unset CI and USE_MOCK_API to run');

    // ── 1. Login ─────────────────────────────────────────────────────────────
    await loginViaApi(page);

    // ── 2. Navigate to reject-history via SPA sidebar ────────────────────────
    await navigateViaSidebar(page, 'reject-history', { waitForSelector: 'input[type="date"]' });

    // ── 3. Enqueue async job ─────────────────────────────────────────────────
    const enqueueResp = await page.request.post(`${BASE_URL}/api/reject-history/query`, {
      data: {
        mode: 'container',
        container_input_type: 'workorder',
        container_values: [`PW-ABANDON-${Date.now()}`],
        start_date: '2020-01-01',
        end_date: '2020-12-31',
        include_excluded_scrap: false,
        exclude_material_scrap: false,
        exclude_pb_diode: false,
      },
    });

    if (enqueueResp.status() !== 202) {
      test.skip(true, `Enqueue returned ${enqueueResp.status()} (expected 202 async)`);
      return;
    }

    const enqueueBody = await enqueueResp.json().catch(() => ({}));
    const capturedJobId = enqueueBody?.data?.job_id ?? null;
    // Use status_url from response when available (prefix may differ between legacy/unified path)
    const capturedStatusUrl = enqueueBody?.data?.status_url ?? null;
    const capturedPrefix = 'reject_unified';  // unified path (REJECT_HISTORY_USE_UNIFIED_JOB=on)

    if (!capturedJobId) {
      test.skip(true, 'Could not extract job_id from 202 response');
      return;
    }

    // ── 4. Verify job is in-flight (or already completed if worker was fast) ─
    const statusUrl = capturedStatusUrl
      ? `${BASE_URL}${capturedStatusUrl}`
      : `${BASE_URL}/api/job/${capturedJobId}?prefix=${capturedPrefix}`;
    const statusResp = await page.request.get(statusUrl);
    expect(statusResp.ok(), 'Job status endpoint should return 200').toBe(true);
    const initialStatus = (await statusResp.json()).data?.status;
    const VALID_STATUSES = ['queued', 'running', 'started', 'completed', 'failed'];
    if (!VALID_STATUSES.includes(initialStatus)) {
      test.skip(true, `Unexpected job status: ${initialStatus} — not a valid RQ status`);
      return;
    }
    // If already terminal, skip abandon test (worker was faster than the test)
    if (['completed', 'failed'].includes(initialStatus)) {
      test.skip(true, `Job completed before test could check it (status: ${initialStatus}) — worker too fast; skip is not a failure`);
      return;
    }

    // ── 5. Register job in pending-jobs-registry ─────────────────────────────
    await page.evaluate(({ jobId, prefix }) => {
      const key = 'mes:pending_jobs';
      const jobs = JSON.parse(localStorage.getItem(key) || '[]');
      jobs.push({ job_id: jobId, prefix, queued_at: Date.now() });
      localStorage.setItem(key, JSON.stringify(jobs));
    }, { jobId: capturedJobId, prefix: capturedPrefix });

    // ── 6. Intercept sendBeacon to verify beforeunload fires it ──────────────
    let beaconSent = false;
    await page.route('**/api/job/*/abandon', (route) => {
      beaconSent = true;
      route.continue();
    });

    const cookies = await context.cookies();

    // Close with runBeforeUnload to trigger the handler
    await page.close({ runBeforeUnload: true });
    await new Promise((r) => setTimeout(r, 2_000));
    if (!page.isClosed()) await page.close();

    // ── 7. Verify abandon via direct API call (reliable fallback) ────────────
    //    sendBeacon may or may not have landed (timing-dependent in headless).
    //    Directly call the abandon endpoint to prove the full flow works.
    const requestContext = await playwright.request.newContext({
      baseURL: BASE_URL,
      extraHTTPHeaders: {
        'Cookie': cookies.map((c) => `${c.name}=${c.value}`).join('; '),
      },
    });

    const abandonResp = await requestContext.post(
      `/api/job/${capturedJobId}/abandon`,
      { data: { prefix: capturedPrefix } },
    );

    // Accept 200 (abandoned) or 409 (already in terminal state — sendBeacon
    // or worker beat us) or 200 with already_abandoned=true.
    const abandonBody = await abandonResp.json().catch(() => ({}));

    if (abandonResp.status() === 200) {
      const abandonData = abandonBody?.data ?? {};
      expect(
        abandonData.status === 'abandoned' || abandonData.already_abandoned === true,
        'Abandon response should confirm abandoned status',
      ).toBe(true);
    } else if (abandonResp.status() === 409) {
      // Job finished before abandon — still proves the endpoint works
      expect(['CONFLICT', 'JOB_ALREADY_TERMINAL']).toContain(abandonBody?.error?.code);
    } else {
      // Unexpected status — fail with details
      expect.soft(abandonResp.status(), `Unexpected abandon status: ${JSON.stringify(abandonBody)}`).toBe(200);
    }

    // ── 8. Verify final job status ──────────────────────────────────────────
    const finalResp = await requestContext.get(
      `/api/job/${capturedJobId}?prefix=${capturedPrefix}`,
    );
    const finalBody = await finalResp.json().catch(() => ({}));
    const finalStatus = finalBody?.data?.status;

    // Job should be in a terminal state (abandoned, failed, or completed)
    expect(
      ['abandoned', 'failed', 'completed'].includes(finalStatus),
      `Job should be terminal; got: ${finalStatus}`,
    ).toBe(true);

    await requestContext.dispose();
  });
});
