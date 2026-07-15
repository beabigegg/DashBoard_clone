// @vitest-environment jsdom
/**
 * useProductionAchievement — orchestration tests (TDD, production-achievement
 * -overhaul IP-7).
 *
 * 4-mode FilterState (OD-1: no shift_code filter — D/N are columns only),
 * resolveMonthPeriod() period resolution (PA-13), range end capped at
 * min(end,today), OD-3 (auto-run on mode/station change), OD-4 (ignore
 * mode/station change while a 202 poll is in flight — enforced at the
 * setMode/setWorkcenterGroup mutation site, mirroring the existing runQuery
 * loading-guard idiom), OD-7 (persist last mode/station across a full page
 * round-trip via sessionStorage), default workcenter_group 焊接_DB.
 *
 * DuckDB is mocked at the `core/duckdb-client` + `core/duckdb-activation-policy`
 * boundary (same convention as before) so the REAL useProductionAchievementDuckDB
 * composable runs end-to-end — only the browser WASM engine / parquet fetch
 * are stubbed. `global.fetch` drives every JSON `/api/...` call.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useProductionAchievement, resolveMonthPeriod } from '../composables/useProductionAchievement';

vi.mock('../../core/duckdb-activation-policy', () => ({
  checkLocalComputeEligibility: vi.fn().mockReturnValue({ eligible: true, reason: 'ok' }),
}));

vi.mock('../../core/duckdb-client', () => {
  const mockClient = {
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  };
  return {
    getDuckDBClient: vi.fn().mockReturnValue(mockClient),
    fetchParquetBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)),
    isDuckDBSupported: vi.fn().mockReturnValue(true),
  };
});

async function mockedDuckDbClient() {
  const mod = await import('../../core/duckdb-client');
  return mod.getDuckDBClient() as unknown as {
    init: ReturnType<typeof vi.fn>;
    registerParquet: ReturnType<typeof vi.fn>;
    sendQuery: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
  };
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

const SPOOL_HIT_BODY = {
  success: true,
  data: {
    query_id: 'abc123',
    spool_download_url: '/api/spool/production_achievement/abc123.parquet',
    spec_workcenter_map: [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }],
    targets_map: [],
    package_lf_map: [],
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
    daily_plan_map: [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 300 }],
  },
  meta: {},
};

const DAILY_ROW = {
  package_lf_group: 'SOD-123FL',
  d_output_qty: 200,
  n_output_qty: 100,
  daily_output_qty: 300,
  daily_plan_qty: 300,
  achievement_rate: 1.0,
};

// Raw shape returned by computeCumulativeView's rowsSql query (composable
// multiplies daily_plan_qty by elapsed_days in JS — see useProductionAchievementDuckDB.ts).
// setMode('range') without an explicit setRangeDates() call defaults both
// start/end to "today", so elapsed_days = 1 here.
const RAW_CUMULATIVE_ROW = {
  package_lf_group: 'SOD-123FL',
  cumulative_actual_qty: 3000,
  daily_plan_qty: 3000,
};

const EXPECTED_CUMULATIVE_ROW = {
  package_lf_group: 'SOD-123FL',
  cumulative_actual_qty: 3000,
  cumulative_plan_qty: 3000,
  cumulative_diff_qty: 0,
  cumulative_achievement_rate: 1.0,
};

// Raw shape returned by the mocked DuckDB trend SQL (client.sendQuery row) --
// includes the window-function running totals the real query now computes.
const RAW_TREND_ROW = { output_date: '2026-07-01', actual_qty: 300, plan_qty: 300, cumulative_actual_qty: 300, cumulative_plan_qty: 300 };
// Fully mapped CumulativeTrendPoint the composable derives from RAW_TREND_ROW.
const TREND_POINT = {
  output_date: '2026-07-01',
  actual_qty: 300,
  plan_qty: 300,
  achievement_rate: 1.0,
  cumulative_actual_qty: 300,
  cumulative_plan_qty: 300,
  cumulative_achievement_rate: 1.0,
};

describe('resolveMonthPeriod (PA-13 pure function)', () => {
  it('1st-of-month reference date resolves to the FULL previous calendar month', () => {
    const period = resolveMonthPeriod(new Date(2026, 6, 1)); // 2026-07-01 (local)
    expect(period.start).toBe('2026-06-01');
    expect(period.end).toBe('2026-06-30');
  });

  it('1st-of-January rolls back to December of the previous year', () => {
    const period = resolveMonthPeriod(new Date(2026, 0, 1)); // 2026-01-01
    expect(period.start).toBe('2025-12-01');
    expect(period.end).toBe('2025-12-31');
  });

  it('non-1st reference date resolves to [1st of current month, referenceDate] (month-to-date)', () => {
    const period = resolveMonthPeriod(new Date(2026, 6, 14)); // 2026-07-14
    expect(period.start).toBe('2026-07-01');
    expect(period.end).toBe('2026-07-14');
  });
});

describe('useProductionAchievement — filter state defaults + mode', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('defaults to mode=today and workcenter_group=焊接_DB when no persisted state exists', () => {
    const { filters } = useProductionAchievement();
    expect(filters.mode).toBe('today');
    expect(filters.workcenter_group).toBe('焊接_DB');
  });

  it('has no shift_code field at all (OD-1: shift filter dropped)', () => {
    const { filters } = useProductionAchievement();
    expect((filters as unknown as Record<string, unknown>).shift_code).toBeUndefined();
  });
});

describe('useProductionAchievement — runQuery mode branching + auto-run + async flow', () => {
  const originalFetch = global.fetch;

  beforeEach(async () => {
    sessionStorage.clear();
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: true, data: { shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB', '焊接_WB'] }, meta: {} }),
    );
    const client = await mockedDuckDbClient();
    client.init.mockClear();
    client.registerParquet.mockClear();
    client.sendQuery.mockClear().mockResolvedValue([]);
    client.destroy.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('today/yesterday modes compute the DailyView (computeDailyView)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([DAILY_ROW]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { dailyRows, cumulativeRows, runQuery, viewKind } = useProductionAchievement();
    await runQuery();

    expect(viewKind.value).toBe('daily');
    expect(dailyRows.value).toEqual([DAILY_ROW]);
    expect(cumulativeRows.value).toEqual([]);
  });

  it('month/range modes compute the CumulativeView (computeCumulativeView) — including a single-day range (OD-2)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([RAW_CUMULATIVE_ROW]); // rows query
    client.sendQuery.mockResolvedValueOnce([RAW_TREND_ROW]); // trend query

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { cumulativeRows, cumulativeTrend, dailyRows, runQuery, setMode, viewKind } = useProductionAchievement();
    // setMode() itself auto-runs (OD-3) — do not ALSO call runQuery() here,
    // it would race the fire-and-forget query already triggered by setMode().
    void runQuery;
    setMode('range');
    await vi.waitFor(() => expect(cumulativeRows.value).toEqual([EXPECTED_CUMULATIVE_ROW]));

    expect(viewKind.value).toBe('cumulative');
    expect(cumulativeTrend.value).toEqual([TREND_POINT]);
    expect(dailyRows.value).toEqual([]);
  });

  it('OD-3: setMode auto-runs the query without any explicit submit call', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(SPOOL_HIT_BODY));

    const { setMode, hasQueried } = useProductionAchievement();
    setMode('month'); // no explicit runQuery() call from the test
    await vi.waitFor(() => expect(hasQueried.value).toBe(true));
  });

  it('OD-3: setWorkcenterGroup auto-runs (or client-side re-filters) without an explicit submit call', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(SPOOL_HIT_BODY));

    const { setWorkcenterGroup, hasQueried } = useProductionAchievement();
    setWorkcenterGroup('焊接_WB');
    await vi.waitFor(() => expect(hasQueried.value).toBe(true));
  });

  it('re-selecting the CURRENT mode is a no-op (free, no new fetch) — Reversibility note', async () => {
    const { setMode, filters } = useProductionAchievement();
    expect(filters.mode).toBe('today');
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();
    setMode('today');
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('OD-4: a mode/station change while a 202 poll is in flight is ignored — filters do not change and no second query starts', async () => {
    const JOB_ID = 'pa-job-mid-poll';
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    let reportCallCount = 0;
    let resolveJobStatus: ((v: Response) => void) | null = null;
    const jobStatusPromise = new Promise<Response>((resolve) => {
      resolveJobStatus = resolve;
    });

    fetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/report')) {
        reportCallCount++;
        if (reportCallCount === 1) {
          return Promise.resolve(
            jsonResponse({
              success: true,
              data: { async: true, job_id: JOB_ID, status_url: `/api/job/${JOB_ID}?prefix=production-achievement` },
              meta: {},
            }),
          );
        }
        return Promise.resolve(jsonResponse(SPOOL_HIT_BODY));
      }
      if (u.includes(`/api/job/${JOB_ID}`)) {
        return jobStatusPromise; // held pending until the test resolves it below — a true mid-poll state
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { runQuery, setMode, setWorkcenterGroup, filters, loading } = useProductionAchievement();
    const runPromise = runQuery();
    await vi.waitFor(() => expect(loading.value).toBe(true));

    expect(filters.mode).toBe('today');
    setMode('month'); // OD-4: must be ignored while loading
    expect(filters.mode).toBe('today'); // unchanged — the change never took effect

    expect(filters.workcenter_group).toBe('焊接_DB');
    setWorkcenterGroup('焊接_WB'); // OD-4: must also be ignored while loading
    expect(filters.workcenter_group).toBe('焊接_DB');

    expect(reportCallCount).toBe(1); // only the original enqueue — no second /report call fired

    // Resolve the held job-status call so runQuery() finishes cleanly (no dangling poll timer).
    resolveJobStatus!(jsonResponse({ success: true, data: { status: 'finished', job_id: JOB_ID }, meta: {} }));
    await runPromise;
  });

  it('OD-7: persists mode + workcenter_group to sessionStorage on change, and a fresh composable instance restores them', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }),
    );

    const first = useProductionAchievement();
    first.setWorkcenterGroup('焊接_WB');
    await vi.waitFor(() => expect(first.hasQueried.value).toBe(true));

    // Simulate a full page round-trip (new module-level composable instance,
    // same sessionStorage — mirrors navigating to /production-achievement-settings and back).
    const second = useProductionAchievement();
    expect(second.filters.workcenter_group).toBe('焊接_WB');
  });
});

describe('useProductionAchievement — month mode date resolution (regression: field-name mismatch)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('setMode("month") sends REAL start_date/end_date query params, never undefined (resolveMonthPeriod returns {start,end}, the request needs {start_date,end_date})', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    let capturedUrl = '';
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('/api/production-achievement/report')) {
        capturedUrl = String(url);
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { setMode } = useProductionAchievement();
    setMode('month');
    await vi.waitFor(() => expect(capturedUrl).toContain('/api/production-achievement/report'));

    expect(capturedUrl).not.toContain('start_date=undefined');
    expect(capturedUrl).not.toContain('end_date=undefined');
    expect(capturedUrl).toMatch(/start_date=\d{4}-\d{2}-\d{2}/);
    expect(capturedUrl).toMatch(/end_date=\d{4}-\d{2}-\d{2}/);
  });
});

describe('useProductionAchievement — range mode date handling', () => {
  beforeEach(() => {
    sessionStorage.clear();
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
  });

  it('setRangeDates caps end_date at today when a future date is supplied', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    let capturedUrl = '';
    let reportCallCount = 0;
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/production-achievement/report')) {
        reportCallCount++;
        capturedUrl = String(url);
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { setMode, setRangeDates, loading } = useProductionAchievement();
    setMode('range');
    // Let setMode()'s own OD-3 auto-run fully settle before the next
    // sequential interaction — mirrors a real user's separate clicks, and
    // avoids racing two fire-and-forget runQuery() calls in the same tick.
    await vi.waitFor(() => {
      expect(reportCallCount).toBeGreaterThanOrEqual(1);
      expect(loading.value).toBe(false);
    });

    const farFuture = '2099-12-31';
    setRangeDates('2026-07-01', farFuture);
    await vi.waitFor(() => expect(reportCallCount).toBeGreaterThanOrEqual(2));

    expect(capturedUrl).not.toContain(farFuture);
    expect(capturedUrl).toContain('start_date=2026-07-01');
  });
});
