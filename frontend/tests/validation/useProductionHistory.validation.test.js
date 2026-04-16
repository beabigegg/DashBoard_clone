/**
 * Validation tests for production-history API response shapes.
 *
 * Tests guardResponse() + assertShape() behavior for:
 * - /api/production-history/query (sync path data shape)
 * - /api/production-history/type-options
 * - /api/production-history/count
 *
 * Confirms:
 * 1. Valid response passes without console.warn
 * 2. Missing required field triggers console.warn
 * 3. Wrong type triggers console.warn
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { guardResponse, _resetWarned } from '../../src/core/dev-warnings.js';
import {
  PRODUCTION_HISTORY_QUERY_SCHEMA,
  PRODUCTION_HISTORY_TYPE_OPTIONS_SCHEMA,
  PRODUCTION_HISTORY_COUNT_SCHEMA,
} from '../../src/core/endpoint-schemas.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  _resetSchemaWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

// ---------------------------------------------------------------------------
// /api/production-history/query — schema: { items: 'array' }
// ---------------------------------------------------------------------------

describe('useProductionHistory validation — /api/production-history/query', () => {
  const endpoint = '/api/production-history/query';

  it('valid response with items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: [{ lot_id: 'L001', qty: 100 }] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with empty items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: [] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('items as object (not array) triggers console.warn', () => {
    const response = {
      success: true,
      data: { items: { lot_id: 'L001' } },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('items as null triggers console.warn', () => {
    const response = {
      success: true,
      data: { items: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing items field triggers console.warn', () => {
    const response = {
      success: true,
      data: { dataset_id: 'ds-123' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('null data triggers warn', () => {
    const response = { success: true, data: null, meta: { timestamp: '2024-01-01T00:00:00' } };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// /api/production-history/type-options — schema: { items: 'array' }
// ---------------------------------------------------------------------------

describe('useProductionHistory validation — /api/production-history/type-options', () => {
  const endpoint = '/api/production-history/type-options';

  it('valid items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: ['QFN', 'DFN'] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('items as string triggers warn', () => {
    const response = {
      success: true,
      data: { items: 'QFN,DFN' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// /api/production-history/count — schema: { count: 'number' }
// ---------------------------------------------------------------------------

describe('useProductionHistory validation — /api/production-history/count', () => {
  const endpoint = '/api/production-history/count';

  it('valid count number passes without warn', () => {
    const response = {
      success: true,
      data: { count: 42 },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('count as string triggers console.warn', () => {
    const response = {
      success: true,
      data: { count: '42' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing count field triggers console.warn', () => {
    const response = {
      success: true,
      data: {},
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('count as NaN triggers console.warn', () => {
    const response = {
      success: true,
      data: { count: NaN },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Direct assertShape tests
// ---------------------------------------------------------------------------

describe('PRODUCTION_HISTORY_QUERY_SCHEMA — assertShape direct', () => {
  it('accepts items array', () => {
    expect(assertShape({ items: [] }, PRODUCTION_HISTORY_QUERY_SCHEMA, 'data')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects items as number', () => {
    expect(assertShape({ items: 0 }, PRODUCTION_HISTORY_QUERY_SCHEMA, 'data')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

describe('PRODUCTION_HISTORY_COUNT_SCHEMA — assertShape direct', () => {
  it('accepts valid count', () => {
    expect(assertShape({ count: 100 }, PRODUCTION_HISTORY_COUNT_SCHEMA, 'data')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects NaN count', () => {
    expect(assertShape({ count: NaN }, PRODUCTION_HISTORY_COUNT_SCHEMA, 'data')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});
