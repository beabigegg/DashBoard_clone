/**
 * Validation tests for reject-history API response shapes.
 *
 * Tests guardResponse() + assertShape() behavior for:
 * - /api/reject-history/summary
 * - /api/reject-history/options
 *
 * Confirms:
 * 1. Valid response passes without console.warn
 * 2. Missing required field triggers console.warn
 * 3. Wrong type triggers console.warn
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { guardResponse, _resetWarned } from '../../src/core/dev-warnings.js';
import {
  REJECT_HISTORY_SUMMARY_SCHEMA,
  REJECT_HISTORY_OPTIONS_SCHEMA,
} from '../../src/core/endpoint-schemas.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  _resetSchemaWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

// ---------------------------------------------------------------------------
// /api/reject-history/summary — schema: { total_lots: 'number?', total_qty: 'number?' }
// ---------------------------------------------------------------------------

describe('useRejectHistory validation — /api/reject-history/summary', () => {
  const endpoint = '/api/reject-history/summary';

  it('valid response with all optional fields present passes without warn', () => {
    const response = {
      success: true,
      data: { total_lots: 1500, total_qty: 23000 },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with optional fields null passes without warn', () => {
    const response = {
      success: true,
      data: { total_lots: null, total_qty: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with optional fields absent passes without warn', () => {
    const response = {
      success: true,
      data: {},
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('wrong type for total_lots (string) triggers console.warn', () => {
    const response = {
      success: true,
      data: { total_lots: '1500', total_qty: 23000 },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('wrong type for total_qty (boolean) triggers console.warn', () => {
    const response = {
      success: true,
      data: { total_lots: 1500, total_qty: true },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing success field triggers envelope warn', () => {
    const response = {
      data: { total_lots: 100, total_qty: 500 },
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
// /api/reject-history/options — schema: { pj_types: 'array' }
// ---------------------------------------------------------------------------

describe('useRejectHistory validation — /api/reject-history/options', () => {
  const endpoint = '/api/reject-history/options';

  it('valid response with pj_types array passes without warn', () => {
    const response = {
      success: true,
      data: { pj_types: ['TYPE_A', 'TYPE_B'] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with empty pj_types array passes without warn', () => {
    const response = {
      success: true,
      data: { pj_types: [] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('pj_types as null (not array) triggers console.warn', () => {
    const response = {
      success: true,
      data: { pj_types: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('pj_types as string triggers console.warn', () => {
    const response = {
      success: true,
      data: { pj_types: 'TYPE_A,TYPE_B' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing pj_types triggers console.warn (required field)', () => {
    const response = {
      success: true,
      data: {},
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Direct assertShape tests for REJECT_HISTORY schemas
// ---------------------------------------------------------------------------

describe('REJECT_HISTORY_SUMMARY_SCHEMA — assertShape direct', () => {
  it('accepts valid shape', () => {
    const result = assertShape(
      { total_lots: 100, total_qty: 5000 },
      REJECT_HISTORY_SUMMARY_SCHEMA,
      'data'
    );
    expect(result).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('warns on wrong type for total_qty', () => {
    assertShape(
      { total_lots: 100, total_qty: '5000' },
      REJECT_HISTORY_SUMMARY_SCHEMA,
      'data'
    );
    expect(console.warn).toHaveBeenCalled();
  });
});

describe('REJECT_HISTORY_OPTIONS_SCHEMA — assertShape direct', () => {
  it('accepts valid array', () => {
    const result = assertShape(
      { pj_types: ['A', 'B'] },
      REJECT_HISTORY_OPTIONS_SCHEMA,
      'data'
    );
    expect(result).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects non-array pj_types', () => {
    const result = assertShape(
      { pj_types: 'A,B' },
      REJECT_HISTORY_OPTIONS_SCHEMA,
      'data'
    );
    expect(result).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});
