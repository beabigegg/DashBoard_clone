/**
 * useProductionAchievement — filter state + async report/target fetch
 * orchestration for the 生產達成率 report page.
 *
 * production-achievement-async-spool (ADR-0016): GET .../report is now an
 * always-async spool-backed endpoint (mirrors resource-history's async flow
 * -- see useResourceHistoryDuckDB.ts / App.vue for the reference pattern):
 *   - spool miss  -> 202 {async:true, job_id, status_url}; poll via the
 *     generic GET /api/job/<job_id>?prefix=production-achievement until
 *     status=finished, then re-issue the identical GET /report (now a
 *     zero-Oracle-cost spool hit, data-shape-contract.md §3.28.4).
 *   - spool hit   -> 200 {query_id, spool_download_url, spec_workcenter_map,
 *     targets_map}; PA-06/PA-07 (rollup + target join + achievement_rate)
 *     now run entirely client-side in DuckDB-WASM (useProductionAchievementDuckDB).
 *   - worker unavailable -> 503, no sync fallback (always_async=True).
 *
 * shift_code/workcenter_group are NO LONGER server-side filter params (the
 * canonical spool key is date-range only) -- narrowing now happens in the
 * DuckDB computeView() SQL (business-rules.md PA-08).
 *
 * Endpoints (api-contract.md rows 256-261, data-shape-contract.md §3.28):
 *   GET /api/production-achievement/report?start_date&end_date
 *   GET /api/job/<job_id>?prefix=production-achievement            (generic poll, §1.4)
 *   POST /api/job/<job_id>/abandon  { prefix }                     (generic cancel, §1.4)
 *   GET /api/production-achievement/filter-options
 *   GET /api/production-achievement/targets?shift_code&workcenter_group
 *   PUT /api/production-achievement/targets  { shift_code, workcenter_group, target_qty }
 */
import { reactive, ref } from 'vue';
import { apiGet, apiPost } from '../../core/api';
import type { ApiResponse } from '../../core/types';
import { unwrapApiData } from '../../core/unwrap-api-result';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import { useProductionAchievementDuckDB } from './useProductionAchievementDuckDB';
import type { SpecWorkcenterMapRow, TargetsMapRow } from './useProductionAchievementDuckDB';

export interface ProductionAchievementReportRow {
  output_date: string;
  shift_code: string;
  workcenter_group: string;
  actual_output_qty: number;
  target_qty: number | null;
  achievement_rate: number | null;
}

export interface ProductionAchievementTargetRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number;
  updated_at: string;
  updated_by: string;
}

export interface FilterState {
  start_date: string;
  end_date: string;
  shift_code: string;
  workcenter_group: string;
}

interface ReportSpoolHit {
  query_id: string;
  spool_download_url: string;
  spec_workcenter_map: SpecWorkcenterMapRow[];
  targets_map: TargetsMapRow[];
}

interface ReportAsyncEnqueued {
  async: true;
  job_id: string;
  status_url: string;
}

// GET /report + the poll re-fetch can both run long (worker fan-out, queueing)
// -- mirrors resource-history/eap-alarm's async-page timeout, not the 90s default.
const API_TIMEOUT = 360000;

const DEFAULT_SHIFT_CODES = ['N', 'D', 'A', 'B', 'C'];

function getCsrfToken(): string {
  return (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null)?.content ?? '';
}

interface PutError extends Error {
  status: number;
  errorCode: string | null;
}

/**
 * core/api.ts's apiPost() hardcodes method: 'POST' (no PUT override hook), so
 * PUT requests use a small dedicated helper — same CSRF-header + envelope
 * pattern as the existing admin-pages/App.vue putJson() precedent.
 */
async function apiPut<T>(url: string, payload: unknown): Promise<ApiResponse<T>> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(payload) });
  let body: ApiResponse<T> | null = null;
  try {
    body = await resp.json();
  } catch {
    // empty/non-JSON body — fall through to the status-based error below
  }
  if (!resp.ok || (body && body.success === false)) {
    const message =
      (body && !body.success ? body.error?.message : undefined) || `HTTP ${resp.status}`;
    const err = new Error(message) as PutError;
    err.status = resp.status;
    err.errorCode = (body && !body.success ? body.error?.code : null) || null;
    throw err;
  }
  return body as ApiResponse<T>;
}

function defaultDateRange(): { start: string; end: string } {
  const today = new Date();
  const end = today.toISOString().slice(0, 10);
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  return { start: monthAgo.toISOString().slice(0, 10), end };
}

function isAsyncEnqueued(data: unknown): data is ReportAsyncEnqueued {
  const d = data as Record<string, unknown> | null;
  return !!d && d.async === true && typeof d.job_id === 'string' && d.job_id.length > 0;
}

export function useProductionAchievement() {
  const { start, end } = defaultDateRange();

  const filters = reactive<FilterState>({
    start_date: start,
    end_date: end,
    shift_code: '',
    workcenter_group: '',
  });

  const filterOptions = reactive<{ shift_codes: string[]; workcenter_groups: string[] }>({
    shift_codes: [...DEFAULT_SHIFT_CODES],
    workcenter_groups: [],
  });

  const rows = ref<ProductionAchievementReportRow[]>([]);
  const targets = ref<ProductionAchievementTargetRow[]>([]);
  const loading = ref(false);
  const error = ref('');
  const hasQueried = ref(false);

  // Permission is not pre-checkable via a dedicated contract endpoint for a
  // non-admin user (api-contract.md only exposes GET .../targets, ungated,
  // and the admin-only GET .../permissions). The edit control is shown
  // optimistically and this flag is flipped to false the first time a PUT
  // 403s, so a stale permission cache never lets the user retry silently.
  const editForbidden = ref(false);
  const editError = ref('');
  const editSaving = ref(false);

  // ── Async job progress (RQ 202 path, api-contract.md §7 Type B) ──────────
  const asyncJobProgress = reactive({
    active: false,
    jobId: null as string | null,
    status: null as string | null,
    progress: '',
    pct: 0,
    elapsedSeconds: 0,
  });

  let _jobAbortController: AbortController | null = null;
  let _jobStartedAt: number | null = null;
  let _elapsedTimer: ReturnType<typeof setInterval> | null = null;

  function _startElapsedTimer(): void {
    _jobStartedAt = Date.now();
    _elapsedTimer = setInterval(() => {
      if (_jobStartedAt !== null) {
        asyncJobProgress.elapsedSeconds = Math.floor((Date.now() - _jobStartedAt) / 1000);
      }
    }, 1000);
  }

  function _stopElapsedTimer(): void {
    if (_elapsedTimer !== null) {
      clearInterval(_elapsedTimer);
      _elapsedTimer = null;
    }
    _jobStartedAt = null;
  }

  function _resetAsyncProgress(): void {
    asyncJobProgress.active = false;
    asyncJobProgress.jobId = null;
    asyncJobProgress.status = null;
    asyncJobProgress.progress = '';
    asyncJobProgress.pct = 0;
    asyncJobProgress.elapsedSeconds = 0;
    _stopElapsedTimer();
  }

  /** Best-effort cancel of an in-flight poll (button + component-unmount use). */
  async function cancelQuery(): Promise<void> {
    const jobId = asyncJobProgress.jobId;
    if (_jobAbortController) {
      _jobAbortController.abort();
      _jobAbortController = null;
    }
    _resetAsyncProgress();
    loading.value = false;
    if (jobId) {
      try {
        await apiPost(`/api/job/${jobId}/abandon`, { prefix: 'production-achievement' }, { silent: true, timeout: 10000 });
      } catch {
        // Non-fatal: abandon is best-effort.
      }
    }
  }

  const duckdb = useProductionAchievementDuckDB();

  async function fetchFilterOptions(): Promise<void> {
    try {
      const res = await apiGet<{ shift_codes?: string[]; workcenter_groups?: string[] }>(
        '/api/production-achievement/filter-options',
      );
      if (res.success) {
        const data = (res.data ?? {}) as { shift_codes?: string[]; workcenter_groups?: string[] };
        if (Array.isArray(data.shift_codes) && data.shift_codes.length > 0) {
          filterOptions.shift_codes = data.shift_codes;
        }
        filterOptions.workcenter_groups = Array.isArray(data.workcenter_groups) ? data.workcenter_groups : [];
      }
    } catch {
      // Fail-open on filter-options load: keep the default shift-code enum,
      // leave workcenter_groups empty (user can still submit with no filter).
    }
  }

  async function fetchTargets(): Promise<void> {
    try {
      const res = await apiGet<ProductionAchievementTargetRow[]>('/api/production-achievement/targets');
      if (res.success) {
        targets.value = Array.isArray(res.data) ? res.data : [];
      }
    } catch {
      // GET targets degrades server-side to null target_qty; a network-level
      // failure here just leaves the local target list empty (view-only, no crash).
      targets.value = [];
    }
  }

  /**
   * Params captured once at enqueue time and threaded through the entire
   * poll -> tail-refetch -> render cycle for a single runQuery() call — NOT
   * live `filters` (monkey scenario 3 / FIX 3). Without this, a user who
   * edits the date range while a 202 job is still polling would cause the
   * tail re-GET to ask for a DIFFERENT date range whose spool doesn't exist
   * yet (still 202, not the expected 200 spool-hit), and/or would filter the
   * OLD spool's rendered rows by a shift_code/workcenter_group the user
   * selected for a query that never actually ran against that range.
   * Mirrors the repo's "snapshot committed params" pattern.
   */
  interface QuerySnapshot {
    start_date: string;
    end_date: string;
    shift_code: string;
    workcenter_group: string;
  }

  async function _fetchReportOnce(snapshot: QuerySnapshot): Promise<ReportSpoolHit | ReportAsyncEnqueued> {
    const response = await apiGet<ReportSpoolHit | ReportAsyncEnqueued>('/api/production-achievement/report', {
      timeout: API_TIMEOUT,
      params: { start_date: snapshot.start_date, end_date: snapshot.end_date },
    });
    return unwrapApiData(response, '查詢失敗，請稍後再試') as ReportSpoolHit | ReportAsyncEnqueued;
  }

  const MAX_TAIL_REENQUEUE_ATTEMPTS = 2;

  /**
   * Poll the enqueued job to completion, then re-issue the identical
   * GET /report (bound to the immutable `snapshot`, not live `filters`) —
   * the canonical spool now exists, so the second call normally takes the
   * 200 spool-hit path at zero Oracle cost (data-shape-contract.md §3.28.4).
   *
   * `asyncJobProgress.active` is deliberately left `true` (relabelled) after
   * the job finishes, through the tail re-GET — the caller (runQuery) resets
   * it only once the whole cycle (including DuckDB activate/render) has
   * settled, so the blank full-page LoadingOverlay never flashes back on for
   * the multi-second parquet-fetch + WASM-compute leg (FIX 2).
   *
   * Returns null (with error.value / a blank error already set as
   * appropriate) on cancellation, job failure, or poll timeout.
   */
  async function _pollForCompletion(
    job: ReportAsyncEnqueued,
    snapshot: QuerySnapshot,
    attempt = 0,
  ): Promise<ReportSpoolHit | null> {
    asyncJobProgress.active = true;
    asyncJobProgress.jobId = job.job_id;
    asyncJobProgress.status = 'queued';
    asyncJobProgress.progress = '';
    asyncJobProgress.pct = 0;
    asyncJobProgress.elapsedSeconds = 0;
    _startElapsedTimer();

    const controller = new AbortController();
    _jobAbortController = controller;

    try {
      await pollJobUntilComplete(job.status_url, {
        signal: controller.signal,
        onProgress: (statusResp) => {
          asyncJobProgress.status = statusResp.status;
          asyncJobProgress.progress = (statusResp.progress as string) || (statusResp.stage as string) || '';
          asyncJobProgress.pct = typeof statusResp.pct === 'number' ? statusResp.pct : 0;
        },
      });
    } catch (err) {
      if (_jobAbortController === controller) _jobAbortController = null;
      _resetAsyncProgress(); // no further render will happen — safe to drop the card now
      const e = err as Error & { name?: string; errorCode?: string };
      if (e?.name === 'AbortError') {
        return null; // user-cancelled — leave error blank
      }
      if (e?.errorCode === 'JOB_FAILED') {
        error.value = e?.message || '查詢執行失敗';
      } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
        error.value = '查詢執行超時，請縮小日期範圍後重試';
      } else {
        error.value = e?.message || '查詢執行發生錯誤';
      }
      return null;
    }

    if (_jobAbortController === controller) _jobAbortController = null;
    _stopElapsedTimer();
    // Keep the progress card visible (relabelled, FIX 2) — do NOT call
    // _resetAsyncProgress() here; runQuery()'s finally does that once
    // activate()/computeView() has also settled.
    asyncJobProgress.status = 'finished';
    asyncJobProgress.progress = '正在載入結果…';
    asyncJobProgress.pct = 100;

    const data = await _fetchReportOnce(snapshot);

    // FIX 3: the tail re-GET can itself come back 202 again (e.g. the spool
    // TTL/eviction raced the completion signal) — re-poll the NEW job
    // against the SAME snapshot rather than feeding an undefined
    // spool_download_url into activate(). Bounded so a backend bug can't
    // spin this forever.
    if (isAsyncEnqueued(data)) {
      if (attempt >= MAX_TAIL_REENQUEUE_ATTEMPTS) {
        _resetAsyncProgress();
        error.value = '查詢完成但結果尚未就緒，請稍後重試';
        return null;
      }
      return _pollForCompletion(data, snapshot, attempt + 1);
    }
    return data as ReportSpoolHit;
  }

  async function _fetchReport(snapshot: QuerySnapshot): Promise<ReportSpoolHit | null> {
    const data = await _fetchReportOnce(snapshot);
    if (isAsyncEnqueued(data)) {
      return _pollForCompletion(data, snapshot);
    }
    return data as ReportSpoolHit;
  }

  /** Hand the spool-hit response to DuckDB-WASM and render the computed rows. */
  async function _activateAndRender(data: ReportSpoolHit, snapshot: QuerySnapshot): Promise<void> {
    await duckdb.activate(data.spool_download_url, data.spec_workcenter_map || [], data.targets_map || []);
    rows.value = await duckdb.computeView({
      shiftCode: snapshot.shift_code || undefined,
      workcenterGroup: snapshot.workcenter_group || undefined,
    });
  }

  async function runQuery(): Promise<void> {
    if (loading.value) return;
    error.value = '';
    loading.value = true;
    hasQueried.value = true;
    _resetAsyncProgress();
    duckdb.deactivate();
    // FIX 3: snapshot the enqueue-time params once — the entire poll ->
    // tail-refetch -> render cycle below reads ONLY this snapshot, never
    // live `filters` (which the user may keep editing while a 202 job polls).
    const snapshot: QuerySnapshot = {
      start_date: filters.start_date,
      end_date: filters.end_date,
      shift_code: filters.shift_code,
      workcenter_group: filters.workcenter_group,
    };
    try {
      const data = await _fetchReport(snapshot);
      if (!data) {
        // Cancelled mid-poll or the poll failed — error.value (if any) is
        // already set by _pollForCompletion(); table renders empty, not an error.
        rows.value = [];
        return;
      }
      await _activateAndRender(data, snapshot);
    } catch (err: unknown) {
      rows.value = [];
      error.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
    } finally {
      loading.value = false;
      // FIX 2: only now (after activate()/computeView() has also settled,
      // success or failure) is it safe to drop the progress card — doing
      // this earlier flashes the blank full-page overlay back on during the
      // parquet-fetch + WASM-compute leg. No-op if the poll never ran.
      _resetAsyncProgress();
    }
  }

  async function saveTarget(payload: { shift_code: string; workcenter_group: string; target_qty: number }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await apiPut<null>('/api/production-achievement/targets', payload);
      await fetchTargets();
      // Re-render achievement_rate immediately from the refreshed target
      // list. A target-value PUT never changes the spooled report data
      // (only PA-07's join input) -- when DuckDB is already active for this
      // session, recompute client-side (zero Oracle/spool cost) instead of
      // re-issuing the async report.
      if (hasQueried.value) {
        if (duckdb.isActive.value) {
          const targetsMap: TargetsMapRow[] = targets.value.map((t) => ({
            shift_code: t.shift_code,
            workcenter_group: t.workcenter_group,
            target_qty: t.target_qty,
          }));
          await duckdb.updateTargetsMap(targetsMap);
          rows.value = await duckdb.computeView({
            shiftCode: filters.shift_code || undefined,
            workcenterGroup: filters.workcenter_group || undefined,
          });
        } else {
          await runQuery();
        }
      }
      return true;
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      const code = (err as { errorCode?: string | null })?.errorCode;
      if (status === 403 || code === 'FORBIDDEN') {
        // A 403 that slips through the proactive UI (e.g. stale permission
        // cache) is handled gracefully here: disable further edit attempts
        // for the rest of the session rather than retrying silently.
        editForbidden.value = true;
        editError.value = '您沒有編輯目標值的權限';
      } else if (status === 503) {
        editError.value = '目標值服務暫時無法使用，請稍後再試';
      } else if (status === 400) {
        editError.value = err instanceof Error ? err.message : '目標值格式錯誤';
      } else {
        editError.value = err instanceof Error ? err.message : '儲存失敗，請稍後再試';
      }
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  function resetFilters(): void {
    const { start: s, end: e } = defaultDateRange();
    filters.start_date = s;
    filters.end_date = e;
    filters.shift_code = '';
    filters.workcenter_group = '';
    rows.value = [];
    hasQueried.value = false;
    error.value = '';
    void cancelQuery();
    duckdb.deactivate();
  }

  return {
    filters,
    filterOptions,
    rows,
    targets,
    loading,
    error,
    hasQueried,
    editForbidden,
    editError,
    editSaving,
    asyncJobProgress,
    fetchFilterOptions,
    fetchTargets,
    runQuery,
    saveTarget,
    resetFilters,
    cancelQuery,
  };
}
