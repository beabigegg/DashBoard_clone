/**
 * useAsyncJobPolling.js
 *
 * Shared composable for polling async job status endpoints.
 * Extracted from useTraceProgress.js for reuse by reject-history and other
 * heavy-query features.
 *
 * Usage:
 *   const { pollJobUntilComplete } = useAsyncJobPolling()
 *   await pollJobUntilComplete(statusUrl, { signal, onProgress })
 */

import { apiGet } from '../core/api.js';

const JOB_POLL_INTERVAL_MS = 3000;
const JOB_POLL_MAX_MS = 1800000; // 30 minutes

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Poll an async job status URL until the job completes or fails.
 *
 * The server response is expected to include a `status` field with values:
 *   'queued' | 'started' | 'running' | 'completed' | 'finished' | 'failed'
 *
 * @param {string} statusUrl - Full URL of the job status endpoint
 * @param {object} [options]
 * @param {AbortSignal} [options.signal] - AbortController signal for cancellation
 * @param {function} [options.onProgress] - Callback invoked with each status response
 * @param {number} [options.pollIntervalMs] - Override poll interval in ms
 * @param {number} [options.maxPollMs] - Override maximum polling duration in ms
 * @returns {Promise<object>} The final status object when job completes
 * @throws {DOMException} 'AbortError' if cancelled via signal
 * @throws {Error} With errorCode 'JOB_FAILED' on job failure
 * @throws {Error} With errorCode 'JOB_POLL_TIMEOUT' if max poll duration exceeded
 */
export async function pollJobUntilComplete(statusUrl, {
  signal,
  onProgress,
  pollIntervalMs = JOB_POLL_INTERVAL_MS,
  maxPollMs = JOB_POLL_MAX_MS,
} = {}) {
  const started = Date.now();

  while (true) {
    if (signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError');
    }

    const raw = await apiGet(statusUrl, { timeout: 15000, signal });
    // Unwrap the standard API envelope { success, data, meta }
    const status = raw?.data || raw;

    if (typeof onProgress === 'function') {
      onProgress(status);
    }

    // Accept both 'finished' (trace) and 'completed' (reject) as done signals
    if (status.status === 'finished' || status.status === 'completed') {
      return status;
    }

    if (status.status === 'failed') {
      const error = new Error(status.error || '非同步查詢失敗');
      error.errorCode = 'JOB_FAILED';
      throw error;
    }

    if (Date.now() - started > maxPollMs) {
      const error = new Error('非同步查詢超時');
      error.errorCode = 'JOB_POLL_TIMEOUT';
      throw error;
    }

    await sleep(pollIntervalMs);
  }
}

/**
 * Composable wrapper that provides pollJobUntilComplete.
 * Allows future extension (e.g. reactive state) without breaking callers.
 */
export function useAsyncJobPolling() {
  return {
    pollJobUntilComplete,
  };
}
