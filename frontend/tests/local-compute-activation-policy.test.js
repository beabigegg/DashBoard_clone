/**
 * Tests for DuckDB local-compute activation policy.
 * Task 5.3 — Verifies that local mode suppresses /view requests when active
 * and that the activation policy gates correctly.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { checkLocalComputeEligibility } from '../src/core/duckdb-activation-policy.js';

// Mock isDuckDBSupported so we can control browser support
vi.mock('../src/core/duckdb-client.js', () => ({
  isDuckDBSupported: vi.fn(() => true),
  getDuckDBClient: vi.fn(),
  fetchParquetBuffer: vi.fn(),
}));

import { isDuckDBSupported } from '../src/core/duckdb-client.js';

describe('checkLocalComputeEligibility', () => {
  beforeEach(() => {
    isDuckDBSupported.mockReturnValue(true);
  });

  it('returns eligible=true when all conditions met', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
      threshold: 5000,
      flagEnabled: true,
    });
    expect(result.eligible).toBe(true);
    expect(result.reason).toBe('ok');
  });

  it('returns eligible=false when flag is disabled', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
      flagEnabled: false,
    });
    expect(result.eligible).toBe(false);
    expect(result.reason).toBe('flag_disabled');
  });

  it('returns eligible=false when browser does not support DuckDB', () => {
    isDuckDBSupported.mockReturnValue(false);
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
    });
    expect(result.eligible).toBe(false);
    expect(result.reason).toBe('browser_unsupported');
  });

  it('returns eligible=false when spool_download_url is absent', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: null,
      totalRowCount: 10000,
    });
    expect(result.eligible).toBe(false);
    expect(result.reason).toBe('no_spool_url');
  });

  it('returns eligible=false when row count is below threshold', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 100,
      threshold: 5000,
    });
    expect(result.eligible).toBe(false);
    expect(result.reason).toBe('below_threshold');
  });

  it('returns eligible=false when totalRowCount equals threshold - 1', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/hold_dataset/abc.parquet',
      totalRowCount: 4999,
      threshold: 5000,
    });
    expect(result.eligible).toBe(false);
  });

  it('returns eligible=true when totalRowCount exactly equals threshold', () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/hold_dataset/abc.parquet',
      totalRowCount: 5000,
      threshold: 5000,
    });
    expect(result.eligible).toBe(true);
  });

  it('returns eligible=false for empty opts (no spool url)', () => {
    const result = checkLocalComputeEligibility({});
    expect(result.eligible).toBe(false);
  });
});

describe('Local compute suppresses /view requests — integration contract', () => {
  /**
   * These tests verify the _contract_ that when local compute is active,
   * the page composable skips server /view calls. Since the composables
   * are Vue components, we test the decision logic that gates the API call.
   *
   * The actual DuckDB execution path is covered by parity tests.
   */

  it('eligible response triggers activation path (not server view)', () => {
    // Simulate a query response with spool metadata
    const queryResponse = {
      query_id: 'abc123',
      spool_download_url: '/api/spool/resource_dataset/abc123.parquet',
      total_row_count: 8000,
      summary: {},
      detail: {},
    };

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: queryResponse.spool_download_url,
      totalRowCount: queryResponse.total_row_count,
    });

    // Contract: when eligible=true, the page MUST attempt duckdb.activate()
    // instead of calling GET /api/resource/history/view
    expect(eligible).toBe(true);
  });

  it('ineligible response falls back to server view path', () => {
    // Simulate a small dataset response (no spool)
    const queryResponse = {
      query_id: 'small_query',
      total_row_count: 500,
      summary: {},
      detail: {},
    };

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: queryResponse.spool_download_url,
      totalRowCount: queryResponse.total_row_count,
    });

    // Contract: when eligible=false, the page MUST use GET /api/*/view
    expect(eligible).toBe(false);
  });

  it('resource history and hold history use same threshold default (5000)', () => {
    const baseOpts = {
      spoolDownloadUrl: '/api/spool/x/y.parquet',
    };
    // At exactly 5000 rows, both pages should activate
    expect(checkLocalComputeEligibility({ ...baseOpts, totalRowCount: 5000 }).eligible).toBe(true);
    // At 4999 rows, both pages should NOT activate
    expect(checkLocalComputeEligibility({ ...baseOpts, totalRowCount: 4999 }).eligible).toBe(false);
  });
});
