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
  PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA,
} from '../../src/core/endpoint-schemas.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';
import {
  parseWildcardInput,
  _buildUrl,
} from '../../src/production-history/composables/useFirstTierFilters.ts';

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

// ---------------------------------------------------------------------------
// /api/production-history/filter-options — data-shape §2.7
// ---------------------------------------------------------------------------

describe('PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA — assertShape direct', () => {
  it('accepts complete four-array payload', () => {
    expect(
      assertShape(
        { pj_types: ['A'], packages: ['PKG-1'], bops: ['BOP-1'], pj_functions: ['FN-1'] },
        PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA,
        'data',
      ),
    ).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('accepts all four arrays empty (narrowed-to-zero co-occurrence)', () => {
    expect(
      assertShape(
        { pj_types: [], packages: [], bops: [], pj_functions: [] },
        PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA,
        'data',
      ),
    ).toBe(true);
  });

  it('rejects missing pj_functions field', () => {
    expect(
      assertShape(
        { pj_types: [], packages: [], bops: [] },
        PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA,
        'data',
      ),
    ).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('rejects pj_types as object (not array)', () => {
    expect(
      assertShape(
        { pj_types: {}, packages: [], bops: [], pj_functions: [] },
        PRODUCTION_HISTORY_FILTER_OPTIONS_SCHEMA,
        'data',
      ),
    ).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// parseWildcardInput — multi-line parser for first-tier wildcard textareas
// (AC-5 idempotence, dedup, trim, separator handling)
// ---------------------------------------------------------------------------

describe('parseWildcardInput — multi-line parser', () => {
  it('returns [] for null/undefined/empty', () => {
    expect(parseWildcardInput(null)).toEqual([]);
    expect(parseWildcardInput(undefined)).toEqual([]);
    expect(parseWildcardInput('')).toEqual([]);
    expect(parseWildcardInput('   ')).toEqual([]);
  });

  it('splits on newline, comma, and whitespace', () => {
    expect(parseWildcardInput('a\nb,c d')).toEqual(['a', 'b', 'c', 'd']);
  });

  it('trims whitespace around each token', () => {
    expect(parseWildcardInput('  A , B \n  C  ')).toEqual(['A', 'B', 'C']);
  });

  it('deduplicates while preserving first-seen order', () => {
    expect(parseWildcardInput('A,B,A,C,B')).toEqual(['A', 'B', 'C']);
  });

  it('preserves * wildcard tokens (does NOT translate * to %)', () => {
    // Backend handles wildcard translation per PHF-02.
    const out = parseWildcardInput('MA2025*\n*2025\nMA*2025');
    expect(out).toEqual(['MA2025*', '*2025', 'MA*2025']);
    for (const token of out) {
      expect(token).not.toContain('%');
    }
  });

  it('handles mixed CRLF + tab + comma separators', () => {
    expect(parseWildcardInput('A\r\nB\tC,D\n\nE')).toEqual(['A', 'B', 'C', 'D', 'E']);
  });

  it('is idempotent: parse(parse(x).join("\\n")) == parse(x) (AC-5)', () => {
    const inputs = [
      'MA2025\nMA2025*\nMA*2025',
      '  A , B , A ',
      'one\ntwo,three four',
      '',
      'X*\n*Y\n*Z*',
    ];
    for (const input of inputs) {
      const once = parseWildcardInput(input);
      const twice = parseWildcardInput(once.join('\n'));
      expect(twice).toEqual(once);
    }
  });
});

// ---------------------------------------------------------------------------
// _buildUrl — cross-filter URL construction (D7)
// ---------------------------------------------------------------------------

describe('_buildUrl — cross-filter URL construction', () => {
  const endpoint = '/api/production-history/filter-options';

  it('returns plain endpoint when selection is empty', () => {
    expect(_buildUrl(endpoint, {})).toBe(endpoint);
    expect(
      _buildUrl(endpoint, { pj_types: [], packages: [], bops: [], pj_functions: [] }),
    ).toBe(endpoint);
  });

  it('omits empty arrays from the encoded selection', () => {
    const url = _buildUrl(endpoint, { pj_types: ['A'], packages: [] });
    expect(url).toContain('selected=');
    const json = decodeURIComponent(url.split('selected=')[1]);
    const parsed = JSON.parse(json);
    expect(parsed).toEqual({ pj_types: ['A'] });
  });

  it('encodes a full four-field selection', () => {
    const url = _buildUrl(endpoint, {
      pj_types: ['A'],
      packages: ['PKG-1'],
      bops: ['BOP-1'],
      pj_functions: ['FN-1'],
    });
    const json = decodeURIComponent(url.split('selected=')[1]);
    expect(JSON.parse(json)).toEqual({
      pj_types: ['A'],
      packages: ['PKG-1'],
      bops: ['BOP-1'],
      pj_functions: ['FN-1'],
    });
  });
});
