/**
 * Validation tests for material-trace API response shapes.
 *
 * Tests guardResponse() + assertShape() behavior for:
 * - /api/material-trace/spool   — { items: 'array' }
 * - /api/material-trace/query   — { query_id: 'string?', job_id: 'string?' }
 *
 * Confirms:
 * 1. Valid response passes without console.warn
 * 2. Missing required field triggers console.warn
 * 3. Wrong type triggers console.warn
 *
 * NOTE: useMaterialTrace composable was not found in the codebase.
 * These tests validate the registered endpoint schemas directly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { guardResponse, _resetWarned } from '../../src/core/dev-warnings.js';
import {
  MATERIAL_TRACE_SPOOL_SCHEMA,
  MATERIAL_TRACE_QUERY_SCHEMA,
} from '../../src/core/endpoint-schemas.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  _resetSchemaWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

// ---------------------------------------------------------------------------
// /api/material-trace/spool — schema: { items: 'array' }
// ---------------------------------------------------------------------------

describe('useMaterialTrace validation — /api/material-trace/spool', () => {
  const endpoint = '/api/material-trace/spool';

  it('valid items array passes without warn', () => {
    const response = {
      success: true,
      data: { items: [{ lot_id: 'L001', material: 'WAFER' }] },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid empty items array passes without warn', () => {
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
      data: { items: {} },
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
      data: { page: 1, total: 10 },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing success field triggers envelope warn', () => {
    const response = {
      data: { items: [] },
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
// /api/material-trace/query — schema: { query_id: 'string?', job_id: 'string?' }
// ---------------------------------------------------------------------------

describe('useMaterialTrace validation — /api/material-trace/query', () => {
  const endpoint = '/api/material-trace/query';

  it('valid response with query_id passes without warn', () => {
    const response = {
      success: true,
      data: { query_id: 'qry-abc-123', job_id: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with job_id passes without warn', () => {
    const response = {
      success: true,
      data: { query_id: null, job_id: 'job-xyz-456' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with both null (optional fields) passes without warn', () => {
    const response = {
      success: true,
      data: { query_id: null, job_id: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('valid response with neither field absent (optional) passes without warn', () => {
    const response = {
      success: true,
      data: {},
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('query_id as number triggers console.warn', () => {
    const response = {
      success: true,
      data: { query_id: 12345, job_id: null },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    guardResponse(endpoint, response);
    expect(console.warn).toHaveBeenCalled();
  });

  it('job_id as boolean triggers console.warn', () => {
    const response = {
      success: true,
      data: { query_id: null, job_id: true },
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
// Direct assertShape tests
// ---------------------------------------------------------------------------

describe('MATERIAL_TRACE_SPOOL_SCHEMA — assertShape direct', () => {
  it('accepts valid items array', () => {
    expect(assertShape({ items: [{ id: 1 }] }, MATERIAL_TRACE_SPOOL_SCHEMA, 'data')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects items as string', () => {
    expect(assertShape({ items: 'data' }, MATERIAL_TRACE_SPOOL_SCHEMA, 'data')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

describe('MATERIAL_TRACE_QUERY_SCHEMA — assertShape direct', () => {
  it('accepts valid shape with string query_id', () => {
    expect(assertShape(
      { query_id: 'q-1', job_id: null },
      MATERIAL_TRACE_QUERY_SCHEMA,
      'data'
    )).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('rejects number query_id', () => {
    expect(assertShape(
      { query_id: 123, job_id: null },
      MATERIAL_TRACE_QUERY_SCHEMA,
      'data'
    )).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Note: useMaterialTrace composable was not found in frontend/src/
// The tests above cover the API contract via registered schemas.
// ---------------------------------------------------------------------------

describe.todo('useMaterialTrace composable — create before enabling composable-level tests');
