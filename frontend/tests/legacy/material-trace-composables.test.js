/**
 * Tests for material-trace composable logic.
 *
 * Material trace uses parseMultiLineInput from core/reject-history-filters.js
 * to parse LOT IDs / work order inputs. Tests cover input parsing,
 * limit enforcement, and query mode logic.
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { parseMultiLineInput } from '../src/core/reject-history-filters.js';


// ── parseMultiLineInput ────────────────────────────────────────────────────

test('parseMultiLineInput returns empty array for empty string', () => {
  assert.deepEqual(parseMultiLineInput(''), []);
});

test('parseMultiLineInput returns empty array for null', () => {
  assert.deepEqual(parseMultiLineInput(null), []);
});

test('parseMultiLineInput splits on newlines', () => {
  const result = parseMultiLineInput('GA001\nGA002\nGA003');
  assert.deepEqual(result, ['GA001', 'GA002', 'GA003']);
});

test('parseMultiLineInput splits on commas', () => {
  const result = parseMultiLineInput('GA001,GA002,GA003');
  assert.deepEqual(result, ['GA001', 'GA002', 'GA003']);
});

test('parseMultiLineInput splits on mixed newlines and commas', () => {
  const result = parseMultiLineInput('GA001\nGA002,GA003');
  assert.deepEqual(result, ['GA001', 'GA002', 'GA003']);
});

test('parseMultiLineInput trims whitespace from tokens', () => {
  const result = parseMultiLineInput(' GA001 ,  GA002 ');
  assert.deepEqual(result, ['GA001', 'GA002']);
});

test('parseMultiLineInput deduplicates tokens', () => {
  const result = parseMultiLineInput('GA001\nGA001\nGA002');
  assert.deepEqual(result, ['GA001', 'GA002']);
});

test('parseMultiLineInput filters empty tokens', () => {
  const result = parseMultiLineInput('GA001,,\n\nGA002');
  assert.deepEqual(result, ['GA001', 'GA002']);
});

test('parseMultiLineInput replaces * wildcard with %', () => {
  const result = parseMultiLineInput('GA001*');
  assert.deepEqual(result, ['GA001%']);
});


// ── Input limit enforcement ────────────────────────────────────────────────

const FORWARD_INPUT_LIMIT = 200;
const REVERSE_INPUT_LIMIT = 50;

function isOverLimit(tokens, mode) {
  const limit = mode === 'reverse' ? REVERSE_INPUT_LIMIT : FORWARD_INPUT_LIMIT;
  return tokens.length > limit;
}

test('isOverLimit returns false for small forward input', () => {
  const tokens = Array.from({ length: 10 }, (_, i) => `GA${i}`);
  assert.equal(isOverLimit(tokens, 'forward'), false);
});

test('isOverLimit returns true when forward exceeds 200', () => {
  const tokens = Array.from({ length: 201 }, (_, i) => `GA${i}`);
  assert.equal(isOverLimit(tokens, 'forward'), true);
});

test('isOverLimit returns true when reverse exceeds 50', () => {
  const tokens = Array.from({ length: 51 }, (_, i) => `LOT${i}`);
  assert.equal(isOverLimit(tokens, 'reverse'), true);
});

test('isOverLimit forward limit is 200', () => {
  const tokens = Array.from({ length: 200 }, (_, i) => `GA${i}`);
  assert.equal(isOverLimit(tokens, 'forward'), false);
  const oneMore = [...tokens, 'GA200'];
  assert.equal(isOverLimit(oneMore, 'forward'), true);
});


// ── Query mode API mapping ─────────────────────────────────────────────────

function queryModeForApi(mode, forwardInputType) {
  if (mode === 'reverse') return 'material_lot';
  return forwardInputType; // 'lot' or 'workorder'
}

test('queryModeForApi returns "material_lot" for reverse mode', () => {
  assert.equal(queryModeForApi('reverse', 'lot'), 'material_lot');
});

test('queryModeForApi returns "lot" for forward+lot mode', () => {
  assert.equal(queryModeForApi('forward', 'lot'), 'lot');
});

test('queryModeForApi returns "workorder" for forward+workorder mode', () => {
  assert.equal(queryModeForApi('forward', 'workorder'), 'workorder');
});
