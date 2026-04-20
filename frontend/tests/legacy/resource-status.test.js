import test from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeStatus,
  resolveOuBadgeClass,
  getStatusDisplay,
  STATUS_DISPLAY_MAP,
  STATUS_AGGREGATION,
  MATRIX_STATUS_COLUMNS,
  OU_BADGE_THRESHOLDS,
} from '../../src/resource-shared/constants.js';


// ── normalizeStatus ────────────────────────────────────────────────────────

test('normalizeStatus returns PRD for "PRD"', () => {
  assert.equal(normalizeStatus('PRD'), 'PRD');
});

test('normalizeStatus returns UDT for "PM" (aggregated)', () => {
  assert.equal(normalizeStatus('PM'), 'UDT');
});

test('normalizeStatus returns EGT for "ENG" (aggregated)', () => {
  assert.equal(normalizeStatus('ENG'), 'EGT');
});

test('normalizeStatus returns NST for "OFF" (aggregated)', () => {
  assert.equal(normalizeStatus('OFF'), 'NST');
});

test('normalizeStatus returns OTHER for unknown status', () => {
  assert.equal(normalizeStatus('UNKNOWN_XYZ'), 'OTHER');
});

test('normalizeStatus returns OTHER for empty string', () => {
  assert.equal(normalizeStatus(''), 'OTHER');
});

test('normalizeStatus returns OTHER for null', () => {
  assert.equal(normalizeStatus(null), 'OTHER');
});

test('normalizeStatus is case-insensitive', () => {
  assert.equal(normalizeStatus('prd'), 'PRD');
  assert.equal(normalizeStatus('Prd'), 'PRD');
});


// ── resolveOuBadgeClass ───────────────────────────────────────────────────

test('resolveOuBadgeClass returns "high" for value >= 80', () => {
  assert.equal(resolveOuBadgeClass(80), 'high');
  assert.equal(resolveOuBadgeClass(95), 'high');
  assert.equal(resolveOuBadgeClass(100), 'high');
});

test('resolveOuBadgeClass returns "medium" for value >= 50 and < 80', () => {
  assert.equal(resolveOuBadgeClass(50), 'medium');
  assert.equal(resolveOuBadgeClass(70), 'medium');
  assert.equal(resolveOuBadgeClass(79.9), 'medium');
});

test('resolveOuBadgeClass returns "low" for value < 50', () => {
  assert.equal(resolveOuBadgeClass(0), 'low');
  assert.equal(resolveOuBadgeClass(49.9), 'low');
});

test('resolveOuBadgeClass handles null/undefined gracefully', () => {
  const result = resolveOuBadgeClass(null);
  assert.ok(['low', 'medium', 'high'].includes(result));
});


// ── getStatusDisplay ──────────────────────────────────────────────────────

test('getStatusDisplay returns Chinese label for PRD', () => {
  assert.equal(getStatusDisplay('PRD'), STATUS_DISPLAY_MAP['PRD']);
});

test('getStatusDisplay returns normalized status for unknown entries', () => {
  // Unknown statuses return the normalized (uppercase) status itself, not fallback
  const result = getStatusDisplay('unknown_status', '--');
  assert.equal(result, 'UNKNOWN_STATUS');
});

test('getStatusDisplay uses fallback for empty/null input', () => {
  assert.equal(getStatusDisplay('', '--'), '--');
  assert.equal(getStatusDisplay(null, '--'), '--');
});


// ── Constants ─────────────────────────────────────────────────────────────

test('MATRIX_STATUS_COLUMNS contains seven standard statuses', () => {
  const expected = ['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST', 'OTHER'];
  assert.deepEqual([...MATRIX_STATUS_COLUMNS], expected);
});

test('OU_BADGE_THRESHOLDS has high, medium, low keys', () => {
  assert.ok('high' in OU_BADGE_THRESHOLDS);
  assert.ok('medium' in OU_BADGE_THRESHOLDS);
  assert.ok('low' in OU_BADGE_THRESHOLDS);
});

test('OU_BADGE_THRESHOLDS high > medium > low', () => {
  assert.ok(OU_BADGE_THRESHOLDS.high > OU_BADGE_THRESHOLDS.medium);
  assert.ok(OU_BADGE_THRESHOLDS.medium > OU_BADGE_THRESHOLDS.low);
});

test('STATUS_AGGREGATION maps PM to UDT', () => {
  assert.equal(STATUS_AGGREGATION['PM'], 'UDT');
});
