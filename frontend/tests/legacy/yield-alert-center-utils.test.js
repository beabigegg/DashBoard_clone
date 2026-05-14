import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDrilldownNotice,
  parseTokenList,
  toQueryParams,
} from '../../src/yield-alert-center/utils';


test('parseTokenList splits newline/comma and deduplicates', () => {
  assert.deepEqual(parseTokenList('WB01,WB02\nWB01'), ['WB01', 'WB02']);
});


test('toQueryParams appends array params', () => {
  const params = toQueryParams({
    start_date: '2026-03-01',
    end_date: '2026-03-06',
    departments: ['WB01', 'WB02'],
  });
  const text = params.toString();
  assert.ok(text.includes('start_date=2026-03-01'));
  assert.ok(text.includes('departments=WB01'));
  assert.ok(text.includes('departments=WB02'));
});


test('buildDrilldownNotice returns expected messages by status', () => {
  assert.equal(buildDrilldownNotice('exact'), '');
  assert.match(buildDrilldownNotice('partial', 'reason_unmapped'), /原因碼未完整映射/);
  assert.match(buildDrilldownNotice('none'), /未找到對應報廢明細/);
});
