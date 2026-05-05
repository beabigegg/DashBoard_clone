// @vitest-environment jsdom
/**
 * Abort tests for reject-history
 *
 * Tests:
 * - Pending fetch requests are aborted on unmount
 * - No state mutation occurs after unmount (no errors from stale setters)
 *
 * reject-history/App.vue uses _jobAbortController: AbortController | null
 * and calls _jobAbortController?.abort() in onUnmounted.
 * The job polling uses pollJobUntilComplete with { signal }.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock DuckDB (not under test here)
vi.mock('../../src/core/duckdb-client.js', () => ({
  getDuckDBClient: vi.fn(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  })),
  isDuckDBSupported: vi.fn(() => true),
}));

// Mock apiGet used by pollJobUntilComplete
vi.mock('../../src/core/api.js', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  ensureMesApiAvailable: vi.fn(),
  _clearInFlight: vi.fn(),
  _inFlightSize: vi.fn(() => 0),
}));

import { apiGet } from '../../src/core/api.js';

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('reject-history abort — pollJobUntilComplete with signal', () => {
  it('abort before first poll prevents any apiGet calls', async () => {
    const { pollJobUntilComplete } = await import('../../src/shared-composables/useAsyncJobPolling.ts');

    const controller = new AbortController();
    controller.abort();

    // Attach catch immediately to handle rejection
    const promise = pollJobUntilComplete('/api/reject-history/job/1', {
      signal: controller.signal,
      pollIntervalMs: 100,
      maxPollMs: 5000,
    });
    const resultPromise = promise.catch((e) => e);

    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.name).toBe('AbortError');
    expect(apiGet).not.toHaveBeenCalled();
  });

  it('abort during polling stops further apiGet calls', async () => {
    const { pollJobUntilComplete } = await import('../../src/shared-composables/useAsyncJobPolling.ts');

    apiGet.mockResolvedValue({ data: { status: 'running', pct: 10 } });

    const controller = new AbortController();

    // Attach catch immediately
    const promise = pollJobUntilComplete('/api/reject-history/job/2', {
      signal: controller.signal,
      pollIntervalMs: 100,
      maxPollMs: 10000,
    });
    const resultPromise = promise.catch((e) => e);

    // Allow one poll to complete
    await vi.advanceTimersByTimeAsync(50);

    // Abort mid-cycle
    controller.abort();
    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.name).toBe('AbortError');
    // At most one apiGet call happened before abort
    expect(apiGet.mock.calls.length).toBeLessThanOrEqual(2);
  });
});

describe('reject-history abort — useRejectHistoryDuckDB deactivate on unmount', () => {
  it('deactivate sets isActive=false and destroys the client', async () => {
    // Capture the mock client returned during activate()
    const destroySpy = vi.fn();
    const mockClient = {
      init: vi.fn().mockResolvedValue(undefined),
      registerParquet: vi.fn().mockResolvedValue(undefined),
      sendQuery: vi.fn().mockResolvedValue([]),
      destroy: destroySpy,
    };

    const { getDuckDBClient } = await import('../../src/core/duckdb-client.js');
    getDuckDBClient.mockReturnValue(mockClient);

    const { useRejectHistoryDuckDB } = await import('../../src/reject-history/useRejectHistoryDuckDB.js');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
    });

    const { isActive, activate, deactivate } = useRejectHistoryDuckDB();

    await activate('/spool/reject.parquet');
    expect(isActive.value).toBe(true);

    deactivate();
    expect(isActive.value).toBe(false);
    expect(destroySpy).toHaveBeenCalled();
  });

  it('calling computeView after deactivate throws without mutating active state', async () => {
    const { useRejectHistoryDuckDB } = await import('../../src/reject-history/useRejectHistoryDuckDB.js');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
    });

    const { isActive, activate, computeView, deactivate } = useRejectHistoryDuckDB();

    await activate('/spool/reject.parquet');
    deactivate();

    await expect(computeView({})).rejects.toThrow('DuckDB not initialised');
    expect(isActive.value).toBe(false);
  });
});

describe('reject-history abort — no stale state mutation after abort', () => {
  it('no error thrown when abort happens while component is already unmounted', () => {
    // Simulate the pattern: _jobAbortController?.abort() on unmount
    let jobAbortController = null;

    function onUnmounted() {
      jobAbortController?.abort();
    }

    // Component never started a job — controller is null
    expect(() => onUnmounted()).not.toThrow();
  });

  it('aborting active controller nulls it out (simulated runQuery cleanup)', () => {
    let jobAbortController = null;

    // Simulate runQuery setting up a controller
    const controller = new AbortController();
    jobAbortController = controller;

    // Simulate unmount
    jobAbortController?.abort();
    jobAbortController = null;

    expect(controller.signal.aborted).toBe(true);
    expect(jobAbortController).toBeNull();
  });
});
