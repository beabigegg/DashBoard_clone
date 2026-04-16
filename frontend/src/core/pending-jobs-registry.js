/**
 * Pending Jobs Registry
 *
 * Persists async job IDs to localStorage so that in-flight jobs survive
 * page refresh and can be recovered on next load.
 *
 * Schema per entry (JSON-serialised in localStorage):
 *   {
 *     job_id:    string   — RQ job identifier
 *     prefix:    string   — service prefix (e.g. "reject", "yield_alert")
 *     endpoint:  string   — originating API endpoint (for UI context)
 *     queued_at: number   — epoch ms (Date.now())
 *   }
 *
 * Storage key: "mes:pending_jobs"
 */

const STORAGE_KEY = 'mes:pending_jobs';
const MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 hours — beyond job TTL, safe to discard

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function _writeAll(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage may be unavailable (private mode, quota exceeded) — fail silently
  }
}

function _isExpired(entry) {
  return typeof entry.queued_at === 'number' && Date.now() - entry.queued_at > MAX_AGE_MS;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Register a newly-enqueued job.
 *
 * @param {string} job_id  - RQ job ID
 * @param {string} prefix  - Service prefix (e.g. "reject")
 * @param {string} [endpoint] - Originating endpoint for UI context
 */
export function registerJob(job_id, prefix, endpoint = '') {
  if (!job_id || !prefix) return;

  const existing = _readAll().filter((e) => !_isExpired(e));
  // Dedup: replace existing entry for same job_id
  const filtered = existing.filter((e) => e.job_id !== job_id);
  filtered.push({ job_id, prefix, endpoint, queued_at: Date.now() });
  _writeAll(filtered);
}

/**
 * Remove a job from the registry (called when job completes, fails, or is abandoned).
 *
 * @param {string} job_id
 */
export function deregisterJob(job_id) {
  if (!job_id) return;
  const updated = _readAll().filter((e) => e.job_id !== job_id);
  _writeAll(updated);
}

/**
 * Return all non-expired pending jobs.
 *
 * @returns {Array<{job_id: string, prefix: string, endpoint: string, queued_at: number}>}
 */
export function getPendingJobs() {
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
export function clearAllJobs() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * Returns true if a job_id is currently tracked as pending.
 *
 * @param {string} job_id
 * @returns {boolean}
 */
export function isJobPending(job_id) {
  return getPendingJobs().some((e) => e.job_id === job_id);
}
