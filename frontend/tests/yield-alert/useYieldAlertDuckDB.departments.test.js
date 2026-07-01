// @vitest-environment jsdom
/**
 * WASM client parity test (§3.16.5/§3.16.6, IP-6) — useYieldAlertDuckDB.ts
 * queryFilterOptions() (internal to computeView()) must gain the same
 * `SELECT DISTINCT DEPARTMENT_NAME` dimension emitted as `workcenter_groups`
 * that the server-side `_query_filter_options()` / `compute_cross_filter_options()`
 * gained in yield_alert_sql_runtime.py, so large queries that cross the
 * DuckDB-WASM threshold mid-session do not silently lose workcenter_groups
 * cross-filtering.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../src/core/duckdb-client.js', () => ({
  getDuckDBClient: vi.fn(),
  isDuckDBSupported: vi.fn(() => true),
}));

vi.mock('../../src/core/risk-score.js', () => ({
  calcRiskScore: vi.fn(() => 0),
  calcRiskLevel: vi.fn(() => 'low'),
}));

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
  });
});

/**
 * Build a fake DuckDBClient whose sendQuery() inspects the SQL text and
 * returns fixture rows only for the DEPARTMENT_NAME distinct dimension
 * query; every other sub-view query returns an empty result set (all
 * queryTrend/queryHeatmap/queryAlerts/etc. functions tolerate []).
 */
function buildMockClient(departmentNames) {
  return {
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
    sendQuery: vi.fn(async (sql) => {
      // Match only the workcenter_groups option-read query (SELECT DISTINCT ... "DEPARTMENT_NAME"),
      // not incidental GROUP BY references to DEPARTMENT_NAME in other sub-view queries
      // (e.g. TX_DEDUP_COLS in querySummary/queryTrend/etc.).
      if (sql.includes('SELECT DISTINCT') && sql.includes('"DEPARTMENT_NAME"')) {
        // Mimic SQL DISTINCT: dedupe the fixture like the real DuckDB engine would.
        const distinct = Array.from(new Set(departmentNames));
        return distinct.map((v) => ({ v }));
      }
      return [];
    }),
  };
}

describe('useYieldAlertDuckDB — queryFilterOptions workcenter_groups (WASM parity)', () => {
  it('test_query_filter_options_includes_departments — computeView filter_options.workcenter_groups is derived from DEPARTMENT_NAME distinct values', async () => {
    const mockClient = buildMockClient(['重工站A', '重工站B', '重工站A']);

    const { getDuckDBClient } = await import('../../src/core/duckdb-client.js');
    getDuckDBClient.mockReturnValue(mockClient);

    const { useYieldAlertDuckDB } = await import('../../src/yield-alert-center/useYieldAlertDuckDB');
    const { activate, computeView } = useYieldAlertDuckDB();

    await activate('/spool/data.parquet');

    const result = await computeView({
      filters: {},
      granularity: 'day',
      riskThreshold: 98,
      minScrapQty: 1,
      sortBy: 'date_bucket',
      sortDir: 'desc',
      page: 1,
      perPage: 20,
    });

    expect(result.filter_options).toHaveProperty('workcenter_groups');
    // DISTINCT + sort dedupes and orders alphabetically, mirroring server behavior
    expect(result.filter_options.workcenter_groups).toEqual(['重工站A', '重工站B']);

    // Confirm the SQL issued for the workcenter_groups option-read reads raw
    // DEPARTMENT_NAME, not DEPARTMENT_GROUP (Known Risks Pitfall #1 / data-shape §3.16.5).
    // buildDimensionWhere's unrelated `departments`→DEPARTMENT_GROUP filter-apply mapping
    // (:181-183) is untouched by this change and is not exercised here (filters: {}).
    const workcenterGroupsCalls = mockClient.sendQuery.mock.calls.filter(([sql]) =>
      sql.includes('SELECT DISTINCT') && sql.includes('"DEPARTMENT_NAME"'),
    );
    expect(workcenterGroupsCalls.length).toBeGreaterThan(0);
    for (const [sql] of workcenterGroupsCalls) {
      expect(sql).not.toContain('"DEPARTMENT_GROUP"');
    }
  });

  it('test_query_filter_options_workcenter_groups_empty_spool — zero DEPARTMENT_NAME rows yields empty array, not an error', async () => {
    const mockClient = buildMockClient([]);

    const { getDuckDBClient } = await import('../../src/core/duckdb-client.js');
    getDuckDBClient.mockReturnValue(mockClient);

    const { useYieldAlertDuckDB } = await import('../../src/yield-alert-center/useYieldAlertDuckDB');
    const { activate, computeView } = useYieldAlertDuckDB();

    await activate('/spool/data.parquet');

    const result = await computeView({
      filters: {},
      granularity: 'day',
      riskThreshold: 98,
      minScrapQty: 1,
      sortBy: 'date_bucket',
      sortDir: 'desc',
      page: 1,
      perPage: 20,
    });

    expect(result.filter_options.workcenter_groups).toEqual([]);
  });

  it('test_query_filter_options_excludes_sentinel_values — (NA)/-1/blank DEPARTMENT_NAME values are filtered like other dimensions', async () => {
    const mockClient = buildMockClient(['重工站A', '(NA)', '-1', '', '  ']);

    const { getDuckDBClient } = await import('../../src/core/duckdb-client.js');
    getDuckDBClient.mockReturnValue(mockClient);

    const { useYieldAlertDuckDB } = await import('../../src/yield-alert-center/useYieldAlertDuckDB');
    const { activate, computeView } = useYieldAlertDuckDB();

    await activate('/spool/data.parquet');

    const result = await computeView({
      filters: {},
      granularity: 'day',
      riskThreshold: 98,
      minScrapQty: 1,
      sortBy: 'date_bucket',
      sortDir: 'desc',
      page: 1,
      perPage: 20,
    });

    expect(result.filter_options.workcenter_groups).toEqual(['重工站A']);
  });
});
