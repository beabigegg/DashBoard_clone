/**
 * Validation tests for yield-alert API response shapes.
 *
 * The yield-alert-center uses DuckDB-WASM for local computation after receiving
 * a spool URL, so there is no dedicated endpoint schema in ENDPOINT_SCHEMAS for
 * yield-alert itself. Tests here cover:
 * 1. The general envelope shape (guardResponse envelope checks)
 * 2. The computeView output shape produced by useYieldAlertDuckDB
 * 3. assertShape used directly on the internal data structures
 *
 * For the spool-download path the existing MATERIAL_TRACE_SPOOL_SCHEMA pattern
 * applies; here we test the DuckDB output shapes directly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { guardResponse, detectUnknownEnvelope, _resetWarned } from '../../src/core/dev-warnings.js';
import { assertShape, _resetWarned as _resetSchemaWarned } from '../../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  _resetSchemaWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

// ---------------------------------------------------------------------------
// Envelope shape tests (generic — applies to any yield-alert API response)
// ---------------------------------------------------------------------------

describe('useYieldAlert validation — API envelope', () => {
  it('standard success envelope passes without warn', () => {
    const response = {
      success: true,
      data: { spool_download_url: '/spool/yield.parquet', total_row_count: 1234 },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    detectUnknownEnvelope(response, '/api/yield-alert/query');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('missing success field triggers warn', () => {
    const response = {
      data: { spool_download_url: '/spool/yield.parquet' },
      meta: { timestamp: '2024-01-01T00:00:00' },
    };
    detectUnknownEnvelope(response, '/api/yield-alert/query');
    expect(console.warn).toHaveBeenCalled();
  });

  it('missing meta field when success is present triggers warn', () => {
    const response = {
      success: true,
      data: { spool_download_url: '/spool/yield.parquet' },
    };
    detectUnknownEnvelope(response, '/api/yield-alert/query');
    expect(console.warn).toHaveBeenCalled();
  });

  it('non-object response triggers warn', () => {
    detectUnknownEnvelope(null, '/api/yield-alert/query');
    expect(console.warn).toHaveBeenCalled();
  });

  it('string response triggers warn', () => {
    detectUnknownEnvelope('error', '/api/yield-alert/query');
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useYieldAlertDuckDB computeView output shape validation
// We test the structure returned by computeView against expected schemas.
// ---------------------------------------------------------------------------

const SUMMARY_SHAPE = {
  transaction_qty: 'number',
  scrap_qty: 'number',
  yield_pct: 'number',
};

const TREND_ITEM_SHAPE = {
  date_bucket: 'string',
  transaction_qty: 'number',
  scrap_qty: 'number',
  yield_pct: 'number',
};

const ALERT_ITEM_SHAPE = {
  date_bucket: 'string',
  workorder: 'string',
  reason_code: 'string',
  reason_name: 'string',
  department: 'string',
  scrap_qty: 'number',
  yield_pct: 'number',
  risk_score: 'number',
  risk_level: 'string',
};

describe('useYieldAlert validation — DuckDB computeView output shapes', () => {
  it('valid summary shape passes without warn', () => {
    const summary = { transaction_qty: 10000, scrap_qty: 50, yield_pct: 99.5 };
    assertShape(summary, SUMMARY_SHAPE, 'summary');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('missing transaction_qty in summary triggers warn', () => {
    const summary = { scrap_qty: 50, yield_pct: 99.5 };
    assertShape(summary, SUMMARY_SHAPE, 'summary');
    expect(console.warn).toHaveBeenCalled();
  });

  it('transaction_qty as string triggers warn', () => {
    const summary = { transaction_qty: '10000', scrap_qty: 50, yield_pct: 99.5 };
    assertShape(summary, SUMMARY_SHAPE, 'summary');
    expect(console.warn).toHaveBeenCalled();
  });

  it('NaN yield_pct triggers warn', () => {
    const summary = { transaction_qty: 10000, scrap_qty: 50, yield_pct: NaN };
    assertShape(summary, SUMMARY_SHAPE, 'summary');
    expect(console.warn).toHaveBeenCalled();
  });

  it('valid trend item shape passes without warn', () => {
    const item = { date_bucket: '2024-01-01', transaction_qty: 500, scrap_qty: 5, yield_pct: 99.0 };
    assertShape(item, TREND_ITEM_SHAPE, 'trend.items[0]');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('date_bucket as number in trend item triggers warn', () => {
    const item = { date_bucket: 20240101, transaction_qty: 500, scrap_qty: 5, yield_pct: 99.0 };
    assertShape(item, TREND_ITEM_SHAPE, 'trend.items[0]');
    expect(console.warn).toHaveBeenCalled();
  });

  it('valid alert item shape passes without warn', () => {
    const alert = {
      date_bucket: '2024-01-01',
      workorder: 'WO-001',
      reason_code: 'SOLDER_VOID',
      reason_name: '錫球空洞',
      department: '焊接_DB',
      scrap_qty: 10,
      yield_pct: 95.0,
      risk_score: 45.2,
      risk_level: 'high',
    };
    assertShape(alert, ALERT_ITEM_SHAPE, 'alerts.items[0]');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('alert item with missing risk_score triggers warn', () => {
    const alert = {
      date_bucket: '2024-01-01',
      workorder: 'WO-001',
      reason_code: 'SOLDER_VOID',
      reason_name: '錫球空洞',
      department: '焊接_DB',
      scrap_qty: 10,
      yield_pct: 95.0,
      risk_level: 'high',
    };
    assertShape(alert, ALERT_ITEM_SHAPE, 'alerts.items[0]');
    expect(console.warn).toHaveBeenCalled();
  });

  it('alert item with scrap_qty as string triggers warn', () => {
    const alert = {
      date_bucket: '2024-01-01',
      workorder: 'WO-001',
      reason_code: 'SOLDER_VOID',
      reason_name: '錫球空洞',
      department: '焊接_DB',
      scrap_qty: '10',
      yield_pct: 95.0,
      risk_score: 45.2,
      risk_level: 'high',
    };
    assertShape(alert, ALERT_ITEM_SHAPE, 'alerts.items[0]');
    expect(console.warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Spool download URL validation (yield-alert uses same pattern as material-trace)
// ---------------------------------------------------------------------------

import { detectSpoolContentType } from '../../src/core/dev-warnings.js';

describe('useYieldAlert validation — spool URL', () => {
  it('valid parquet spool URL passes without warn', () => {
    detectSpoolContentType('/spool/yield_alert_2024.parquet', '/api/yield-alert/query');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('spool URL with /spool/ path passes without warn', () => {
    detectSpoolContentType('/files/spool/session-abc/data', '/api/yield-alert/query');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('non-string spool URL triggers warn', () => {
    detectSpoolContentType(12345, '/api/yield-alert/query');
    expect(console.warn).toHaveBeenCalled();
  });

  it('null spool URL is a no-op (no warn)', () => {
    detectSpoolContentType(null, '/api/yield-alert/query');
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('undefined spool URL is a no-op (no warn)', () => {
    detectSpoolContentType(undefined, '/api/yield-alert/query');
    expect(console.warn).not.toHaveBeenCalled();
  });
});
