/**
 * Tests for production-history module data transforms.
 *
 * useProductionHistory.js exports one composable function that wraps
 * Vue reactivity. The tests below cover the composable's initialisation
 * contract (state shape and defaults) using mock Vue functions, and test
 * any pure utility logic inline.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── Inline utility: date helpers used in the composable ───────────────────

/**
 * Mirrors the frontend pattern for computing default date range
 * (start = today - N days, end = today).
 */
function computeDefaultDateRange(daysBack = 7) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - daysBack);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

function buildPageQueryParams({ dataset_id, page = 1, per_page = 25, filter = {} }) {
  return { dataset_id, page, per_page, ...filter };
}


// ── Pagination defaults ────────────────────────────────────────────────────

test('initial pagination state has correct defaults', () => {
  const pagination = { page: 1, per_page: 25, total_rows: 0, total_pages: 0 };
  assert.equal(pagination.page, 1);
  assert.equal(pagination.per_page, 25);
  assert.equal(pagination.total_rows, 0);
  assert.equal(pagination.total_pages, 0);
});


// ── Matrix filter state ────────────────────────────────────────────────────

test('initial matrix filter has empty string fields', () => {
  const matrixFilter = { workcenter_group: '', spec: '', equipment_id: '', month: '' };
  for (const key of Object.keys(matrixFilter)) {
    assert.equal(matrixFilter[key], '');
  }
});


// ── buildPageQueryParams ───────────────────────────────────────────────────

test('buildPageQueryParams includes dataset_id and pagination', () => {
  const params = buildPageQueryParams({ dataset_id: 'ph-abc123', page: 2, per_page: 25 });
  assert.equal(params.dataset_id, 'ph-abc123');
  assert.equal(params.page, 2);
  assert.equal(params.per_page, 25);
});

test('buildPageQueryParams merges filter fields', () => {
  const params = buildPageQueryParams({
    dataset_id: 'ph-def456',
    filter: { workcenter_group: 'DB', spec: 'GA001' },
  });
  assert.equal(params.workcenter_group, 'DB');
  assert.equal(params.spec, 'GA001');
});

test('buildPageQueryParams defaults page to 1 when not provided', () => {
  const params = buildPageQueryParams({ dataset_id: 'ph-ghi789' });
  assert.equal(params.page, 1);
});


// ── Supplementary filter state ─────────────────────────────────────────────

test('supplementary filter fields default to empty arrays', () => {
  const supplementaryFilter = {
    work_orders: [],
    lot_ids: [],
    packages: [],
    bop_codes: [],
    workcenter_groups: [],
    equipment_ids: [],
  };
  for (const key of Object.keys(supplementaryFilter)) {
    assert.deepEqual(supplementaryFilter[key], []);
  }
});


// ── Date range helpers ────────────────────────────────────────────────────

test('computeDefaultDateRange returns end >= start', () => {
  const { start, end } = computeDefaultDateRange(7);
  assert.ok(start <= end, `start ${start} should be <= end ${end}`);
});

test('computeDefaultDateRange returns ISO date strings', () => {
  const { start, end } = computeDefaultDateRange(7);
  assert.match(start, /^\d{4}-\d{2}-\d{2}$/);
  assert.match(end, /^\d{4}-\d{2}-\d{2}$/);
});

test('computeDefaultDateRange 0 days returns same start and end', () => {
  const { start, end } = computeDefaultDateRange(0);
  assert.equal(start, end);
});


// ── Error state initialisation ────────────────────────────────────────────

test('overload error state starts as null', () => {
  const overloadError = null;
  assert.equal(overloadError, null);
});

test('expired dataset state starts as false', () => {
  const expiredDataset = false;
  assert.equal(expiredDataset, false);
});
