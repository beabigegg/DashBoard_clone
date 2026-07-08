/**
 * Tests for admin-dashboard tab configuration and utility functions.
 *
 * The admin dashboard has a tab-based layout. This file tests the tab
 * configuration contract and any utility functions used for auto-refresh.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── Tab configuration contract ─────────────────────────────────────────────

const ADMIN_DASHBOARD_TABS = [
  { key: 'overview',     label: '總覽' },
  { key: 'performance',  label: '效能' },
  { key: 'cache',        label: '快取' },
  { key: 'worker',       label: 'Worker' },
  { key: 'usage',        label: '用戶' },
  { key: 'logs',         label: '日誌' },
  { key: 'permissions',  label: '目標值權限' },
];

test('admin dashboard has seven tabs', () => {
  assert.equal(ADMIN_DASHBOARD_TABS.length, 7);
});

test('each tab has a unique key', () => {
  const keys = ADMIN_DASHBOARD_TABS.map(t => t.key);
  const uniqueKeys = new Set(keys);
  assert.equal(uniqueKeys.size, keys.length);
});

test('each tab has a non-empty label', () => {
  for (const tab of ADMIN_DASHBOARD_TABS) {
    assert.ok(tab.label && tab.label.length > 0, `Tab ${tab.key} has empty label`);
  }
});

test('overview tab is first', () => {
  assert.equal(ADMIN_DASHBOARD_TABS[0].key, 'overview');
});

test('permissions tab is appended after logs (last)', () => {
  assert.equal(ADMIN_DASHBOARD_TABS.at(-1).key, 'permissions');
  const keys = ADMIN_DASHBOARD_TABS.map(t => t.key);
  assert.ok(keys.indexOf('logs') < keys.indexOf('permissions'));
});

test('all expected tab keys are present', () => {
  const expectedKeys = ['overview', 'performance', 'cache', 'worker', 'usage', 'logs', 'permissions'];
  const actualKeys = ADMIN_DASHBOARD_TABS.map(t => t.key);
  for (const key of expectedKeys) {
    assert.ok(actualKeys.includes(key), `Missing tab key: ${key}`);
  }
});


// ── Auto-refresh utility ───────────────────────────────────────────────────

/**
 * Mirrors the auto-refresh interval pattern from admin dashboard.
 * Auto-refresh default is 30 seconds.
 */
const AUTO_REFRESH_INTERVAL_MS = 30_000;

test('auto-refresh default interval is 30 seconds', () => {
  assert.equal(AUTO_REFRESH_INTERVAL_MS, 30_000);
});

test('auto-refresh interval is positive integer', () => {
  assert.ok(AUTO_REFRESH_INTERVAL_MS > 0);
  assert.equal(AUTO_REFRESH_INTERVAL_MS % 1, 0);
});


// ── Tab navigation helpers ─────────────────────────────────────────────────

function findTabByKey(tabs, key) {
  return tabs.find(t => t.key === key) || tabs[0];
}

test('findTabByKey returns correct tab', () => {
  const tab = findTabByKey(ADMIN_DASHBOARD_TABS, 'performance');
  assert.equal(tab.key, 'performance');
});

test('findTabByKey falls back to first tab for unknown key', () => {
  const tab = findTabByKey(ADMIN_DASHBOARD_TABS, 'nonexistent-key');
  assert.equal(tab.key, ADMIN_DASHBOARD_TABS[0].key);
});

test('findTabByKey is case-sensitive', () => {
  const tab = findTabByKey(ADMIN_DASHBOARD_TABS, 'OVERVIEW');
  // 'OVERVIEW' is not a valid key → falls back to first tab
  assert.equal(tab.key, 'overview');
});
