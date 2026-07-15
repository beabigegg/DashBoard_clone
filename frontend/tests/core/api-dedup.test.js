/**
 * Tests for per-endpoint in-flight dedup in core/api.js
 *
 * Tests the deduplication Map behaviour: concurrent calls with the same key
 * share one in-flight promise; calls with different keys do not.
 *
 * Does NOT test the full fetch path (that requires a browser or jsdom).
 * Instead tests the dedup key builder and the Map semantics via the
 * exported helpers.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Stub import.meta.env before importing module under test
// ---------------------------------------------------------------------------
vi.stubGlobal('import', { meta: { env: { DEV: false, VITE_APP_VERSION: '1.0.0' } } });

// We test the dedup key builder directly by importing the internal function.
// Since it's not exported, we test observable behaviour via apiGet/apiPost.

// ---------------------------------------------------------------------------
// Minimal fetch stub
// ---------------------------------------------------------------------------
function makeOkResponse(data) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  };
}

// ---------------------------------------------------------------------------
// Tests for _buildDedupKey logic (white-box via observable dedup behaviour)
// ---------------------------------------------------------------------------

describe('in-flight dedup: GET requests', () => {
  let fetchCallCount;
  let capturedUrls;

  beforeEach(() => {
    fetchCallCount = 0;
    capturedUrls = [];

    // Stub global fetch
    global.fetch = vi.fn((url) => {
      fetchCallCount++;
      capturedUrls.push(url);
      return Promise.resolve(makeOkResponse({ success: true, data: { value: fetchCallCount }, meta: {} }));
    });

    global.window = { MesApi: undefined };
    global.document = { querySelector: () => null };
  });

  it('two identical GET calls share one in-flight fetch', async () => {
    // Import lazily so fetch stub is in place
    const { apiGet, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    // Fire two concurrent calls
    const [r1, r2] = await Promise.all([
      apiGet('/api/test/dedup'),
      apiGet('/api/test/dedup'),
    ]);

    // Only one fetch should have been issued
    expect(fetchCallCount).toBe(1);
    // Both callers get the same result
    expect(r1.data.value).toBe(r2.data.value);

    _clearInFlight();
  });

  it('GET calls to different URLs are NOT deduped', async () => {
    const { apiGet, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    await Promise.all([
      apiGet('/api/test/url-a'),
      apiGet('/api/test/url-b'),
    ]);

    expect(fetchCallCount).toBe(2);
    _clearInFlight();
  });

  it('sequential GET calls (after first settles) each issue a new fetch', async () => {
    const { apiGet, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    await apiGet('/api/test/seq');
    await apiGet('/api/test/seq');

    expect(fetchCallCount).toBe(2);
    _clearInFlight();
  });

  it('a GET call with its own externalSignal is NOT deduped with an identical-URL call', async () => {
    // Regression for the "signal is aborted without reason" bug
    // (production-achievement-chengxing-output follow-up, 2026-07-15): two
    // GET calls to the identical URL used to share one in-flight fetch +
    // AbortController even when only one caller supplied its own
    // externalSignal (e.g. a cancel-button controller). Aborting that
    // caller's signal then killed the OTHER, unrelated caller's request too.
    const { apiGet, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    const controller = new AbortController();
    const [r1, r2] = await Promise.all([
      apiGet('/api/test/dedup-signal', { signal: controller.signal }),
      apiGet('/api/test/dedup-signal'),
    ]);

    expect(fetchCallCount).toBe(2);
    expect(r1.success).toBe(true);
    expect(r2.success).toBe(true);
    _clearInFlight();
  });

  it('aborting one caller\'s externalSignal never rejects an unrelated identical-URL caller', async () => {
    const { apiGet, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    // Fetch that only resolves for calls without an abort signal already
    // fired; a call made with an aborted signal should reject via fetch's
    // own abort handling, exactly like the browser would.
    global.fetch = vi.fn((url, { signal } = {}) => {
      return new Promise((resolve, reject) => {
        if (signal) {
          signal.addEventListener('abort', () => reject(new DOMException('signal is aborted without reason', 'AbortError')));
        }
        setTimeout(() => resolve(makeOkResponse({ success: true, data: {}, meta: {} })), 10);
      });
    });

    const controller = new AbortController();
    const cancelledCall = apiGet('/api/test/dedup-abort', { signal: controller.signal });
    const unrelatedCall = apiGet('/api/test/dedup-abort');

    controller.abort();

    await expect(cancelledCall).rejects.toThrow();
    await expect(unrelatedCall).resolves.toMatchObject({ success: true });

    _clearInFlight();
  });
});

describe('in-flight dedup: POST requests', () => {
  let fetchCallCount;

  beforeEach(() => {
    fetchCallCount = 0;

    global.fetch = vi.fn(() => {
      fetchCallCount++;
      return Promise.resolve(makeOkResponse({ success: true, data: {}, meta: {} }));
    });

    global.window = { MesApi: undefined };
    global.document = { querySelector: () => null };
  });

  it('two identical POST calls each issue separate fetches (POST not deduped)', async () => {
    // POST dedup was intentionally removed in c27a9f9 to prevent
    // abort-signal cross-contamination between concurrent spool queries.
    const { apiPost, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    const body = { start_date: '2026-01-01', end_date: '2026-01-07' };
    const [r1, r2] = await Promise.all([
      apiPost('/api/test/post-dedup', body),
      apiPost('/api/test/post-dedup', body),
    ]);

    expect(fetchCallCount).toBe(2);
    expect(r1.success).toBe(r2.success);
    _clearInFlight();
  });

  it('POST calls with different bodies are NOT deduped', async () => {
    const { apiPost, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    await Promise.all([
      apiPost('/api/test/post-diff', { a: 1 }),
      apiPost('/api/test/post-diff', { a: 2 }),
    ]);

    expect(fetchCallCount).toBe(2);
    _clearInFlight();
  });
});

describe('in-flight dedup: size tracking', () => {
  beforeEach(() => {
    // slow fetch that we can control
    global.fetch = vi.fn(() => new Promise(() => {})); // never resolves
    global.window = { MesApi: undefined };
    global.document = { querySelector: () => null };
  });

  it('_inFlightSize reflects pending count', async () => {
    const { apiGet, _inFlightSize, _clearInFlight } = await import('../../src/core/api.js');
    _clearInFlight();

    expect(_inFlightSize()).toBe(0);

    // Start two different requests (not deduped — different URLs)
    const p1 = apiGet('/api/size-a');
    const p2 = apiGet('/api/size-b');

    expect(_inFlightSize()).toBe(2);
    _clearInFlight();
    expect(_inFlightSize()).toBe(0);

    // Prevent unhandled rejection
    p1.catch(() => {});
    p2.catch(() => {});
  });
});
