import { apiGet } from '../core/api.js';

const JOB_POLL_INTERVAL_MS = 3000;
const JOB_POLL_MAX_MS = 1800000; // 30 minutes

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface JobStatusResponse {
  status: string;
  error?: string;
  elapsed_seconds?: number;
  progress?: string;
  [key: string]: unknown;
}

export interface PollOptions {
  signal?: AbortSignal;
  onProgress?: (status: JobStatusResponse) => void;
  pollIntervalMs?: number;
  maxPollMs?: number;
}

export interface AsyncJobPollingComposable {
  pollJobUntilComplete: (statusUrl: string, options?: PollOptions) => Promise<JobStatusResponse>;
}

interface JobError extends Error {
  errorCode: string;
}

/**
 * Poll an async job status URL until the job completes or fails.
 *
 * The server response is expected to include a `status` field with values:
 *   'queued' | 'started' | 'running' | 'completed' | 'finished' | 'failed'
 *
 * @param statusUrl - Full URL of the job status endpoint
 * @param options
 * @param options.signal - AbortController signal for cancellation
 * @param options.onProgress - Callback invoked with each status response
 * @param options.pollIntervalMs - Override poll interval in ms
 * @param options.maxPollMs - Override maximum polling duration in ms
 * @returns The final status object when job completes
 * @throws DOMException 'AbortError' if cancelled via signal
 * @throws Error with errorCode 'JOB_FAILED' on job failure
 * @throws Error with errorCode 'JOB_POLL_TIMEOUT' if max poll duration exceeded
 */
export async function pollJobUntilComplete(
  statusUrl: string,
  {
    signal,
    onProgress,
    pollIntervalMs = JOB_POLL_INTERVAL_MS,
    maxPollMs = JOB_POLL_MAX_MS,
  }: PollOptions = {},
): Promise<JobStatusResponse> {
  const started = Date.now();

  while (true) {
    if (signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError');
    }

    const raw = await apiGet(statusUrl, { timeout: 15000, signal });
    // Unwrap the standard API envelope { success, data, meta }
    const rawObj = raw as { data?: unknown } | null;
    const status: JobStatusResponse = (rawObj?.data ?? raw) as JobStatusResponse;

    if (typeof onProgress === 'function') {
      onProgress(status);
    }

    // Accept both 'finished' (trace) and 'completed' (reject) as done signals
    if (status.status === 'finished' || status.status === 'completed') {
      return status;
    }

    if (status.status === 'failed') {
      const error = new Error(status.error || '非同步查詢失敗') as JobError;
      error.errorCode = 'JOB_FAILED';
      throw error;
    }

    if (Date.now() - started > maxPollMs) {
      const error = new Error('非同步查詢超時') as JobError;
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
export function useAsyncJobPolling(): AsyncJobPollingComposable {
  return {
    pollJobUntilComplete,
  };
}
