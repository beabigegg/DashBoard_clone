/**
 * Tests for pending-jobs-registry.js
 *
 * Uses a minimal localStorage stub (no jsdom required).
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  registerJob,
  deregisterJob,
  getPendingJobs,
  clearAllJobs,
  isJobPending,
} from '../src/core/pending-jobs-registry.js';

// ---------------------------------------------------------------------------
// localStorage stub
// ---------------------------------------------------------------------------

function makeLocalStorageStub() {
  const store = {};
  return {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
    _store: store,
  };
}

beforeEach(() => {
  const stub = makeLocalStorageStub();
  global.localStorage = stub;
  // Clear between tests
  stub.clear();
});

// ---------------------------------------------------------------------------
// registerJob
// ---------------------------------------------------------------------------

describe('registerJob', () => {
  it('adds a job to the registry', () => {
    registerJob('job-001', 'reject', '/api/reject-history/query');
    const jobs = getPendingJobs();
    expect(jobs).toHaveLength(1);
    expect(jobs[0].job_id).toBe('job-001');
    expect(jobs[0].prefix).toBe('reject');
    expect(jobs[0].endpoint).toBe('/api/reject-history/query');
  });

  it('stores queued_at as a number', () => {
    registerJob('job-002', 'yield_alert');
    const jobs = getPendingJobs();
    expect(typeof jobs[0].queued_at).toBe('number');
    expect(jobs[0].queued_at).toBeGreaterThan(0);
  });

  it('defaults endpoint to empty string when omitted', () => {
    registerJob('job-003', 'reject');
    expect(getPendingJobs()[0].endpoint).toBe('');
  });

  it('deduplicates: re-registering same job_id replaces existing entry', () => {
    registerJob('job-004', 'reject');
    registerJob('job-004', 'yield_alert', '/api/yield-alert/query');
    const jobs = getPendingJobs();
    expect(jobs).toHaveLength(1);
    expect(jobs[0].prefix).toBe('yield_alert');
  });

  it('does nothing if job_id is falsy', () => {
    registerJob('', 'reject');
    registerJob(null, 'reject');
    expect(getPendingJobs()).toHaveLength(0);
  });

  it('does nothing if prefix is falsy', () => {
    registerJob('job-005', '');
    expect(getPendingJobs()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// deregisterJob
// ---------------------------------------------------------------------------

describe('deregisterJob', () => {
  it('removes a registered job', () => {
    registerJob('job-010', 'reject');
    deregisterJob('job-010');
    expect(getPendingJobs()).toHaveLength(0);
  });

  it('is a no-op for unknown job_id', () => {
    registerJob('job-011', 'reject');
    deregisterJob('does-not-exist');
    expect(getPendingJobs()).toHaveLength(1);
  });

  it('is a no-op when registry is empty', () => {
    expect(() => deregisterJob('job-012')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// getPendingJobs
// ---------------------------------------------------------------------------

describe('getPendingJobs', () => {
  it('returns empty array when nothing registered', () => {
    expect(getPendingJobs()).toEqual([]);
  });

  it('prunes expired entries (queued_at > 4h ago)', () => {
    const staleEntry = {
      job_id: 'stale-001',
      prefix: 'reject',
      endpoint: '',
      queued_at: Date.now() - 5 * 60 * 60 * 1000, // 5 hours ago
    };
    localStorage.setItem('mes:pending_jobs', JSON.stringify([staleEntry]));

    const jobs = getPendingJobs();
    expect(jobs).toHaveLength(0);
  });

  it('keeps non-expired entries', () => {
    registerJob('fresh-001', 'reject');
    expect(getPendingJobs()).toHaveLength(1);
  });

  it('returns multiple registered jobs', () => {
    registerJob('job-020', 'reject');
    registerJob('job-021', 'yield_alert');
    expect(getPendingJobs()).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// clearAllJobs
// ---------------------------------------------------------------------------

describe('clearAllJobs', () => {
  it('removes all registered jobs', () => {
    registerJob('job-030', 'reject');
    registerJob('job-031', 'yield_alert');
    clearAllJobs();
    expect(getPendingJobs()).toHaveLength(0);
  });

  it('is idempotent when registry already empty', () => {
    expect(() => clearAllJobs()).not.toThrow();
    expect(getPendingJobs()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// isJobPending
// ---------------------------------------------------------------------------

describe('isJobPending', () => {
  it('returns true for a registered job', () => {
    registerJob('job-040', 'reject');
    expect(isJobPending('job-040')).toBe(true);
  });

  it('returns false for an unknown job', () => {
    expect(isJobPending('unknown-job')).toBe(false);
  });

  it('returns false after deregistering', () => {
    registerJob('job-041', 'reject');
    deregisterJob('job-041');
    expect(isJobPending('job-041')).toBe(false);
  });
});
