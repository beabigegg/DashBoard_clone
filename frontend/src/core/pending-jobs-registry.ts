/**
 * Pending Jobs Registry
 *
 * Persists async job IDs to localStorage so that in-flight jobs survive
 * page refresh and can be recovered on next load.
 */

import type { PendingJobEntry } from './types.js';

export type { PendingJobEntry } from './types.js';

const STORAGE_KEY = 'mes:pending_jobs';
const MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 hours — beyond job TTL, safe to discard

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _readAll(): PendingJobEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as PendingJobEntry[]) : [];
  } catch {
    return [];
  }
}

function _writeAll(entries: PendingJobEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage may be unavailable (private mode, quota exceeded) — fail silently
  }
}

function _isExpired(entry: PendingJobEntry): boolean {
  return typeof entry.queued_at === 'number' && Date.now() - entry.queued_at > MAX_AGE_MS;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Register a newly-enqueued job.
 *
 * @param job_id  - RQ job ID
 * @param prefix  - Service prefix (e.g. "reject")
 * @param endpoint - Originating endpoint for UI context
 */
export function registerJob(
  job_id: string | null | undefined,
  prefix: string | null | undefined,
  endpoint = ''
): void {
  if (!job_id || !prefix) return;

  const existing = _readAll().filter((e) => !_isExpired(e));
  // Dedup: replace existing entry for same job_id
  const filtered = existing.filter((e) => e.job_id !== job_id);
  filtered.push({ job_id, prefix, endpoint, queued_at: Date.now() });
  _writeAll(filtered);
}

/**
 * Remove a job from the registry (called when job completes, fails, or is abandoned).
 */
export function deregisterJob(job_id: string): void {
  if (!job_id) return;
  const updated = _readAll().filter((e) => e.job_id !== job_id);
  _writeAll(updated);
}

/**
 * Return all non-expired pending jobs.
 */
export function getPendingJobs(): PendingJobEntry[] {
  const all = _readAll();
  const valid = all.filter((e) => !_isExpired(e));
  // Persist the pruned list back (cleanup stale entries)
  if (valid.length !== all.length) {
    _writeAll(valid);
  }
  return valid;
}

/**
 * Clear all pending jobs (e.g. on logout).
 */
export function clearAllJobs(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * Returns true if a job_id is currently tracked as pending.
 */
export function isJobPending(job_id: string): boolean {
  return getPendingJobs().some((e) => e.job_id === job_id);
}
