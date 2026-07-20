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

// production-achievement-sync-time: sync_time (epoch seconds) / latest_data_timestamp
// ("%Y-%m-%d %H:%M:%S") are always present on a real 200 spool-hit response
// (production_achievement_routes.py api_get_report) — included here so every
// existing test below already exercises the real response shape.
const SYNC_TIME_EPOCH = 1750000000; // 2025-06-15T16:26:40Z
const LATEST_DATA_TIMESTAMP = '2026-07-14 07:29:59';

const SPOOL_HIT_BODY = {
  success: true,
  data: {
    query_id: 'abc123',
    spool_download_url: '/api/spool/production_achievement/abc123.parquet',
    spec_workcenter_map: [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }],
    targets_map: [],
    package_lf_map: [],
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', parent_group: '焊接_DB', plan_source_side: 'input' }],
    plan_map: [{ output_date: '2026-07-14', plan_package_group: 'SOD-123FL', planqty_input: 300, planqty_output: 250 }],
    sync_time: SYNC_TIME_EPOCH,
    latest_data_timestamp: LATEST_DATA_TIMESTAMP,
  },
  meta: {},
};

/** Mirrors useProductionAchievement.ts's syncTimeLabel formatting exactly
 *  (local Date components, never toISOString) so the expectation is
 *  timezone-agnostic regardless of the test runner's TZ. */
function expectedSyncTimeLabel(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${day} ${hh}:${mm}:${ss}`;
}

// Raw row returned by computeDailyView's SELECT — this same object is BOTH
// the mocked client.sendQuery result AND the expected dailyRows.value entry
// (the composable passes every SELECT column straight through PA-21's
// nullableNumber/sf helpers, which are no-ops on already-well-typed values),
// so it must be internally consistent: shift_plan_qty = CEIL(300/2) = 150;
// d_achievement_rate = 200/150; n_achievement_rate = 100/150.
const DAILY_ROW = {
  package_lf_group: 'SOD-123FL',
  d_output_qty: 200,
  n_output_qty: 100,
  daily_output_qty: 300,
  daily_plan_qty: 300,
  achievement_rate: 1.0,
  shift_plan_qty: 150,
  d_achievement_rate: 200 / 150,
  n_achievement_rate: 100 / 150,
};

// Raw shape returned by computeCumulativeView's rowsSql query — cumulative_plan_qty
// is now a REAL SQL SUM(planqty) over the requested range (production-achievement
// -oracle-plan-source), not a daily_plan_qty*elapsed_days JS multiplication --
// see useProductionAchievementDuckDB.ts.
const RAW_CUMULATIVE_ROW = {
  package_lf_group: 'SOD-123FL',
  cumulative_actual_qty: 3000,
  cumulative_plan_qty: 3000,
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

  it('production-achievement-sync-time: runQuery populates syncTime/latestDataTimestamp (and their formatted labels) from the spool-hit response', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { syncTime, latestDataTimestamp, syncTimeLabel, latestDataTimestampLabel, runQuery } = useProductionAchievement();
    // Before any query: no data yet, so both fall back to the em-dash label.
    expect(syncTime.value).toBeNull();
    expect(latestDataTimestamp.value).toBeNull();
    expect(syncTimeLabel.value).toBe('—');
    expect(latestDataTimestampLabel.value).toBe('—');

    await runQuery();

    expect(syncTime.value).toBe(SYNC_TIME_EPOCH);
    expect(latestDataTimestamp.value).toBe(LATEST_DATA_TIMESTAMP);
    expect(syncTimeLabel.value).toBe(expectedSyncTimeLabel(SYNC_TIME_EPOCH));
    expect(latestDataTimestampLabel.value).toBe(LATEST_DATA_TIMESTAMP);
  });

  it('production-achievement-sync-time: null sync_time/latest_data_timestamp on the response (defensive metadata-miss / empty spool) render as the em-dash fallback, never "null"/"undefined"', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    const nullFreshnessBody = {
      ...SPOOL_HIT_BODY,
      data: { ...SPOOL_HIT_BODY.data, sync_time: null, latest_data_timestamp: null },
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(nullFreshnessBody));

    const { syncTime, latestDataTimestamp, syncTimeLabel, latestDataTimestampLabel, runQuery } = useProductionAchievement();
    await runQuery();

    expect(syncTime.value).toBeNull();
    expect(latestDataTimestamp.value).toBeNull();
    expect(syncTimeLabel.value).toBe('—');
    expect(latestDataTimestampLabel.value).toBe('—');
  });

  it('production-achievement-sync-time: a subsequent runQuery() resets syncTime/latestDataTimestamp to null SYNCHRONOUSLY before the new response lands -- a stale value from a prior successful query never lingers through a new in-flight query', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { syncTime, latestDataTimestamp, runQuery } = useProductionAchievement();
    await runQuery();
    expect(syncTime.value).toBe(SYNC_TIME_EPOCH); // sanity: first query populated it

    // Second query: hold its /report fetch on a manually-controlled promise
    // (never a permanently-unresolved one -- resolved + awaited at the end
    // of this test so nothing leaks into later tests) so the assertion below
    // observes state strictly BETWEEN runQuery()'s synchronous reset lines
    // (which run before its first internal `await`) and the second
    // response landing.
    let resolveSecondFetch!: (value: Response) => void;
    const secondFetch = new Promise<Response>((resolve) => {
      resolveSecondFetch = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(() => secondFetch);

    const pending = runQuery(); // synchronous reset lines have already run by the time this returns
    expect(syncTime.value).toBeNull();
    expect(latestDataTimestamp.value).toBeNull();

    // Cleanup: let the second query actually complete so no dangling
    // unresolved promise/timer survives into subsequent tests.
    resolveSecondFetch(jsonResponse(SPOOL_HIT_BODY));
    await pending;
    expect(syncTime.value).toBe(SYNC_TIME_EPOCH);
  });

  it('production-achievement-column-pivot: isExpandedSelection/expandedSubstations correctly reflect an expanded 大項 even when landing DIRECTLY on it via OD-7 persisted state (regression: the very FIRST template access happens before any query has populated the parent/children map, which used to permanently cache a stale false/[] since the map itself is a plain non-reactive Map)', async () => {
    sessionStorage.setItem(
      'production-achievement:last-report-state',
      JSON.stringify({ mode: 'today', source: 'moveout', workcenter_group: '電鍍' }),
    );
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    const EXPANDED_BODY = {
      success: true,
      data: {
        query_id: 'exp1',
        spool_download_url: '/api/spool/production_achievement_moveout/exp1.parquet',
        spec_workcenter_map: [],
        targets_map: [],
        package_lf_map: [],
        workcenter_merge_map: [
          { raw_workcenter_group: '掛鍍', merged_workcenter_group: '掛鍍', parent_group: '電鍍', plan_source_side: 'input' },
          { raw_workcenter_group: '條鍍', merged_workcenter_group: '條鍍', parent_group: '電鍍', plan_source_side: 'input' },
        ],
        plan_map: [],
      },
      meta: {},
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(EXPANDED_BODY));

    const { isExpandedSelection, expandedSubstations, runQuery } = useProductionAchievement();
    // Reading BEFORE the first query resolves is exactly the scenario a
    // template's initial render exercises -- the parent/children map is
    // still empty at this point (no report has completed yet).
    expect(isExpandedSelection.value).toBe(false);
    expect(expandedSubstations.value).toEqual([]);

    await runQuery();

    expect(isExpandedSelection.value).toBe(true);
    expect(expandedSubstations.value).toEqual(['掛鍍', '條鍍']);
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

  it('refreshQuery sends force_refresh=true, unlike a plain runQuery() call', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    const reportUrls: string[] = [];
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/report')) reportUrls.push(u);
      return Promise.resolve(jsonResponse(SPOOL_HIT_BODY));
    });

    const { runQuery, refreshQuery } = useProductionAchievement();
    await runQuery();
    await refreshQuery();

    // 1 (initial runQuery, no force_refresh) + 2 (refreshQuery: the visible
    // active-source request AND the fire-and-forget background request for
    // the OTHER source -- see refreshQuery's doc comment, PA-18 bugfix).
    expect(reportUrls).toHaveLength(3);
    expect(reportUrls[0]).not.toContain('force_refresh');
    const refreshUrls = reportUrls.slice(1);
    expect(refreshUrls.every((u) => u.includes('force_refresh=true'))).toBe(true);
    expect(refreshUrls.some((u) => u.includes('source=output'))).toBe(true);
    expect(refreshUrls.some((u) => u.includes('source=moveout'))).toBe(true);
  });

  it('refreshQuery on a spool-miss carries refresh_plan=true through the tail re-fetch WITHOUT resending force_refresh=true (avoids re-clearing the just-computed spool)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    const JOB_ID = 'pa-job-refresh-tail';
    // Track the ACTIVE source's (output, the default) report URLs separately
    // from the background other-source (moveout) fire-and-forget call --
    // refreshQuery now fires both (PA-18 bugfix), and the background one must
    // not perturb the active source's enqueue->poll->tail-refetch assertions
    // below (it gets a single benign spool-hit and is otherwise ignored).
    const outputReportUrls: string[] = [];
    let jobPollCount = 0;
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/report')) {
        if (u.includes('source=moveout')) {
          return Promise.resolve(jsonResponse(SPOOL_HIT_BODY)); // background call — result discarded, not polled
        }
        outputReportUrls.push(u);
        if (outputReportUrls.length === 1) {
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
        jobPollCount++;
        const payload =
          jobPollCount <= 1
            ? { status: 'started', job_id: JOB_ID, query_id: null, error: null, pct: 20, stage: 'querying', progress: '背景查詢中...' }
            : { status: 'finished', job_id: JOB_ID, query_id: 'qid-refresh-tail', error: null, pct: 100, stage: 'complete', progress: '查詢完成' };
        return Promise.resolve(jsonResponse(payload));
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { refreshQuery } = useProductionAchievement();
    await refreshQuery();

    expect(outputReportUrls).toHaveLength(2);
    // Original request: force_refresh=true (clears the spool, always 202s).
    expect(outputReportUrls[0]).toContain('force_refresh=true');
    // Tail re-fetch after job completion: must NOT resend force_refresh=true
    // (would re-clear the spool the job just finished computing and loop
    // forever) but MUST carry refresh_plan=true so the achievement-rate
    // denominator (plan_map) refreshes together with the now-fresh actual
    // output, instead of silently serving a stale plan cache.
    expect(outputReportUrls[1]).not.toContain('force_refresh');
    expect(outputReportUrls[1]).toContain('refresh_plan=true');
  });

  it('refreshQuery is ignored (OD-4 no-op) while a poll is already in flight', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);

    const JOB_ID = 'pa-job-refresh-mid-poll';
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
        return jobStatusPromise; // held pending — true mid-poll state
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { runQuery, refreshQuery, loading } = useProductionAchievement();
    const runPromise = runQuery();
    await vi.waitFor(() => expect(loading.value).toBe(true));

    await refreshQuery(); // OD-4 no-op: loading is true, runQuery()'s own guard applies
    expect(reportCallCount).toBe(1); // only the original enqueue — refreshQuery fired no second /report call

    resolveJobStatus!(jsonResponse({ success: true, data: { status: 'finished', job_id: JOB_ID }, meta: {} }));
    await runPromise;
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

describe('useProductionAchievement — source (產出/轉出) TAB (PA-18)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('report request carries source=output by default and source=moveout after setSource', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    const urls: string[] = [];
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('/api/production-achievement/report')) urls.push(String(url));
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: [] }, meta: {} }));
    });

    const { runQuery, setSource, filters } = useProductionAchievement();
    await runQuery();
    await vi.waitFor(() => expect(urls.length).toBeGreaterThanOrEqual(1));
    expect(urls[urls.length - 1]).toContain('source=output');

    setSource('moveout');
    expect(filters.source).toBe('moveout');
    await vi.waitFor(() => expect(urls.some((u) => u.includes('source=moveout'))).toBe(true));
  });

  it('setSource persists across a new composable instance (sessionStorage, OD-7-style)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]);
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ success: true, data: { workcenter_groups: [] }, meta: {} }));

    const first = useProductionAchievement();
    first.setSource('moveout');
    await vi.waitFor(() => expect(first.filters.source).toBe('moveout'));

    const second = useProductionAchievement();
    expect(second.filters.source).toBe('moveout');
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

describe('useProductionAchievement — checkSettingsAccess (PA-17)', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns "allowed" when the self-check reports can_edit_targets=true', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: true, data: { can_edit_targets: true }, meta: {} }),
    );
    const { checkSettingsAccess } = useProductionAchievement();
    await expect(checkSettingsAccess()).resolves.toBe('allowed');
  });

  it('returns "denied" when the self-check reports can_edit_targets=false', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: true, data: { can_edit_targets: false }, meta: {} }),
    );
    const { checkSettingsAccess } = useProductionAchievement();
    await expect(checkSettingsAccess()).resolves.toBe('denied');
  });

  it('returns "error" on a network failure -- fail-closed, distinct from an explicit deny', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network down'));
    const { checkSettingsAccess } = useProductionAchievement();
    await expect(checkSettingsAccess()).resolves.toBe('error');
  });

  it('returns "error" on a success:false envelope', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: false, error: { code: 'UNAUTHORIZED', message: '請先登入' }, meta: {} }, 401),
    );
    const { checkSettingsAccess } = useProductionAchievement();
    await expect(checkSettingsAccess()).resolves.toBe('error');
  });
});
