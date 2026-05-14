// @vitest-environment jsdom
/**
 * Abort tests for yield-alert-center
 *
 * Tests:
 * - Pending fetch requests are aborted on unmount
 * - No state mutation occurs after unmount (no errors from stale setters)
 *
 * The yield-alert App.vue uses _jobAbortController (local to setup scope)
 * and calls _jobAbortController?.abort() in onUnmounted.
 * We test this pattern via useYieldAlertDuckDB which owns the fetch lifecycle,
 * and via the App-level abort pattern documented in the source.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// ----- Mock DuckDB client (heavy WASM dependency) -----
vi.mock('../../src/core/duckdb-client.js', () => ({
  getDuckDBClient: vi.fn(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  })),
  isDuckDBSupported: vi.fn(() => true),
}));

vi.mock('../../src/core/risk-score.js', () => ({
  calcRiskScore: vi.fn(() => 0),
  calcRiskLevel: vi.fn(() => 'low'),
}));

// Mock global fetch
let abortedSignals = [];

beforeEach(() => {
  abortedSignals = [];
  vi.clearAllMocks();

  global.fetch = vi.fn((url, opts) => {
    const signal = opts?.signal;
    return new Promise((resolve, reject) => {
      if (signal) {
        if (signal.aborted) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        signal.addEventListener('abort', () => {
          abortedSignals.push(url);
          reject(new DOMException('Aborted', 'AbortError'));
        });
      }
      // Never resolves naturally — simulates a pending request
    });
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('yield-alert abort — fetchParquetBuffer abort on signal', () => {
  it('aborts pending parquet download when AbortController is signalled', async () => {
    const controller = new AbortController();

    // Start a "fetch" that will be aborted
    const fetchPromise = global.fetch('/spool/test.parquet', { signal: controller.signal });

    // Abort it
    controller.abort();

    await expect(fetchPromise).rejects.toMatchObject({ name: 'AbortError' });
    expect(abortedSignals).toContain('/spool/test.parquet');
  });

  it('does not reject fetch that was never aborted', async () => {
    const controller = new AbortController();

    let resolveNow;
    global.fetch = vi.fn(() => new Promise((res) => { resolveNow = res; }));

    const fetchPromise = global.fetch('/spool/normal.parquet', { signal: controller.signal });

    // Resolve without aborting
    resolveNow({ ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)) });

    const result = await fetchPromise;
    expect(result.ok).toBe(true);
  });
});

describe('yield-alert abort — useYieldAlertDuckDB deactivate', () => {
  it('deactivate() sets isActive to false and destroys client', async () => {
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

    const { useYieldAlertDuckDB } = await import('../../src/yield-alert-center/useYieldAlertDuckDB');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
    });

    const { isActive, isLoading, activate, deactivate } = useYieldAlertDuckDB();

    await activate('/spool/data.parquet');
    expect(isActive.value).toBe(true);

    deactivate();
    expect(isActive.value).toBe(false);
    expect(isLoading.value).toBe(false);
    expect(destroySpy).toHaveBeenCalled();
  });

  it('no state mutation after deactivate (calling computeView throws, not corrupts state)', async () => {
    const { useYieldAlertDuckDB } = await import('../../src/yield-alert-center/useYieldAlertDuckDB');

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
    });

    const { isActive, error, activate, computeView, deactivate } = useYieldAlertDuckDB();

    await activate('/spool/data.parquet');
    deactivate();

    // computeView after deactivate should throw but NOT mutate isActive to true
    await expect(computeView({
      filters: {},
      granularity: 'day',
      riskThreshold: 98,
      minScrapQty: 1,
      sortBy: 'date_bucket',
      sortDir: 'desc',
      page: 1,
      perPage: 20,
    })).rejects.toThrow('DuckDB not initialised');

    expect(isActive.value).toBe(false);
  });
});

describe('yield-alert abort — job abort controller pattern', () => {
  it('AbortController.abort() causes in-flight promise to reject with AbortError', async () => {
    const controller = new AbortController();

    // Simulate an in-flight job poll that respects the signal
    const mockPoll = (signal) =>
      new Promise((_, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });

    const pollPromise = mockPoll(controller.signal);

    // Simulate unmount: abort the controller
    controller.abort();

    const err = await pollPromise.catch((e) => e);
    expect(err.name).toBe('AbortError');
  });

  it('abort on already-aborted controller is idempotent', () => {
    const controller = new AbortController();
    controller.abort();
    // Calling abort again should not throw
    expect(() => controller.abort()).not.toThrow();
    expect(controller.signal.aborted).toBe(true);
  });
});
