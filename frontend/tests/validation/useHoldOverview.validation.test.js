/**
 * Validation tests for hold-overview API response shapes.
 *
 * Tests guardResponse() + assertShape() behavior for:
 * - /api/hold-overview/summary  — { totalLots, totalQty, avgAge?, maxAge?, workcenterCount, dataUpdateDate? }
 * - /api/hold-overview/treemap  — { items: 'array' }
 *
 * Confirms:
 * 1. Valid response passes without console.warn
 * 2. Missing required field triggers console.warn
 * 3. Wrong type triggers console.warn
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { guardResponse, _resetWarned } from '../../src/core/dev-warnings.js';
import {
  HOLD_OVERVIEW_SUMMARY_SCHEMA,
  HOLD_OVERVIEW_TREEMAP_SCHEMA,
} from '../../src/core/endpoint-schemas.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  _resetSchemaWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

// ---------------------------------------------------------------------------
// /api/hold-overview/summary
// Schema: { totalLots: 'number', totalQty: 'number', avgAge: 'number?',
//           maxAge: 'number?', workcenterCount: 'number', dataUpdateDate: 'string?' }
// ---------------------------------------------------------------------------

describe('useHoldOverview validation — /api/hold-overview/summary', () => {
  const endpoint = '/api/hold-overview/summary';

  it('fully valid response passes without warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: 3200,
        avgAge: 2.5,
        maxAge: 10,
        workcenterCount: 5,
        dataUpdateDate: '2024-01-15',
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with optional fields null passes without warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: 3200,
        avgAge: null,
        maxAge: null,
        workcenterCount: 5,
        dataUpdateDate: null,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with optional fields absent passes without warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: 3200,
        workcenterCount: 5,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('missing required totalLots triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalQty: 3200,
        workcenterCount: 5,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing required totalQty triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        workcenterCount: 5,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing required workcenterCount triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: 3200,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('totalLots as string triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: '150',
        totalQty: 3200,
        workcenterCount: 5,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('totalQty as boolean triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: false,
        workcenterCount: 5,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('workcenterCount as NaN triggers console.warn', () => {
    const response = {
      success: true,
      data: {
        totalLots: 150,
        totalQty: 3200,
        workcenterCount: NaN,
      },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('null data triggers warn', () => {
    const response = { success: true, data: null, meta: { timestamp: '2024-01-15T08:00:00' } };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing success field triggers envelope warn', () => {
    const response = {
      data: { totalLots: 150, totalQty: 3200, workcenterCount: 5 },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// /api/hold-overview/treemap — schema: { items: 'array' }
// ---------------------------------------------------------------------------

describe('useHoldOverview validation — /api/hold-overview/treemap', () => {
  const endpoint = '/api/hold-overview/treemap';

  it('valid items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: [{ name: 'WC-A', value: 100 }] },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid empty items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: [] },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('items as null triggers console.warn', () => {
    const response = {
      success: true,
      data: { items: null },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing items field triggers console.warn', () => {
    const response = {
      success: true,
      data: { total: 5 },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('items as number triggers console.warn', () => {
    const response = {
      success: true,
      data: { items: 42 },
      meta: { timestamp: '2024-01-15T08:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Direct assertShape tests
// ---------------------------------------------------------------------------

describe('HOLD_OVERVIEW_SUMMARY_SCHEMA — assertShape direct', () => {
  it('accepts complete valid shape', () => {
    const result = assertShape(
      { totalLots: 10, totalQty: 100, workcenterCount: 2, avgAge: 3.5, maxAge: 7, dataUpdateDate: '2024-01-01' },
      HOLD_OVERVIEW_SUMMARY_SCHEMA,
      'data'
    );
    expect(result).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects missing totalLots', () => {
    const result = assertShape(
      { totalQty: 100, workcenterCount: 2 },
      HOLD_OVERVIEW_SUMMARY_SCHEMA,
      'data'
    );
    expect(result).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('rejects totalLots as string', () => {
    const result = assertShape(
      { totalLots: '10', totalQty: 100, workcenterCount: 2 },
      HOLD_OVERVIEW_SUMMARY_SCHEMA,
      'data'
    );
    expect(result).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

describe('HOLD_OVERVIEW_TREEMAP_SCHEMA — assertShape direct', () => {
  it('accepts valid items array', () => {
    expect(assertShape({ items: [] }, HOLD_OVERVIEW_TREEMAP_SCHEMA, 'data')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects items as object', () => {
    expect(assertShape({ items: {} }, HOLD_OVERVIEW_TREEMAP_SCHEMA, 'data')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Export mode — CSV helper schema validation (AC-2, AC-3)
//
// Verifies that the exportLots() helper chain produces the right 15 columns
// from a mock export response payload matching the /api/hold-overview/lots
// data-shape-contract §3.15 column set.
// ---------------------------------------------------------------------------

import { _buildCsv } from '../../src/hold-overview/csvExport.ts';

describe('hold-overview export mode — _buildCsv with lots response shape', () => {
  // Simulate the data returned by the /api/hold-overview/lots export endpoint
  const EXPORT_LOT = {
    lotId: 'LOT-EXP-001',
    workorder: 'WO-EXP-999',
    qty: 100,
    product: 'PROD-EXP',
    package: 'PKG-EXP',
    workcenter: 'WC-EXP',
    holdReason: 'EXP-REASON',
    spec: 'SPEC-EXP',
    age: 7,
    holdTime: '2026-07-18T09:15:00',
    holdDurationHours: 6.25,
    holdBy: 'eng001',
    dept: 'QC',
    holdComment: 'export comment',
    futureHoldComment: 'future export comment',
  };

  it('export response shape produces 15-column CSV row', () => {
    const csv = _buildCsv([EXPORT_LOT]);
    const lines = csv.split('\n');
    expect(lines.length).toBe(2);
    // header must have 15 columns
    expect(lines[0].split(',').length).toBe(15);
    // data row must have 15 columns (no commas in EXPORT_LOT values)
    expect(lines[1].split(',').length).toBe(15);
  });

  it('CSV contains all 15 required field values from export response', () => {
    const csv = _buildCsv([EXPORT_LOT]);
    expect(csv).toContain('LOT-EXP-001');
    expect(csv).toContain('WO-EXP-999');
    expect(csv).toContain('100');
    expect(csv).toContain('PROD-EXP');
    expect(csv).toContain('PKG-EXP');
    expect(csv).toContain('WC-EXP');
    expect(csv).toContain('EXP-REASON');
    expect(csv).toContain('SPEC-EXP');
    expect(csv).toContain('7');
    expect(csv).toContain('2026-07-18T09:15:00');
    expect(csv).toContain('6.25');
    expect(csv).toContain('eng001');
    expect(csv).toContain('QC');
    expect(csv).toContain('export comment');
    expect(csv).toContain('future export comment');
  });

  it('export with export:true param flag excluded from CSV output (CSV has no "export" column)', () => {
    // The export request adds { export: true } but the CSV row must not include
    // an "export" column — it is a request flag, not a data field.
    const csv = _buildCsv([{ ...EXPORT_LOT, export: true }]);
    const headerLine = csv.split('\n')[0];
    expect(headerLine).not.toContain('export');
    // Still 15 columns despite the extra key
    expect(headerLine.split(',').length).toBe(15);
  });

  it('empty lots array from export response produces header-only CSV (AC-5)', () => {
    const csv = _buildCsv([]);
    const lines = csv.split('\n');
    expect(lines.length).toBe(1);
    expect(lines[0].split(',').length).toBe(15);
  });
});
