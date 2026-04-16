import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildWipOverviewQueryParams,
  buildWipDetailQueryParams,
  splitHoldByType,
  prepareParetoData,
} from '../src/core/wip-derive.js';

test('buildWipOverviewQueryParams keeps only non-empty filters', () => {
  const params = buildWipOverviewQueryParams({
    workorder: [' WO-1 ', 'WO-2'],
    lotid: [],
    package: ['PKG-A'],
    type: 'QFN',
    firstname: ['WF-01'],
    waferdesc: 'SiC',
  });

  assert.deepEqual(params, {
    workorder: 'WO-1,WO-2',
    package: 'PKG-A',
    type: 'QFN',
    firstname: 'WF-01',
    waferdesc: 'SiC',
  });
});

test('buildWipOverviewQueryParams maps quality hold status filter', () => {
  const params = buildWipOverviewQueryParams({}, 'quality-hold');
  assert.deepEqual(params, {
    status: 'HOLD',
    hold_type: 'quality',
  });
});

test('buildWipDetailQueryParams uses page/page_size and shared filter mapper', () => {
  const params = buildWipDetailQueryParams({
    page: 2,
    pageSize: 100,
    filters: {
      workorder: 'WO',
      lotid: 'LOT',
      package: '',
      type: 'TSOP',
    },
    statusFilter: 'run',
  });

  assert.deepEqual(params, {
    page: 2,
    page_size: 100,
    workorder: 'WO',
    lotid: 'LOT',
    type: 'TSOP',
    status: 'RUN',
  });
});

test('splitHoldByType partitions quality/non-quality correctly', () => {
  const grouped = splitHoldByType({
    items: [
      { reason: 'Q1', holdType: 'quality' },
      { reason: 'NQ1', holdType: 'non-quality' },
      { reason: 'NQ2' },
    ],
  });

  assert.equal(grouped.quality.length, 1);
  assert.equal(grouped.nonQuality.length, 2);
});

test('prepareParetoData sorts by qty and builds cumulative percentages', () => {
  const data = prepareParetoData([
    { reason: 'B', qty: 20, lots: 1 },
    { reason: 'A', qty: 80, lots: 2 },
  ]);

  assert.deepEqual(data.reasons, ['A', 'B']);
  assert.deepEqual(data.qtys, [80, 20]);
  assert.deepEqual(data.cumulative, [80, 100]);
  assert.equal(data.totalQty, 100);
});
