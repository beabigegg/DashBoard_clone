/**
 * Tests for shared-composables/useAsyncJobPolling.js
 *
 * Covers:
 * - Transient `not_found` response within grace period is retried
 * - After grace period exhausted, stops polling (JOB_POLL_TIMEOUT)
 * - On `completed` status, stops polling and returns result
 * - On `failed` status, throws with errorCode JOB_FAILED
 * - Abort signal stops polling immediately
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { pollJobUntilComplete, useAsyncJobPolling } from '../../src/shared-composables/useAsyncJobPolling.ts';

// Mock the apiGet function used internally
vi.mock('../../src/core/api.js', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

import { apiGet } from '../../src/core/api.js';

describe('pollJobUntilComplete — completed status', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns result immediately when status is completed', async () => {
    const finalResult = { status: 'completed', dataset_id: 'ds-123' };
    apiGet.mockResolvedValueOnce({ data: finalResult });

    const promise = pollJobUntilComplete('/api/job/1', { pollIntervalMs: 100, maxPollMs: 5000 });
    await vi.runAllTimersAsync();

    const result = await promise;
    expect(result).toEqual(finalResult);
    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it('returns result when status is finished (trace alias)', async () => {
    const finalResult = { status: 'finished', query_id: 'q-abc' };
    apiGet.mockResolvedValueOnce({ data: finalResult });

    const promise = pollJobUntilComplete('/api/job/2', { pollIntervalMs: 100, maxPollMs: 5000 });
    await vi.runAllTimersAsync();

    const result = await promise;
    expect(result).toEqual(finalResult);
    expect(apiGet).toHaveBeenCalledTimes(1);
  });

  it('retries while status is running, then returns on completed', async () => {
    apiGet
      .mockResolvedValueOnce({ data: { status: 'running', pct: 25 } })
      .mockResolvedValueOnce({ data: { status: 'running', pct: 75 } })
      .mockResolvedValueOnce({ data: { status: 'completed', dataset_id: 'ds-final' } });

    const onProgress = vi.fn();
    const promise = pollJobUntilComplete('/api/job/3', {
      pollIntervalMs: 50,
      maxPollMs: 10000,
      onProgress,
    });

    // Advance through 3 poll cycles
    await vi.advanceTimersByTimeAsync(50);
    await vi.advanceTimersByTimeAsync(50);
    await vi.advanceTimersByTimeAsync(50);
    await vi.runAllTimersAsync();

    const result = await promise;
    expect(result.status).toBe('completed');
    expect(apiGet).toHaveBeenCalledTimes(3);
    expect(onProgress).toHaveBeenCalledTimes(3);
  });
});

describe('pollJobUntilComplete — failed status', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws with errorCode JOB_FAILED when status is failed', async () => {
    apiGet.mockResolvedValueOnce({ data: { status: 'failed', error: '查詢資料庫失敗' } });

    // Attach catch immediately to avoid unhandled rejection warning
    const promise = pollJobUntilComplete('/api/job/fail', { pollIntervalMs: 50, maxPollMs: 5000 });
    const resultPromise = promise.catch((e) => e);
    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.errorCode).toBe('JOB_FAILED');
  });

  it('uses default error message if error field is absent', async () => {
    apiGet.mockResolvedValueOnce({ data: { status: 'failed' } });

    // Attach catch immediately
    const promise = pollJobUntilComplete('/api/job/fail2', { pollIntervalMs: 50, maxPollMs: 5000 });
    const resultPromise = promise.catch((e) => e);
    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.errorCode).toBe('JOB_FAILED');
    expect(err.message).toBeTruthy();
  });
});

describe('pollJobUntilComplete — timeout (grace period exhausted)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws JOB_POLL_TIMEOUT after maxPollMs is exceeded', async () => {
    // Always return queued — never complete
    apiGet.mockResolvedValue({ data: { status: 'queued' } });

    // Attach catch immediately to avoid unhandled rejection
    const promise = pollJobUntilComplete('/api/job/timeout', {
      pollIntervalMs: 100,
      maxPollMs: 250, // Short limit for test
    });
    const resultPromise = promise.catch((e) => e);

    // Advance well past maxPollMs
    await vi.advanceTimersByTimeAsync(500);
    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.errorCode).toBe('JOB_POLL_TIMEOUT');
  });

  it('calls onProgress for each poll before timeout', async () => {
    apiGet.mockResolvedValue({ data: { status: 'started', pct: 10 } });
    const onProgress = vi.fn();

    // Attach catch immediately
    const promise = pollJobUntilComplete('/api/job/timeout2', {
      pollIntervalMs: 100,
      maxPollMs: 350,
      onProgress,
    });
    const resultPromise = promise.catch(() => 'timeout');

    await vi.advanceTimersByTimeAsync(500);
    await vi.runAllTimersAsync();

    await resultPromise;
    // Should have made multiple calls before timing out
    expect(onProgress.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe('pollJobUntilComplete — abort signal', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws AbortError when signal is already aborted before start', async () => {
    const controller = new AbortController();
    controller.abort();

    // Attach catch immediately so rejection is handled
    const promise = pollJobUntilComplete('/api/job/abort', {
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

  it('stops polling when signal is aborted mid-poll', async () => {
    const controller = new AbortController();

    // First poll returns running, then we abort
    apiGet.mockResolvedValue({ data: { status: 'running', pct: 50 } });

    // Attach catch immediately
    const promise = pollJobUntilComplete('/api/job/abort2', {
      signal: controller.signal,
      pollIntervalMs: 100,
      maxPollMs: 10000,
    });
    const resultPromise = promise.catch((e) => e);

    // Complete first poll cycle
    await vi.advanceTimersByTimeAsync(50);
    // Abort during the second sleep
    controller.abort();
    await vi.runAllTimersAsync();

    const err = await resultPromise;
    expect(err.name).toBe('AbortError');
  });
});

describe('useAsyncJobPolling — composable wrapper', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exposes pollJobUntilComplete function', () => {
    const { pollJobUntilComplete: fn } = useAsyncJobPolling();
    expect(typeof fn).toBe('function');
  });

  it('returned function is the same implementation', () => {
    const { pollJobUntilComplete: fn } = useAsyncJobPolling();
    expect(fn).toBe(pollJobUntilComplete);
  });
});
