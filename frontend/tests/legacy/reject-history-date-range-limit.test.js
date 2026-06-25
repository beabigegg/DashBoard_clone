import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PRIMARY_QUERY_MAX_DAYS,
  validateDateRange,
} from '../../src/core/reject-history-filters.js';

test('reject-history date range validates one-year max days', () => {
  assert.equal(PRIMARY_QUERY_MAX_DAYS, 365);

  const ok = validateDateRange('2025-01-01', '2025-12-31');
  assert.equal(ok, '');

  const over = validateDateRange('2025-01-01', '2026-01-01');
  assert.equal(over, '查詢範圍不可超過 365 天（約一年）');
});
