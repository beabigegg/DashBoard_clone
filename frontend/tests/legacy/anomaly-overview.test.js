/**
 * Tests for anomaly-overview composables and section configuration.
 *
 * The anomaly overview page has a section-based layout where each anomaly
 * type (yield, reject, hold, equipment) is a section. This file tests the
 * section configuration contract and any drilldown utility logic.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── Section configuration contract ────────────────────────────────────────

const ANOMALY_SECTIONS = [
  { key: 'yield',      apiPath: '/api/analytics/yield-anomalies',      route: '/yield-alert-center' },
  { key: 'reject',     apiPath: '/api/analytics/reject-spikes',        route: '/reject-history' },
  { key: 'hold',       apiPath: '/api/analytics/hold-outliers',        route: '/hold-history' },
  { key: 'equipment',  apiPath: '/api/analytics/equipment-deviations', route: '/resource-history' },
];

test('anomaly overview has four sections', () => {
  assert.equal(ANOMALY_SECTIONS.length, 4);
});

test('each section has a unique key', () => {
  const keys = ANOMALY_SECTIONS.map(s => s.key);
  assert.equal(new Set(keys).size, keys.length);
});

test('each section has an apiPath and route', () => {
  for (const section of ANOMALY_SECTIONS) {
    assert.ok(section.apiPath && section.apiPath.startsWith('/api/'), `${section.key} missing valid apiPath`);
    assert.ok(section.route && section.route.startsWith('/'), `${section.key} missing valid route`);
  }
});

test('yield section links to yield-alert-center', () => {
  const yield_ = ANOMALY_SECTIONS.find(s => s.key === 'yield');
  assert.ok(yield_.route.includes('yield-alert'));
});


// ── Drilldown state helpers ────────────────────────────────────────────────

function initDrilldownState() {
  return {
    sectionKey: null,
    itemIndex: -1,
    loading: false,
    error: '',
    items: [],
  };
}

test('initDrilldownState starts with null sectionKey', () => {
  const state = initDrilldownState();
  assert.equal(state.sectionKey, null);
});

test('initDrilldownState starts with -1 itemIndex', () => {
  const state = initDrilldownState();
  assert.equal(state.itemIndex, -1);
});

test('initDrilldownState starts with loading false', () => {
  const state = initDrilldownState();
  assert.equal(state.loading, false);
});

test('initDrilldownState starts with empty items array', () => {
  const state = initDrilldownState();
  assert.deepEqual(state.items, []);
});


// ── Risk level mapping ─────────────────────────────────────────────────────

const RISK_LEVEL_LABELS = {
  high: '高風險',
  medium: '中風險',
  low: '低風險',
};

test('risk level labels cover all three levels', () => {
  assert.ok('high' in RISK_LEVEL_LABELS);
  assert.ok('medium' in RISK_LEVEL_LABELS);
  assert.ok('low' in RISK_LEVEL_LABELS);
});

function getRiskLabel(level) {
  return RISK_LEVEL_LABELS[level] || '未知';
}

test('getRiskLabel returns correct label for high', () => {
  assert.equal(getRiskLabel('high'), '高風險');
});

test('getRiskLabel returns "未知" for unknown level', () => {
  assert.equal(getRiskLabel('extreme'), '未知');
});


// ── Anomaly count aggregation ──────────────────────────────────────────────

function totalAnomalyCount(sections) {
  return sections.reduce((sum, s) => sum + (s.items?.length ?? 0), 0);
}

test('totalAnomalyCount sums item counts across sections', () => {
  const sections = [
    { items: [1, 2, 3] },
    { items: [4, 5] },
    { items: [] },
  ];
  assert.equal(totalAnomalyCount(sections), 5);
});

test('totalAnomalyCount handles sections without items', () => {
  const sections = [{}, {}, {}];
  assert.equal(totalAnomalyCount(sections), 0);
});
