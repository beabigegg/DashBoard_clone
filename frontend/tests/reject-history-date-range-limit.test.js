import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PRIMARY_QUERY_MAX_DAYS,
  validateDateRange,
} from '../src/core/reject-history-filters.js';

test('reject-history date range validates half-year max days', () => {
  assert.equal(PRIMARY_QUERY_MAX_DAYS, 183);

  const ok = validateDateRange('2025-01-01', '2025-07-02');
  assert.equal(ok, '');

  const over = validateDateRange('2025-01-01', '2025-07-03');
  assert.equal(over, '查詢範圍不可超過 183 天（最多半年）');
});
