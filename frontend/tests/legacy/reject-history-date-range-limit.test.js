import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PRIMARY_QUERY_MAX_DAYS,
  validateDateRange,
} from '../../src/core/reject-history-filters.js';

test('reject-history date range validates half-year max days', () => {
  assert.equal(PRIMARY_QUERY_MAX_DAYS, 190);

  const ok = validateDateRange('2025-01-01', '2025-07-09');
  assert.equal(ok, '');

  const over = validateDateRange('2025-01-01', '2025-07-10');
  assert.equal(over, '查詢範圍不可超過 190 天（約半年）');
});
