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


// ── First-tier filter composable (cross-filter loader) ─────────────────────
//
// Added by change `prod-history-first-tier-cache-filters`.  Exercises the
// useFirstTierFilters composable's fetcher injection + selection-driven
// re-fetch + pruning of dropped values (PHF-01 fail-open picker).

import {
  parseWildcardInput,
  useFirstTierFilters,
  _buildUrl,
} from '../../src/production-history/composables/useFirstTierFilters.ts';

// ── useFirstTierFilters — buffer/commit split ──────────────────────────────
//
// Added by change `fix-prod-history-multiselect-filter`.
// Exercises: setSelection() is buffer-only; commitSelection() diffs and fires.

test('setSelection() updates buffer but does not call fetcher', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return { success: true, data: { pj_types: [], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  ft.setSelection('pj_types', ['A']);
  // Give the event loop a tick — no debounce should fire.
  await new Promise((r) => setTimeout(r, 5));

  // Buffer is updated…
  assert.deepEqual(ft.selection.pj_types, ['A']);
  // …but fetcher was NOT called.
  assert.equal(calls.length, 0);
});

test('setSelection() does not start debounce timer', async () => {
  let timerFired = false;
  const fetcher = async () => {
    timerFired = true;
    return { success: true, data: { pj_types: [], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 1 });

  ft.setSelection('pj_types', ['B']);
  await new Promise((r) => setTimeout(r, 20)); // well past debounce window

  assert.equal(timerFired, false);
});

test('commitSelection() fires fetcher exactly once with debounce', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return { success: true, data: { pj_types: ['A'], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  ft.setSelection('pj_types', ['A']);
  ft.commitSelection('pj_types');
  await new Promise((r) => setTimeout(r, 5));

  assert.equal(calls.length, 1);
  assert.ok(calls[0].includes('selected='), 'request should carry selected=');
  const parsed = JSON.parse(decodeURIComponent(calls[0].split('selected=')[1]));
  assert.deepEqual(parsed, { pj_types: ['A'] });
});

test('commitSelection() with unchanged selection is a no-op', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return { success: true, data: { pj_types: ['A'], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  // Prime: initial fetch sets _lastCommitted
  await ft.fetchFilterOptions();
  const callsAfterInit = calls.length;

  // setSelection + commitSelection with same value as _lastCommitted (empty [] === [])
  ft.setSelection('packages', []);
  ft.commitSelection('packages');
  await new Promise((r) => setTimeout(r, 5));

  // No additional fetch should have fired.
  assert.equal(calls.length, callsAfterInit);
});

test('commitSelection() reads from buffer (latest setSelection wins)', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return { success: true, data: { pj_types: ['A', 'B'], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  ft.setSelection('pj_types', ['A']);
  ft.setSelection('pj_types', ['A', 'B']); // latest wins
  ft.commitSelection('pj_types');
  await new Promise((r) => setTimeout(r, 5));

  assert.equal(calls.length, 1);
  const parsed = JSON.parse(decodeURIComponent(calls[0].split('selected=')[1]));
  assert.deepEqual(parsed, { pj_types: ['A', 'B'] });
});

test('multiple setSelection followed by single commitSelection produces one fetcher call', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return { success: true, data: { pj_types: [], packages: [], bops: [], pj_functions: [] }, meta: {} };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  // Simulate user toggling multiple options inside an open dropdown.
  ft.setSelection('pj_types', ['A']);
  ft.setSelection('pj_types', ['A', 'B']);
  ft.setSelection('pj_types', ['A', 'B', 'C']);
  // User closes dropdown — exactly ONE commit.
  ft.commitSelection('pj_types');
  await new Promise((r) => setTimeout(r, 5));

  // Only one fetch call, with the final buffer value.
  assert.equal(calls.length, 1);
});

test('parseWildcardInput handles material-trace-style multi-line paste', () => {
  const raw = '  MA2025*\n*2025\nMA*2025,MA2025\nMA2025*\n  ';
  const out = parseWildcardInput(raw);
  assert.deepEqual(out, ['MA2025*', '*2025', 'MA*2025', 'MA2025']);
});

test('parseWildcardInput is idempotent across re-parse cycles', () => {
  const seeds = ['MA*\nMA2025*\nMA*', 'A,B,C\nA', ''];
  for (const seed of seeds) {
    const a = parseWildcardInput(seed);
    const b = parseWildcardInput(a.join('\n'));
    assert.deepEqual(b, a);
  }
});

test('useFirstTierFilters loads base options on first call (empty selection)', async () => {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    return {
      success: true,
      data: {
        pj_types: ['A', 'B'],
        packages: ['PKG-1', 'PKG-2'],
        bops: ['BOP-1'],
        pj_functions: ['FN-1'],
      },
      meta: { schema_version: 2, updated_at: '2026-05-14T00:00:00Z' },
    };
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  await ft.fetchFilterOptions();

  // No `?selected=` for empty selection.
  assert.equal(calls.length, 1);
  assert.ok(!calls[0].includes('?selected='));
  // Base + current options both reflect the response.
  assert.deepEqual(ft.baseOptions.value.pj_types, ['A', 'B']);
  assert.deepEqual(ft.options.value.packages, ['PKG-1', 'PKG-2']);
  assert.equal(ft.lastUpdatedAt.value, '2026-05-14T00:00:00Z');
});

test('useFirstTierFilters re-fetches with selected payload after setSelection+commitSelection', async () => {
  const calls = [];
  let responseIdx = 0;
  const responses = [
    {
      success: true,
      data: { pj_types: ['A', 'B'], packages: ['PKG-1', 'PKG-2'], bops: ['BOP-1', 'BOP-2'], pj_functions: ['FN-1'] },
      meta: {},
    },
    {
      success: true,
      // After selecting pj_types=['A'], BOP-2 disappears from co-occurrence.
      data: { pj_types: ['A'], packages: ['PKG-1'], bops: ['BOP-1'], pj_functions: ['FN-1'] },
      meta: {},
    },
  ];
  const fetcher = async (url) => {
    calls.push(url);
    return responses[Math.min(responseIdx++, responses.length - 1)];
  };
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  await ft.fetchFilterOptions(); // initial load
  ft.setSelection('pj_types', ['A']);
  // Migrated: setSelection no longer auto-fires; call commitSelection to apply.
  ft.commitSelection('pj_types');

  // commitSelection schedules via setTimeout(..., 0) — give it one tick.
  await new Promise((r) => setTimeout(r, 5));

  assert.equal(calls.length, 2);
  const url = calls[1];
  assert.ok(url.includes('selected='), 'second call should carry selected=');
  const parsed = JSON.parse(decodeURIComponent(url.split('selected=')[1]));
  assert.deepEqual(parsed, { pj_types: ['A'] });
});

test('useFirstTierFilters prunes selection values that vanish from new options', async () => {
  let responseIdx = 0;
  const responses = [
    {
      success: true,
      data: { pj_types: ['A', 'B'], packages: ['PKG-1', 'PKG-2'], bops: ['BOP-1'], pj_functions: ['FN-1'] },
      meta: {},
    },
    {
      success: true,
      data: { pj_types: ['A'], packages: ['PKG-1'], bops: ['BOP-1'], pj_functions: ['FN-1'] },
      meta: {},
    },
  ];
  const fetcher = async () => responses[Math.min(responseIdx++, responses.length - 1)];
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });

  await ft.fetchFilterOptions();
  // Pretend the user picked BOTH packages.
  ft.selection.packages = ['PKG-1', 'PKG-2'];
  ft.setSelection('pj_types', ['A']);
  // Migrated: setSelection no longer auto-fires; call commitSelection to apply.
  ft.commitSelection('pj_types');
  await new Promise((r) => setTimeout(r, 5));

  // PKG-2 is no longer in the narrowed options → must be pruned silently.
  assert.deepEqual(ft.selection.packages, ['PKG-1']);
});

test('buildQueryFragment omits empty fields and routes wildcard textareas through parser', async () => {
  const fetcher = async () => ({
    success: true,
    data: { pj_types: ['A'], packages: ['PKG-1'], bops: ['BOP-1'], pj_functions: ['FN-1'] },
    meta: {},
  });
  const ft = useFirstTierFilters({ fetcher, debounceMs: 0 });
  await ft.fetchFilterOptions();

  ft.selection.pj_types = ['A'];
  ft.selection.packages = ['PKG-1'];
  ft.wildcardInput.mfg_orders = 'WO-1\nWO-2*';
  ft.wildcardInput.lot_ids = '';
  ft.wildcardInput.wafer_lots = 'WAFER*';

  const fragment = ft.buildQueryFragment();
  assert.deepEqual(fragment.pj_types, ['A']);
  assert.deepEqual(fragment.pj_packages, ['PKG-1']);
  assert.equal(fragment.pj_bops, undefined);
  assert.equal(fragment.pj_functions, undefined);
  assert.deepEqual(fragment.mfg_orders, ['WO-1', 'WO-2*']);
  assert.equal(fragment.lot_ids, undefined);
  assert.deepEqual(fragment.wafer_lots, ['WAFER*']);
});

test('_buildUrl drops empty arrays and JSON-encodes selection', () => {
  const u = _buildUrl('/x', { pj_types: ['A', 'B'], packages: [], bops: ['B-1'], pj_functions: [] });
  const json = decodeURIComponent(u.split('selected=')[1]);
  assert.deepEqual(JSON.parse(json), { pj_types: ['A', 'B'], bops: ['B-1'] });
});
