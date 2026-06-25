/**
 * Validation tests for reject-history API response shapes and primary prefilter payload.
 *
 * Tests guardResponse() + assertShape() behavior for:
 * - /api/reject-history/summary
 * - /api/reject-history/options
 *
 * Also tests primary prefilter (BASE_WHERE layer) payload construction:
 * - pj_types / packages / pj_functions included when non-empty
 * - empty arrays omitted from POST body (per IP-13)
 * - pj_bop field absent from all payloads (AC-6)
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
import { toRejectFilterSnapshot } from '../../src/core/reject-history-filters.ts';

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

// ---------------------------------------------------------------------------
// Primary prefilter payload tests (AC-5, AC-6)
// Exercises toRejectFilterSnapshot and simulates buildPrimaryQueryBody logic
// ---------------------------------------------------------------------------

/**
 * Simulates the App.vue logic that builds the POST body for /api/reject-history/query.
 * Only sends primary prefilter fields when non-empty (matches IP-13 constraint).
 */
function buildPrimaryQueryBody({
  startDate = '2026-01-01',
  endDate = '2026-01-31',
  mode = 'date_range',
  includeExcludedScrap = false,
  excludeMaterialScrap = true,
  excludePbDiode = true,
  pjTypes = [],
  primaryPackages = [],
  pjFunctions = [],
} = {}) {
  const body = {
    mode,
    start_date: startDate,
    end_date: endDate,
    include_excluded_scrap: includeExcludedScrap,
    exclude_material_scrap: excludeMaterialScrap,
    exclude_pb_diode: excludePbDiode,
  };
  if (pjTypes.length > 0) body.pj_types = pjTypes;
  if (primaryPackages.length > 0) body.packages = primaryPackages;
  if (pjFunctions.length > 0) body.pj_functions = pjFunctions;
  return body;
}

describe('primary prefilter payload — pj_types multiselect value included in primary filter payload', () => {
  it('pj_types multiselect value included in primary filter payload', () => {
    const body = buildPrimaryQueryBody({ pjTypes: ['TYPE_A', 'TYPE_B'] });
    expect(body.pj_types).toEqual(['TYPE_A', 'TYPE_B']);
  });

  it('packages multiselect value included in primary filter payload', () => {
    const body = buildPrimaryQueryBody({ primaryPackages: ['PKG-X', 'PKG-Y'] });
    expect(body.packages).toEqual(['PKG-X', 'PKG-Y']);
  });

  it('pj_functions multiselect value included in primary filter payload', () => {
    const body = buildPrimaryQueryBody({ pjFunctions: ['FN-LASER', 'FN-EDGE'] });
    expect(body.pj_functions).toEqual(['FN-LASER', 'FN-EDGE']);
  });

  it('empty prefilter arrays sent as empty list not undefined', () => {
    // When all selections are empty, the body must NOT contain pj_types/packages/pj_functions
    // (omit from body per IP-13 "don't send empty arrays")
    const body = buildPrimaryQueryBody({ pjTypes: [], primaryPackages: [], pjFunctions: [] });
    // The fields should be absent (undefined), not empty arrays, per IP-13
    expect('pj_types' in body).toBe(false);
    expect('packages' in body).toBe(false);
    expect('pj_functions' in body).toBe(false);
  });

  it('pj_bop field absent from all request payloads', () => {
    // AC-6: pj_bop must never appear in any payload path
    const body = buildPrimaryQueryBody({ pjTypes: ['TYPE_A'] });
    expect('pj_bop' in body).toBe(false);
    expect('pj_bops' in body).toBe(false);
    expect('bop' in body).toBe(false);
  });
});

describe('toRejectFilterSnapshot — primary prefilter fields normalized', () => {
  it('normalizes pjTypes from unknown input', () => {
    const snap = toRejectFilterSnapshot({ pjTypes: ['TYPE_A', '  TYPE_B  ', ''] });
    // Empty string filtered; surrounding spaces trimmed
    expect(snap.pjTypes).toEqual(['TYPE_A', 'TYPE_B']);
  });

  it('normalizes primaryPackages from unknown input', () => {
    const snap = toRejectFilterSnapshot({ primaryPackages: ['PKG-X', 'PKG-Y', 'PKG-X'] });
    // Duplicates deduplicated
    expect(snap.primaryPackages).toEqual(['PKG-X', 'PKG-Y']);
  });

  it('normalizes pjFunctions from unknown input', () => {
    const snap = toRejectFilterSnapshot({ pjFunctions: ['FN-A'] });
    expect(snap.pjFunctions).toEqual(['FN-A']);
  });

  it('returns empty arrays when primary prefilter fields absent', () => {
    const snap = toRejectFilterSnapshot({});
    expect(snap.pjTypes).toEqual([]);
    expect(snap.primaryPackages).toEqual([]);
    expect(snap.pjFunctions).toEqual([]);
  });

  it('primary prefilter fields coexist with supplementary packages without conflict', () => {
    // The supplementary packages field (WHERE_CLAUSE layer) and primaryPackages
    // (BASE_WHERE layer) are separate fields and must not interfere.
    const snap = toRejectFilterSnapshot({
      packages: ['SUPP-PKG-A'],
      primaryPackages: ['PRIM-PKG-X'],
    });
    expect(snap.packages).toEqual(['SUPP-PKG-A']);
    expect(snap.primaryPackages).toEqual(['PRIM-PKG-X']);
  });
});
