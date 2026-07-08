// @vitest-environment jsdom
/**
 * useProductionAchievement — orchestration tests (TDD: updated for
 * production-achievement-async-spool's 202/200-spool-hit/503 report flow).
 *
 * DuckDB is mocked at the `core/duckdb-client` + `core/duckdb-activation-policy`
 * boundary (same convention as useProductionAchievementDuckDB.test.ts) so the
 * REAL useProductionAchievementDuckDB composable runs end-to-end here —
 * only the browser WASM engine / parquet fetch are stubbed. `global.fetch`
 * drives every JSON `/api/...` call (report/poll/targets/PUT), matching the
 * existing convention in this file.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useProductionAchievement } from '../composables/useProductionAchievement';

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
    targets_map: [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 120 }],
  },
  meta: {},
};

const COMPUTED_ROW = {
  output_date: '2026-01-01',
  shift_code: 'D',
  workcenter_group: '焊接_DB',
  actual_output_qty: 100,
  target_qty: 120,
  achievement_rate: 0.833,
};

describe('useProductionAchievement', () => {
  const originalFetch = global.fetch;

  beforeEach(async () => {
    // core/api.ts's apiGet/apiPost use the global fetch too (no MesApi bridge in jsdom)
    global.fetch = vi.fn();
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

  it('runQuery: spool hit (200) activates DuckDB and renders the computed rows', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValue([]); // CREATE TABLE calls
    client.sendQuery.mockResolvedValueOnce([]); // spec map create
    client.sendQuery.mockResolvedValueOnce([]); // targets map create
    client.sendQuery.mockResolvedValueOnce([]); // rollup create
    client.sendQuery.mockResolvedValueOnce([COMPUTED_ROW]); // computeView SELECT

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { rows, runQuery, hasQueried, error } = useProductionAchievement();
    await runQuery();

    expect(hasQueried.value).toBe(true);
    expect(error.value).toBe('');
    expect(rows.value).toEqual([COMPUTED_ROW]);
    expect(client.registerParquet).toHaveBeenCalledWith(
      'production_achievement_data',
      expect.any(ArrayBuffer),
    );
  });

  it('runQuery: spool miss (202) polls to completion, re-fetches, then renders rows', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([COMPUTED_ROW]);

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { async: true, job_id: 'job-1', status_url: '/api/job/job-1?prefix=production-achievement' },
          meta: {},
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished', query_id: 'abc123' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { rows, runQuery, hasQueried, error, asyncJobProgress } = useProductionAchievement();
    await runQuery();

    expect(hasQueried.value).toBe(true);
    expect(error.value).toBe('');
    expect(rows.value).toEqual([COMPUTED_ROW]);
    expect(asyncJobProgress.active).toBe(false); // reset after completion
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('FIX 2: asyncJobProgress stays active (relabelled) through the tail refetch + DuckDB activate/render, resetting only after the whole cycle settles', async () => {
    const client = await mockedDuckDbClient();
    const { runQuery, asyncJobProgress } = useProductionAchievement();

    let activeDuringCompute: boolean | null = null;
    let statusDuringCompute: string | null = null;
    let progressDuringCompute = '';
    let pctDuringCompute = -1;

    client.sendQuery
      .mockResolvedValueOnce([]) // spec map create
      .mockResolvedValueOnce([]) // targets map create
      .mockResolvedValueOnce([]) // rollup create
      .mockImplementationOnce(async () => {
        // Snapshot progress state exactly when the final computeView SELECT
        // runs — stands in for the multi-second parquet-fetch + WASM-compute
        // leg that must NOT drop back to a blank full-page overlay (FIX 2).
        activeDuringCompute = asyncJobProgress.active;
        statusDuringCompute = asyncJobProgress.status;
        progressDuringCompute = asyncJobProgress.progress;
        pctDuringCompute = asyncJobProgress.pct;
        return [COMPUTED_ROW];
      });

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { async: true, job_id: 'job-2', status_url: '/api/job/job-2?prefix=production-achievement' },
          meta: {},
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished', query_id: 'abc123' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    await runQuery();

    expect(activeDuringCompute).toBe(true);
    expect(statusDuringCompute).toBe('finished');
    expect(progressDuringCompute).toBe('正在載入結果…');
    expect(pctDuringCompute).toBe(100);
    // Only AFTER the whole cycle (poll + tail refetch + activate/render) has
    // settled does the progress card reset.
    expect(asyncJobProgress.active).toBe(false);
  });

  it('FIX 3: mid-poll date-range edits do not leak into the tail re-GET (enqueue-time snapshot, not live filters)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([COMPUTED_ROW]);

    const { filters, runQuery, rows } = useProductionAchievement();
    const originalStart = filters.start_date;
    const originalEnd = filters.end_date;

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { async: true, job_id: 'job-3', status_url: '/api/job/job-3?prefix=production-achievement' },
          meta: {},
        }),
      )
      .mockImplementationOnce(async () => {
        // The user edits the date range WHILE the job is still polling.
        filters.start_date = '2099-01-01';
        filters.end_date = '2099-01-31';
        return jsonResponse({ success: true, data: { status: 'finished', query_id: 'abc123' }, meta: {} });
      })
      .mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    await runQuery();

    expect(rows.value).toEqual([COMPUTED_ROW]);
    const tailCallUrl = String(fetchMock.mock.calls[2][0]);
    expect(tailCallUrl).toContain(`start_date=${originalStart}`);
    expect(tailCallUrl).toContain(`end_date=${originalEnd}`);
    expect(tailCallUrl).not.toContain('2099-01-01');
    // The user's live edit is preserved for their NEXT query — only the
    // already-in-flight cycle ignored it.
    expect(filters.start_date).toBe('2099-01-01');
  });

  it('FIX 3: tail re-GET returning 202 again is handled by re-polling the new job, not by throwing', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([COMPUTED_ROW]);

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { async: true, job_id: 'job-4', status_url: '/api/job/job-4?prefix=production-achievement' },
          meta: {},
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished' }, meta: {} })) // first poll finished
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { async: true, job_id: 'job-4b', status_url: '/api/job/job-4b?prefix=production-achievement' },
          meta: {},
        }),
      ) // tail re-GET unexpectedly still 202 (e.g. spool TTL/eviction raced completion)
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished' }, meta: {} })) // second poll finished
      .mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY)); // second tail re-GET -> 200 spool-hit

    const { runQuery, rows, error } = useProductionAchievement();
    await expect(runQuery()).resolves.toBeUndefined();

    expect(error.value).toBe('');
    expect(rows.value).toEqual([COMPUTED_ROW]);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it('FIX 3: repeated 202-on-retry beyond the safety cap surfaces a clear error instead of looping forever', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { async: true, job_id: 'j0', status_url: '/api/job/j0?prefix=production-achievement' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { async: true, job_id: 'j1', status_url: '/api/job/j1?prefix=production-achievement' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { async: true, job_id: 'j2', status_url: '/api/job/j2?prefix=production-achievement' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { status: 'finished' }, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ success: true, data: { async: true, job_id: 'j3', status_url: '/api/job/j3?prefix=production-achievement' }, meta: {} }));

    const { runQuery, rows, error } = useProductionAchievement();
    await runQuery();

    expect(rows.value).toEqual([]);
    expect(error.value).not.toBe('');
  });

  it('runQuery: 503 worker-unavailable surfaces a clear error and empties rows', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse(
        { success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '背景查詢服務不可用，請稍後再試' }, meta: {} },
        503,
      ),
    );

    const { rows, runQuery, error, hasQueried } = useProductionAchievement();
    await runQuery();

    expect(rows.value).toEqual([]);
    expect(error.value).toContain('背景查詢服務不可用');
    // FIX 1 precondition: hasQueried stays true AND error is truthy at the
    // same time — App.vue's showResults = hasQueried && !error must resolve
    // to false here (see App.test.ts for the template-level assertion) so
    // the summary/chart/empty-table never render alongside this error.
    expect(hasQueried.value).toBe(true);
  });

  it('runQuery sets error and empties rows on network failure (no crash)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));

    const { rows, runQuery, error } = useProductionAchievement();
    await runQuery();

    expect(rows.value).toEqual([]);
    expect(error.value).not.toBe('');
  });

  it('runQuery: empty spool renders an empty row set, not an error (empty-result invariant)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]); // computeView SELECT -> zero rows

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { rows, runQuery, hasQueried, error } = useProductionAchievement();
    await runQuery();

    expect(hasQueried.value).toBe(true);
    expect(error.value).toBe('');
    expect(rows.value).toEqual([]);
  });

  it('saveTarget: recomputes client-side from refreshed targets when DuckDB is already active (no re-query)', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery
      .mockResolvedValueOnce([]) // spec map create
      .mockResolvedValueOnce([]) // targets map create
      .mockResolvedValueOnce([]) // rollup create
      .mockResolvedValueOnce([COMPUTED_ROW]); // computeView after runQuery()

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY)) // runQuery's GET /report
      .mockResolvedValueOnce(jsonResponse({ success: true, data: null, meta: {} })) // PUT targets
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 200, updated_at: 't', updated_by: 'u' }],
          meta: {},
        }),
      ); // GET targets refetch

    const { runQuery, saveTarget, hasQueried, rows } = useProductionAchievement();
    await runQuery();
    expect(hasQueried.value).toBe(true);

    client.sendQuery.mockClear();
    client.sendQuery
      .mockResolvedValueOnce([]) // updateTargetsMap re-registration
      .mockResolvedValueOnce([{ ...COMPUTED_ROW, target_qty: 200, achievement_rate: 0.5 }]); // computeView after save

    const ok = await saveTarget({ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 200 });

    expect(ok).toBe(true);
    // Only 2 sendQuery calls (targets-map re-register + recompute) — no
    // second parquet download / rollup rebuild, and NO extra GET /report.
    expect(client.sendQuery).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledTimes(3); // report, PUT, targets-refetch only
    expect(rows.value[0].target_qty).toBe(200);
  });

  it('saveTarget: falls back to a full runQuery when DuckDB is not active yet', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ success: true, data: null, meta: {} })) // PUT
      .mockResolvedValueOnce(jsonResponse({ success: true, data: [], meta: {} })); // GET targets refetch

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(true);
    expect(editForbidden.value).toBe(false);
    expect(editError.value).toBe('');
  });

  it('saveTarget flips editForbidden on a 403 FORBIDDEN response (graceful degrade)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { success: false, error: { code: 'FORBIDDEN', message: '無權限' }, meta: {} },
        403,
      ),
    );

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(false);
    expect(editForbidden.value).toBe(true);
    expect(editError.value).not.toBe('');
  });

  it('saveTarget surfaces a 503 without flipping editForbidden (OPS disabled, not a permission denial)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫停' }, meta: {} },
        503,
      ),
    );

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(false);
    expect(editForbidden.value).toBe(false);
    expect(editError.value).not.toBe('');
  });

  it('resetFilters clears rows/hasQueried and deactivates the DuckDB session', async () => {
    const client = await mockedDuckDbClient();
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([COMPUTED_ROW]);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));

    const { rows, runQuery, hasQueried, resetFilters } = useProductionAchievement();
    await runQuery();
    expect(rows.value.length).toBe(1);

    resetFilters();
    expect(rows.value).toEqual([]);
    expect(hasQueried.value).toBe(false);
    expect(client.destroy).toHaveBeenCalled();
  });

  it('cancelQuery aborts an in-flight poll without throwing', async () => {
    const { cancelQuery, asyncJobProgress } = useProductionAchievement();
    asyncJobProgress.active = true;
    asyncJobProgress.jobId = 'job-xyz';
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse({ success: true, data: { acknowledged: true }, meta: {} }));

    await expect(cancelQuery()).resolves.toBeUndefined();
    expect(asyncJobProgress.active).toBe(false);
  });
});
