/**
 * Unit tests for frontend/src/core/datetime.js
 *
 * Tests formatLogTime with valid ISO, naive ISO, null, and unparseable input.
 */
import test from 'node:test';
import assert from 'node:assert/strict';

// Import the module under test
import { formatLogTime } from '../src/core/datetime.js';


// ── formatLogTime ──────────────────────────────────────────────────────────

test('formatLogTime: returns "-" for null', () => {
  assert.strictEqual(formatLogTime(null), '-');
});

test('formatLogTime: returns "-" for undefined', () => {
  assert.strictEqual(formatLogTime(undefined), '-');
});

test('formatLogTime: returns "-" for empty string', () => {
  assert.strictEqual(formatLogTime(''), '-');
});

test('formatLogTime: formats valid UTC ISO string', () => {
  const result = formatLogTime('2026-04-13T03:48:30.000000+00:00');
  // Should be a non-empty string in zh-TW locale format (YYYY/MM/DD HH:mm:ss)
  assert.ok(typeof result === 'string');
  assert.ok(result.length > 0);
  assert.notStrictEqual(result, '-');
  // Should contain year and separators typical of zh-TW locale
  assert.match(result, /2026/);
});

test('formatLogTime: formats naive ISO string (no timezone)', () => {
  // Naive ISO strings are parsed as local time by Date constructor
  const result = formatLogTime('2026-04-13T03:48:30');
  assert.ok(typeof result === 'string');
  assert.ok(result.length > 0);
  assert.notStrictEqual(result, '-');
  assert.match(result, /2026/);
});

test('formatLogTime: returns original value for unparseable string', () => {
  const garbage = 'not-a-date-xyz';
  const result = formatLogTime(garbage);
  assert.strictEqual(result, garbage);
});
