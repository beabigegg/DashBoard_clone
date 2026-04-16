/**
 * Tests for mid-section-defect composable logic.
 *
 * Covers buildMachineChartFromAttribution and session cache helpers
 * extracted from mid-section-defect/App.vue.
 */
import test from 'node:test';
import assert from 'node:assert/strict';


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
