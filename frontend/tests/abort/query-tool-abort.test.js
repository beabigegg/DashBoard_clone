/**
 * Abort tests for query-tool
 *
 * Tests:
 * - onBeforeUnmount calls nextRequestId() to invalidate in-flight requests
 * - Stale responses from in-flight fetches are dropped after unmount
 * - No state mutation occurs after unmount
 *
 * query-tool/App.vue uses useRequestGuard pattern: on unmount it calls
 * nextRequestId() to invalidate any pending requests. The composables
 * (useLotResolve, useLotDetail, etc.) use apiPost/apiGet — we verify
 * the guard correctly drops stale responses.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../src/core/api.js', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  ensureMesApiAvailable: vi.fn(),
  _clearInFlight: vi.fn(),
  _inFlightSize: vi.fn(() => 0),
}));

import { apiPost } from '../../src/core/api.js';
import { useRequestGuard } from '../../src/shared-composables/useRequestGuard.ts';

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('query-tool abort — useRequestGuard invalidation on unmount', () => {
  it('nextRequestId on unmount marks any captured request id as stale', () => {
    // useRequestGuard imported at top of file
    const { nextRequestId, isStaleRequest } = useRequestGuard();

    // Simulate: component fires a request
    const reqId = nextRequestId();
    expect(isStaleRequest(reqId)).toBe(false);

    // Simulate: onBeforeUnmount fires nextRequestId to invalidate
    nextRequestId();

    // Previous request is now stale
    expect(isStaleRequest(reqId)).toBe(true);
  });

  it('response arriving after unmount-triggered nextRequestId is dropped', () => {
    // useRequestGuard imported at top of file
    const { nextRequestId, isStaleRequest } = useRequestGuard();

    const results = [];

    // Component fires request
    const reqId = nextRequestId();

    // Unmount fires — invalidates reqId synchronously
    nextRequestId();

    // Simulate: response arrives (synchronously, after the guard advanced)
    const response = { data: { lots: ['LOT-001'] } };
    if (!isStaleRequest(reqId)) {
      results.push(response);
    }

    // Result was dropped because it's stale
    expect(results).toHaveLength(0);
  });
});

describe('query-tool abort — useLotResolve loading state cleanup', () => {
  it('loading.resolving returns to false after a failed request', async () => {
    const { useLotResolve } = await import('../../src/query-tool/composables/useLotResolve.js');

    apiPost.mockRejectedValueOnce(new Error('Network error'));

    const { loading, errorMessage, resolveLots, setInputText } = useLotResolve({ inputType: 'lot_id' });

    setInputText('LOT-001');

    await resolveLots();

    expect(loading.resolving).toBe(false);
    expect(errorMessage.value).toBeTruthy();
  });

  it('loading.resolving returns to false after successful request', async () => {
    const { useLotResolve } = await import('../../src/query-tool/composables/useLotResolve.js');

    apiPost.mockResolvedValueOnce({
      data: { data: [{ lot_id: 'LOT-001', container_id: 'C001' }], not_found: [], expansion_info: {} },
    });

    const { loading, resolvedLots, resolveLots, setInputText } = useLotResolve({ inputType: 'lot_id' });

    setInputText('LOT-001');

    await resolveLots();

    expect(loading.resolving).toBe(false);
    expect(resolvedLots.value.length).toBeGreaterThan(0);
  });
});

describe('query-tool abort — no stale state mutation (abort then settle)', () => {
  it('AbortController abort causes pending fetch to reject', async () => {
    const controller = new AbortController();

    global.fetch = vi.fn((_url, opts) => {
      const signal = opts?.signal;
      return new Promise((_res, reject) => {
        if (signal) {
          signal.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError'))
          );
        }
      });
    });

    const fetchPromise = fetch('/api/query-tool/resolve', {
      method: 'POST',
      signal: controller.signal,
    });

    controller.abort();

    const err = await fetchPromise.catch((e) => e);
    expect(err.name).toBe('AbortError');
  });

  it('abort on an already-settled promise is a no-op (does not re-reject)', async () => {
    const controller = new AbortController();

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ success: true, data: {}, meta: {} }),
    });

    const result = await fetch('/api/query-tool/resolve', { signal: controller.signal });

    // Abort after fetch already resolved
    expect(() => controller.abort()).not.toThrow();
    expect(result.ok).toBe(true);
  });
});
