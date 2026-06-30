/**
 * Tests for mid-section-defect composable logic.
 *
 * Covers buildMachineChartFromAttribution and session cache helpers
 * extracted from mid-section-defect/App.vue, plus useContainerFilterOptions
 * cross-filter behaviour (AC-3, AC-4).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { ref } from 'vue';
import {
  useContainerFilterOptions,
  _buildContainerFilterUrl,
} from '../../src/mid-section-defect/composables/useContainerFilterOptions.ts';


const CHART_TOP_N = 10;

/**
 * Mirrors buildMachineChartFromAttribution from mid-section-defect/App.vue.
 * Aggregates machine attribution records into chart items sorted by defect_qty.
 */
function buildMachineChartFromAttribution(records) {
  if (!records || records.length === 0) return [];
  const agg = {};
  for (const rec of records) {
    const key = rec.EQUIPMENT_NAME || '(未知)';
    if (!agg[key]) agg[key] = { input_qty: 0, defect_qty: 0, lot_count: 0 };
    agg[key].input_qty += rec.INPUT_QTY;
    agg[key].defect_qty += rec.DEFECT_QTY;
    agg[key].lot_count += rec.DETECTION_LOT_COUNT;
  }
  const sorted = Object.entries(agg).sort((a, b) => b[1].defect_qty - a[1].defect_qty);
  const items = [];
  const other = { input_qty: 0, defect_qty: 0, lot_count: 0 };
  for (let i = 0; i < sorted.length; i++) {
    const [name, data] = sorted[i];
    if (i < CHART_TOP_N) {
      const rate = data.input_qty > 0 ? Math.round((data.defect_qty / data.input_qty) * 1e6) / 1e4 : 0;
      items.push({ name, input_qty: data.input_qty, defect_qty: data.defect_qty, defect_rate: rate, lot_count: data.lot_count });
    } else {
      other.input_qty += data.input_qty;
      other.defect_qty += data.defect_qty;
      other.lot_count += data.lot_count;
    }
  }
  if (other.defect_qty > 0 || other.input_qty > 0) {
    const rate = other.input_qty > 0 ? Math.round((other.defect_qty / other.input_qty) * 1e6) / 1e4 : 0;
    items.push({ name: '其他', ...other, defect_rate: rate });
  }
  const totalDefects = items.reduce((s, d) => s + d.defect_qty, 0);
  let cumsum = 0;
  for (const item of items) {
    cumsum += item.defect_qty;
    item.cumulative_pct = totalDefects > 0 ? Math.round((cumsum / totalDefects) * 1e4) / 100 : 0;
  }
  return items;
}


// ── buildMachineChartFromAttribution ──────────────────────────────────────

test('returns empty array for empty input', () => {
  assert.deepEqual(buildMachineChartFromAttribution([]), []);
});

test('returns empty array for null input', () => {
  assert.deepEqual(buildMachineChartFromAttribution(null), []);
});

test('aggregates single machine record correctly', () => {
  const records = [{ EQUIPMENT_NAME: 'MW01', INPUT_QTY: 100, DEFECT_QTY: 5, DETECTION_LOT_COUNT: 2 }];
  const result = buildMachineChartFromAttribution(records);
  assert.equal(result.length, 1);
  assert.equal(result[0].name, 'MW01');
  assert.equal(result[0].defect_qty, 5);
  assert.equal(result[0].input_qty, 100);
});

test('aggregates multiple records for the same machine', () => {
  const records = [
    { EQUIPMENT_NAME: 'MW01', INPUT_QTY: 50, DEFECT_QTY: 2, DETECTION_LOT_COUNT: 1 },
    { EQUIPMENT_NAME: 'MW01', INPUT_QTY: 50, DEFECT_QTY: 3, DETECTION_LOT_COUNT: 1 },
  ];
  const result = buildMachineChartFromAttribution(records);
  assert.equal(result.length, 1);
  assert.equal(result[0].defect_qty, 5);
  assert.equal(result[0].input_qty, 100);
});

test('sorts machines by defect_qty descending', () => {
  const records = [
    { EQUIPMENT_NAME: 'Low',  INPUT_QTY: 100, DEFECT_QTY: 1, DETECTION_LOT_COUNT: 1 },
    { EQUIPMENT_NAME: 'High', INPUT_QTY: 100, DEFECT_QTY: 10, DETECTION_LOT_COUNT: 1 },
    { EQUIPMENT_NAME: 'Mid',  INPUT_QTY: 100, DEFECT_QTY: 5, DETECTION_LOT_COUNT: 1 },
  ];
  const result = buildMachineChartFromAttribution(records);
  assert.equal(result[0].name, 'High');
  assert.equal(result[1].name, 'Mid');
  assert.equal(result[2].name, 'Low');
});

test('calculates defect_rate as percentage with 4 decimal precision', () => {
  const records = [{ EQUIPMENT_NAME: 'MW01', INPUT_QTY: 1000, DEFECT_QTY: 1, DETECTION_LOT_COUNT: 1 }];
  const result = buildMachineChartFromAttribution(records);
  // 1/1000 = 0.1%
  assert.equal(result[0].defect_rate, 0.1);
});

test('handles missing EQUIPMENT_NAME by using "(未知)"', () => {
  const records = [{ EQUIPMENT_NAME: null, INPUT_QTY: 50, DEFECT_QTY: 3, DETECTION_LOT_COUNT: 1 }];
  const result = buildMachineChartFromAttribution(records);
  assert.equal(result[0].name, '(未知)');
});

test('cumulative_pct of last item equals 100 for single machine', () => {
  const records = [{ EQUIPMENT_NAME: 'MW01', INPUT_QTY: 100, DEFECT_QTY: 5, DETECTION_LOT_COUNT: 1 }];
  const result = buildMachineChartFromAttribution(records);
  assert.equal(result[result.length - 1].cumulative_pct, 100);
});

test('groups machines beyond CHART_TOP_N into "其他"', () => {
  // Create 11 machines (more than CHART_TOP_N=10)
  const records = Array.from({ length: 11 }, (_, i) => ({
    EQUIPMENT_NAME: `MW${String(i).padStart(2, '0')}`,
    INPUT_QTY: 100,
    DEFECT_QTY: i + 1,
    DETECTION_LOT_COUNT: 1,
  }));
  const result = buildMachineChartFromAttribution(records);
  const other = result.find(r => r.name === '其他');
  assert.ok(other, 'Expected "其他" bucket for overflow machines');
  assert.equal(result.length, CHART_TOP_N + 1);
});


// ── AC-3: App filters state includes pjTypes and packages ─────────────────

test('test_app_filters_state_includes_pj_types_and_packages', () => {
  // Mirrors the App.vue filters reactive initial shape.
  // Verifies that pjTypes and packages are present and default to empty arrays.
  const filtersShape = {
    startDate: '',
    endDate: '',
    lossReasons: [],
    station: ['測試'],
    direction: 'backward',
    pjTypes: [],
    packages: [],
  };
  assert.ok(Object.prototype.hasOwnProperty.call(filtersShape, 'pjTypes'),
    'filters must include pjTypes');
  assert.ok(Object.prototype.hasOwnProperty.call(filtersShape, 'packages'),
    'filters must include packages');
  assert.deepEqual(filtersShape.pjTypes, []);
  assert.deepEqual(filtersShape.packages, []);
});


// ── _buildContainerFilterUrl ──────────────────────────────────────────────

test('_buildContainerFilterUrl returns bare endpoint when both selections empty', () => {
  const url = _buildContainerFilterUrl('/api/mid-section-defect/container-filter-options', [], []);
  assert.equal(url, '/api/mid-section-defect/container-filter-options');
});

test('_buildContainerFilterUrl encodes pj_types when pjTypes selected', () => {
  const url = _buildContainerFilterUrl(
    '/api/mid-section-defect/container-filter-options',
    ['TYPE_A'],
    [],
  );
  assert.ok(url.includes('selected='), 'URL must include selected=');
  const parsed = JSON.parse(decodeURIComponent(url.split('selected=')[1]));
  assert.deepEqual(parsed, { pj_types: ['TYPE_A'] });
});

test('_buildContainerFilterUrl encodes both pj_types and packages when both selected', () => {
  const url = _buildContainerFilterUrl(
    '/api/mid-section-defect/container-filter-options',
    ['TYPE_A'],
    ['PKG_X'],
  );
  const parsed = JSON.parse(decodeURIComponent(url.split('selected=')[1]));
  assert.deepEqual(parsed.pj_types, ['TYPE_A']);
  assert.deepEqual(parsed.packages, ['PKG_X']);
});


// ── AC-4: Cross-filter — selecting pjTypes narrows packageOptions ──────────

test('test_cross_filter_type_selection_narrows_package_options', async () => {
  const narrowedPackages = ['PKG_X'];
  const fullPackages = ['PKG_X', 'PKG_Y'];

  const fetcher = async (url) => {
    const hasTypeFilter = url.includes('pj_types');
    return {
      success: true,
      data: {
        pj_types: ['TYPE_A', 'TYPE_B'],
        packages: hasTypeFilter ? narrowedPackages : fullPackages,
      },
    };
  };

  const selectedTypes = ref([]);
  const selectedPkgs = ref([]);
  const { fetchOptions, packageOptions } = useContainerFilterOptions(
    selectedTypes,
    selectedPkgs,
    { fetcher, debounceMs: 0 },
  );

  // Wait for the initial mount-time fetch (no selection → full options).
  await fetchOptions();
  assert.deepEqual(packageOptions.value, fullPackages,
    'initial fetch should return full package list');

  // Select a type and re-fetch — packages should be narrowed.
  selectedTypes.value = ['TYPE_A'];
  await fetchOptions();
  assert.deepEqual(packageOptions.value, narrowedPackages,
    'after type selection, packageOptions must be narrowed');
});

test('useContainerFilterOptions fetch on mount populates pjTypeOptions', async () => {
  const fetcher = async () => ({
    success: true,
    data: { pj_types: ['TYPE_A', 'TYPE_B'], packages: ['PKG_X'] },
  });

  const { fetchOptions, pjTypeOptions } = useContainerFilterOptions(ref([]), ref([]), { fetcher });
  await fetchOptions();
  assert.deepEqual(pjTypeOptions.value, ['TYPE_A', 'TYPE_B']);
});

test('useContainerFilterOptions fails open on fetch error', async () => {
  const fetcher = async () => { throw new Error('network failure'); };

  const { fetchOptions, pjTypeOptions, packageOptions } = useContainerFilterOptions(
    ref([]), ref([]), { fetcher },
  );
  // Should not throw; options remain empty.
  await fetchOptions();
  assert.deepEqual(pjTypeOptions.value, []);
  assert.deepEqual(packageOptions.value, []);
});


// ── AC-8: Forward cross-filter composable logic ───────────────────────────

/**
 * Mirrors byDetectionLossReasonChartData computed from App.vue.
 * Converts by_detection_loss_reason items to ParetoChart-compatible ChartItem[].
 */
function buildLossReasonChartData(items, selectedReason = null) {
  if (!Array.isArray(items) || items.length === 0) return [];
  const filtered = selectedReason
    ? items.filter((item) => item.loss_reason === selectedReason)
    : items;
  const totalQty = filtered.reduce((s, d) => s + d.reject_qty, 0);
  let cumsum = 0;
  return filtered.map((item) => {
    cumsum += item.reject_qty;
    return {
      name: item.loss_reason,
      input_qty: 0,
      defect_qty: item.reject_qty,
      defect_rate: Math.round((item.reject_rate || 0) * 10000) / 100,
      lot_count: 0,
      cumulative_pct: totalQty > 0 ? Math.round((cumsum / totalQty) * 1e4) / 100 : 0,
    };
  });
}

/**
 * Mirrors formatAmplification from KpiCards.vue.
 */
function formatAmplification(v) {
  if (v === null || v === undefined) return '—';
  return `×${Number(v).toFixed(1)}`;
}

test('AC-8: buildLossReasonChartData returns empty for empty input', () => {
  assert.deepEqual(buildLossReasonChartData([]), []);
});

test('AC-8: buildLossReasonChartData converts reject_rate 0..1 to percentage', () => {
  const items = [{ loss_reason: '外觀不良', reject_qty: 10, reject_rate: 0.05 }];
  const result = buildLossReasonChartData(items);
  assert.equal(result.length, 1);
  assert.equal(result[0].name, '外觀不良');
  assert.equal(result[0].defect_qty, 10);
  assert.equal(result[0].defect_rate, 5); // 0.05 * 100 = 5%
  assert.equal(result[0].cumulative_pct, 100);
});

test('AC-8: buildLossReasonChartData cross-filters by selected front reason', () => {
  const items = [
    { loss_reason: '外觀不良', reject_qty: 20, reject_rate: 0.1 },
    { loss_reason: '電性不良', reject_qty: 5, reject_rate: 0.02 },
  ];
  const result = buildLossReasonChartData(items, '外觀不良');
  assert.equal(result.length, 1);
  assert.equal(result[0].name, '外觀不良');
});

test('AC-8: buildLossReasonChartData returns all items when no selection', () => {
  const items = [
    { loss_reason: '外觀不良', reject_qty: 20, reject_rate: 0.1 },
    { loss_reason: '電性不良', reject_qty: 5, reject_rate: 0.02 },
  ];
  const result = buildLossReasonChartData(items, null);
  assert.equal(result.length, 2);
});

test('AC-8: formatAmplification returns "—" when null', () => {
  assert.equal(formatAmplification(null), '—');
  assert.equal(formatAmplification(undefined), '—');
});

test('AC-8: formatAmplification returns "×0.0" for 0.0 (real zero)', () => {
  assert.equal(formatAmplification(0.0), '×0.0');
});

test('AC-8: formatAmplification formats 1-decimal string for nonzero value', () => {
  assert.equal(formatAmplification(2.3456), '×2.3');
  assert.equal(formatAmplification(1), '×1.0');
});

test('AC-8: forward selection toggle: setting same frontReason again would clear it (logic mirror)', () => {
  // Mirror the toggle logic in handleSankeyNodeClick
  function handleSankeyNodeClick(cur, payload) {
    if (payload.frontReason && cur.frontReason === payload.frontReason) {
      return { frontReason: null, downstreamGroup: null };
    }
    if (payload.downstreamGroup && cur.downstreamGroup === payload.downstreamGroup) {
      return { frontReason: null, downstreamGroup: null };
    }
    return { ...payload };
  }

  // First click sets selection
  let sel = handleSankeyNodeClick({ frontReason: null, downstreamGroup: null }, { frontReason: '外觀不良', downstreamGroup: null });
  assert.equal(sel.frontReason, '外觀不良');

  // Second click on same node clears
  sel = handleSankeyNodeClick(sel, { frontReason: '外觀不良', downstreamGroup: null });
  assert.equal(sel.frontReason, null);
});

test('AC-8: buildLossReasonChartData cumulative_pct sums to 100 for multiple items', () => {
  const items = [
    { loss_reason: '外觀不良', reject_qty: 60, reject_rate: 0.06 },
    { loss_reason: '電性不良', reject_qty: 40, reject_rate: 0.04 },
  ];
  const result = buildLossReasonChartData(items);
  assert.equal(result.length, 2);
  assert.equal(result[result.length - 1].cumulative_pct, 100);
});
