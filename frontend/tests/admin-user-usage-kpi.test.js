/**
 * Tests for admin-user-usage-kpi utility functions.
 *
 * Covers the formatDuration helper and date initialisation logic
 * from admin-user-usage-kpi/App.vue.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── formatDuration (mirrors App.vue implementation) ───────────────────────

function formatDuration(sec) {
  if (sec == null || sec === 0) return '-';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}


test('formatDuration returns "-" for null', () => {
  assert.equal(formatDuration(null), '-');
});

test('formatDuration returns "-" for 0', () => {
  assert.equal(formatDuration(0), '-');
});

test('formatDuration returns seconds for < 60s', () => {
  assert.equal(formatDuration(45), '45s');
  assert.equal(formatDuration(1), '1s');
});

test('formatDuration returns minutes for 60-3599s', () => {
  assert.equal(formatDuration(60), '1m');
  assert.equal(formatDuration(120), '2m');
  assert.equal(formatDuration(3599), `${Math.round(3599 / 60)}m`);
});

test('formatDuration returns hours for >= 3600s', () => {
  assert.equal(formatDuration(3600), '1.0h');
  assert.equal(formatDuration(7200), '2.0h');
  assert.equal(formatDuration(5400), '1.5h');
});

test('formatDuration rounds minutes correctly', () => {
  // 90s = 1.5 min → rounds to 2m
  assert.equal(formatDuration(90), '2m');
  // 89s rounds to 1m
  assert.equal(formatDuration(89), `${Math.round(89 / 60)}m`);
});


// ── Default date range initialisation ─────────────────────────────────────

function initDates(daysBack = 30) {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const start = new Date(now);
  start.setDate(start.getDate() - daysBack);
  return { startDate: start.toISOString().slice(0, 10), endDate: end };
}

test('initDates returns ISO date strings', () => {
  const { startDate, endDate } = initDates();
  assert.match(startDate, /^\d{4}-\d{2}-\d{2}$/);
  assert.match(endDate, /^\d{4}-\d{2}-\d{2}$/);
});

test('initDates endDate is today', () => {
  const { endDate } = initDates();
  const today = new Date().toISOString().slice(0, 10);
  assert.equal(endDate, today);
});

test('initDates startDate is 30 days before endDate', () => {
  const { startDate, endDate } = initDates(30);
  const end = new Date(endDate);
  const start = new Date(startDate);
  const diffDays = Math.round((end - start) / (1000 * 60 * 60 * 24));
  assert.equal(diffDays, 30);
});


// ── KPI data structure validation ─────────────────────────────────────────

function validateKpiShape(data) {
  if (!data || typeof data !== 'object') return false;
  const required = ['overview', 'dau_trend', 'duration_distribution'];
  return required.every(k => k in data);
}

test('validateKpiShape returns true for complete data', () => {
  const data = {
    overview: {},
    dau_trend: [],
    duration_distribution: [],
  };
  assert.equal(validateKpiShape(data), true);
});

test('validateKpiShape returns false for missing fields', () => {
  assert.equal(validateKpiShape({ overview: {} }), false);
});

test('validateKpiShape returns false for null', () => {
  assert.equal(validateKpiShape(null), false);
});
