/**
 * Tests for admin-performance metric utility functions.
 *
 * Covers metric formatting and threshold logic used in
 * the admin performance monitoring dashboard.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── Metric formatting utilities ────────────────────────────────────────────

/**
 * Format a latency value in ms, rounded to 1 decimal.
 * Returns '--' for null/undefined/zero.
 */
function formatLatencyMs(val) {
  if (val == null || Number.isNaN(val)) return '--';
  return `${Math.round(Number(val) * 10) / 10}ms`;
}

/**
 * Compute slow query rate from count and slow_count.
 */
function calcSlowQueryRate(count, slowCount) {
  if (!count || count === 0) return 0;
  return Math.round((slowCount / count) * 1000) / 10;
}

/**
 * Determine health status class from latency p95 value.
 */
function resolveLatencyHealth(p95Ms) {
  if (p95Ms == null) return 'unknown';
  if (p95Ms < 500) return 'healthy';
  if (p95Ms < 2000) return 'warning';
  return 'critical';
}


// ── formatLatencyMs ────────────────────────────────────────────────────────

test('formatLatencyMs returns "--" for null', () => {
  assert.equal(formatLatencyMs(null), '--');
});

test('formatLatencyMs formats integer milliseconds', () => {
  assert.equal(formatLatencyMs(250), '250ms');
});

test('formatLatencyMs rounds to one decimal', () => {
  assert.equal(formatLatencyMs(123.456), '123.5ms');
});


// ── calcSlowQueryRate ──────────────────────────────────────────────────────

test('calcSlowQueryRate returns 0 for zero total count', () => {
  assert.equal(calcSlowQueryRate(0, 5), 0);
});

test('calcSlowQueryRate returns 0 for null count', () => {
  assert.equal(calcSlowQueryRate(null, 5), 0);
});

test('calcSlowQueryRate computes correct percentage', () => {
  // 10 slow out of 100 total = 10%
  assert.equal(calcSlowQueryRate(100, 10), 10);
});

test('calcSlowQueryRate rounds to one decimal', () => {
  // 1 slow out of 3 total = 33.3%
  const result = calcSlowQueryRate(3, 1);
  assert.equal(result, Math.round((1 / 3) * 1000) / 10);
});


// ── resolveLatencyHealth ──────────────────────────────────────────────────

test('resolveLatencyHealth returns "healthy" for p95 < 500ms', () => {
  assert.equal(resolveLatencyHealth(200), 'healthy');
  assert.equal(resolveLatencyHealth(499), 'healthy');
});

test('resolveLatencyHealth returns "warning" for p95 500-1999ms', () => {
  assert.equal(resolveLatencyHealth(500), 'warning');
  assert.equal(resolveLatencyHealth(1999), 'warning');
});

test('resolveLatencyHealth returns "critical" for p95 >= 2000ms', () => {
  assert.equal(resolveLatencyHealth(2000), 'critical');
  assert.equal(resolveLatencyHealth(5000), 'critical');
});

test('resolveLatencyHealth returns "unknown" for null', () => {
  assert.equal(resolveLatencyHealth(null), 'unknown');
});


// ── Performance history bucket helpers ────────────────────────────────────

/**
 * Extract p50/p95 from a performance history array.
 */
function getLatestBucketLatency(history) {
  if (!Array.isArray(history) || history.length === 0) {
    return { p50_ms: null, p95_ms: null };
  }
  const latest = history[history.length - 1];
  return { p50_ms: latest.p50_ms ?? null, p95_ms: latest.p95_ms ?? null };
}

test('getLatestBucketLatency returns nulls for empty history', () => {
  const result = getLatestBucketLatency([]);
  assert.equal(result.p50_ms, null);
  assert.equal(result.p95_ms, null);
});

test('getLatestBucketLatency returns last entry values', () => {
  const history = [
    { p50_ms: 100, p95_ms: 400 },
    { p50_ms: 120, p95_ms: 450 },
  ];
  const result = getLatestBucketLatency(history);
  assert.equal(result.p50_ms, 120);
  assert.equal(result.p95_ms, 450);
});
