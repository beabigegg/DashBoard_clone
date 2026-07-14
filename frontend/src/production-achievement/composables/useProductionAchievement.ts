/**
 * useProductionAchievement — 4-mode filter state + async report/target fetch
 * orchestration for the 生產達成率 report page.
 *
 * Change: production-achievement-overhaul (IP-7). Widens the filter model
 * from a free-form date-range + shift_code/workcenter_group query into a
 * fixed 4-mode selector (當日/前日/當月/自訂區間) with a single station-group
 * filter — OD-1 drops shift_code as a filter entirely (D/N render as columns,
 * never a filter). Mode determines both the date window (`resolveMonthPeriod`
 * for 當月; range end capped at min(end,today) for 自訂區間) and which
 * DuckDB-WASM view is computed: 當日/前日 -> computeDailyView (PA-12),
 * 當月/自訂區間 -> computeCumulativeView (PA-13, D3 aggregate-then-divide;
 * OD-2: 自訂區間 is ALWAYS cumulative-style, even a single-day range).
 *
 * The async 202-poll machinery (spool-miss -> enqueue -> poll -> tail re-GET)
 * is UNCHANGED from production-achievement-async-spool (ADR-0016) — only its
 * request params (drop shift_code, mode replaces literal start/end from the
 * caller) and its post-fetch DuckDB activation (5 inline maps, 2-stage
 * rollup) changed. See useProductionAchievementDuckDB.ts.
 *
 * OD-3 (full auto-run, all 4 modes) / OD-4 (ignore a mode or station change
 * while a 202 poll is in flight, no cancel-and-restart): both are enforced at
 * the `setMode`/`setWorkcenterGroup`/`setRangeDates` mutation sites via the
 * SAME `if (loading.value) return` idiom `runQuery()` already used — a change
 * attempted mid-poll is a pure no-op (filters do not update, no new query
 * starts); it is not queued or retried once the in-flight query resolves.
 *
 * OD-7 (preserve mode/station across the round-trip to /production-achievement
 * -settings and back): persisted to `sessionStorage` on every successful
 * mode/station change and restored when a new composable instance is created
 * (survives a full page navigation, since settings is a separate mini-app).
 *
 * "Station-group switch is instant/free — a client-side re-filter of the
 * already-downloaded day's spool, not a new query" (interaction-design.md §
 * Reversibility): setWorkcenterGroup() recomputes from the cached DuckDB
 * tables directly when a spool is already active, exactly like the existing
 * saveTarget() client-side-recompute precedent — no new /report fetch.
 *
 * Endpoints (api-contract.md rows 256-261, data-shape-contract.md §3.28):
 *   GET /api/production-achievement/report?start_date&end_date&workcenter_group
 *   GET /api/job/<job_id>?prefix=production-achievement            (generic poll, §1.4)
 *   POST /api/job/<job_id>/abandon  { prefix }                     (generic cancel, §1.4)
 *   GET /api/production-achievement/filter-options
 *   GET /api/production-achievement/targets?shift_code&workcenter_group
 *   PUT /api/production-achievement/targets  { shift_code, workcenter_group, target_qty }
 */
import { computed, reactive, ref } from 'vue';
import { apiGet, apiPost } from '../../core/api';
import type { ApiResponse } from '../../core/types';
import { unwrapApiData } from '../../core/unwrap-api-result';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import { useProductionAchievementDuckDB } from './useProductionAchievementDuckDB';
import type {
  SpecWorkcenterMapRow,
  TargetsMapRow,
  PackageLfMapRow,
  WorkcenterMergeMapRow,
  DailyPlanMapRow,
  DailyViewRow,
  CumulativeViewRow,
  CumulativeTrendPoint,
} from './useProductionAchievementDuckDB';

export type ProductionAchievementMode = 'today' | 'yesterday' | 'month' | 'range';

export interface ProductionAchievementTargetRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number;
  updated_at: string;
  updated_by: string;
}

export interface FilterState {
  mode: ProductionAchievementMode;
  workcenter_group: string;
  /** Meaningful only when mode === 'range'. */
  start_date: string;
  /** Meaningful only when mode === 'range'; capped at min(end_date, today) before use. */
  end_date: string;
}

interface ReportSpoolHit {
  query_id: string;
  spool_download_url: string;
  spec_workcenter_map: SpecWorkcenterMapRow[];
  targets_map: TargetsMapRow[];
  package_lf_map: PackageLfMapRow[];
  workcenter_merge_map: WorkcenterMergeMapRow[];
  daily_plan_map: DailyPlanMapRow[];
}

interface ReportAsyncEnqueued {
  async: true;
  job_id: string;
  status_url: string;
}

// GET /report + the poll re-fetch can both run long (worker fan-out, queueing)
// -- mirrors resource-history/eap-alarm's async-page timeout, not the 90s default.
const API_TIMEOUT = 360000;

const DEFAULT_MODE: ProductionAchievementMode = 'today';
const DEFAULT_WORKCENTER_GROUP = '焊接_DB';
const VALID_MODES: ProductionAchievementMode[] = ['today', 'yesterday', 'month', 'range'];

// OD-7: survives a full page navigation to /production-achievement-settings
// and back (separate mini-app — no in-memory store can bridge that round-trip).
const PERSIST_KEY = 'production-achievement:last-report-state';

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

function formatLocalDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * PA-13 period resolution: on the 1st of the month, resolve to the FULL
 * previous calendar month (the current month has not started yet); any other
 * day resolves to month-to-date [1st, referenceDate]. Pure function, local
 * Date components only (never `.toISOString()` — that converts to UTC and
 * can shift the calendar date near local midnight, e.g. UTC+8).
 */
export function resolveMonthPeriod(referenceDate: Date): { start: string; end: string } {
  const y = referenceDate.getFullYear();
  const m = referenceDate.getMonth(); // 0-indexed
  if (referenceDate.getDate() === 1) {
    const prevMonthLastDay = new Date(y, m, 0); // day 0 rolls back to the last day of the previous month
    const prevMonthFirstDay = new Date(y, m - 1, 1);
    return { start: formatLocalDate(prevMonthFirstDay), end: formatLocalDate(prevMonthLastDay) };
  }
  const firstOfMonth = new Date(y, m, 1);
  return { start: formatLocalDate(firstOfMonth), end: formatLocalDate(referenceDate) };
}

interface PersistedReportState {
  mode: ProductionAchievementMode;
  workcenter_group: string;
}

function readPersistedState(): PersistedReportState {
  try {
    const raw = sessionStorage.getItem(PERSIST_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<PersistedReportState>;
      const mode = VALID_MODES.includes(parsed.mode as ProductionAchievementMode) ? (parsed.mode as ProductionAchievementMode) : DEFAULT_MODE;
      const workcenter_group =
        typeof parsed.workcenter_group === 'string' && parsed.workcenter_group ? parsed.workcenter_group : DEFAULT_WORKCENTER_GROUP;
      return { mode, workcenter_group };
    }
  } catch {
    // sessionStorage unavailable (e.g. private browsing quota) — fall back to defaults
  }
  return { mode: DEFAULT_MODE, workcenter_group: DEFAULT_WORKCENTER_GROUP };
}

function persistState(mode: ProductionAchievementMode, workcenter_group: string): void {
  try {
    sessionStorage.setItem(PERSIST_KEY, JSON.stringify({ mode, workcenter_group }));
  } catch {
    // best-effort only — never throw from a persistence side-effect
  }
}

function isAsyncEnqueued(data: unknown): data is ReportAsyncEnqueued {
  const d = data as Record<string, unknown> | null;
  return !!d && d.async === true && typeof d.job_id === 'string' && d.job_id.length > 0;
}

export function useProductionAchievement() {
  const persisted = readPersistedState();

  const filters = reactive<FilterState>({
    mode: persisted.mode,
    workcenter_group: persisted.workcenter_group,
    start_date: '',
    end_date: '',
  });

  const filterOptions = reactive<{ workcenter_groups: string[] }>({
    workcenter_groups: [],
  });

  const dailyRows = ref<DailyViewRow[]>([]);
  const cumulativeRows = ref<CumulativeViewRow[]>([]);
  const cumulativeTrend = ref<CumulativeTrendPoint[]>([]);
  const targets = ref<ProductionAchievementTargetRow[]>([]);
  const loading = ref(false);
  const error = ref('');
  const hasQueried = ref(false);

  const viewKind = computed<'daily' | 'cumulative'>(() =>
    filters.mode === 'today' || filters.mode === 'yesterday' ? 'daily' : 'cumulative',
  );

  // Permission is not pre-checkable via a dedicated contract endpoint for a
  // non-admin user. The edit control is shown optimistically and this flag is
  // flipped to false the first time a PUT 403s (fail-closed, same as before).
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
      const res = await apiGet<{ workcenter_groups?: string[] }>('/api/production-achievement/filter-options');
      if (res.success) {
        const data = (res.data ?? {}) as { workcenter_groups?: string[] };
        filterOptions.workcenter_groups = Array.isArray(data.workcenter_groups) ? data.workcenter_groups : [];
      }
    } catch {
      // Fail-open on filter-options load: station select just shows no options
      // beyond the current default value; the report itself is unaffected.
    }
  }

  async function fetchTargets(): Promise<void> {
    try {
      const res = await apiGet<ProductionAchievementTargetRow[]>('/api/production-achievement/targets');
      if (res.success) {
        targets.value = Array.isArray(res.data) ? res.data : [];
      }
    } catch {
      targets.value = [];
    }
  }

  /**
   * Params captured once at enqueue time and threaded through the entire
   * poll -> tail-refetch -> render cycle for a single runQuery() call (same
   * "snapshot committed params" precedent as production-achievement-async
   * -spool). Mode/station cannot actually change mid-flight any more (OD-4 is
   * now enforced earlier, at the setMode/setWorkcenterGroup call site), but
   * the snapshot is kept as defense-in-depth and because start_date/end_date
   * are RESOLVED values (today/yesterday/month compute their own window every
   * call) that must stay fixed across the tail re-GET regardless.
   */
  interface QuerySnapshot {
    mode: ProductionAchievementMode;
    start_date: string;
    end_date: string;
    workcenter_group: string;
  }

  let _lastSnapshot: QuerySnapshot | null = null;

  function _resolveSnapshotDates(mode: ProductionAchievementMode, now: Date): { start_date: string; end_date: string } {
    if (mode === 'today') {
      const d = formatLocalDate(now);
      return { start_date: d, end_date: d };
    }
    if (mode === 'yesterday') {
      const y = new Date(now);
      y.setDate(y.getDate() - 1);
      const d = formatLocalDate(y);
      return { start_date: d, end_date: d };
    }
    if (mode === 'month') {
      const period = resolveMonthPeriod(now);
      return { start_date: period.start, end_date: period.end };
    }
    // range (OD-2: always cumulative-style, even a single day)
    const todayStr = formatLocalDate(now);
    const rawStart = filters.start_date || todayStr;
    const rawEnd = filters.end_date || todayStr;
    const end = rawEnd > todayStr ? todayStr : rawEnd; // never a future end_date (PA-13)
    return { start_date: rawStart, end_date: end };
  }

  async function _fetchReportOnce(snapshot: QuerySnapshot): Promise<ReportSpoolHit | ReportAsyncEnqueued> {
    const response = await apiGet<ReportSpoolHit | ReportAsyncEnqueued>('/api/production-achievement/report', {
      timeout: API_TIMEOUT,
      params: { start_date: snapshot.start_date, end_date: snapshot.end_date, workcenter_group: snapshot.workcenter_group },
    });
    return unwrapApiData(response, '查詢失敗，請稍後再試') as ReportSpoolHit | ReportAsyncEnqueued;
  }

  const MAX_TAIL_REENQUEUE_ATTEMPTS = 2;

  /**
   * Poll the enqueued job to completion, then re-issue the identical
   * GET /report (bound to the immutable `snapshot`) — the canonical spool now
   * exists, so the second call normally takes the 200 spool-hit path at zero
   * Oracle cost (data-shape-contract.md §3.28.4).
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
      _resetAsyncProgress();
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
    asyncJobProgress.status = 'finished';
    asyncJobProgress.progress = '正在載入結果…';
    asyncJobProgress.pct = 100;

    const data = await _fetchReportOnce(snapshot);

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

  function _clearRows(): void {
    dailyRows.value = [];
    cumulativeRows.value = [];
    cumulativeTrend.value = [];
  }

  /** Re-run computeDailyView/computeCumulativeView against the ALREADY-cached
   *  DuckDB tables (no spool re-fetch) for the given mode/date-window. */
  async function _recompute(mode: ProductionAchievementMode, startDate: string, endDate: string, workcenterGroup: string): Promise<void> {
    if (mode === 'today' || mode === 'yesterday') {
      dailyRows.value = await duckdb.computeDailyView({ workcenterGroup });
      cumulativeRows.value = [];
      cumulativeTrend.value = [];
    } else {
      const result = await duckdb.computeCumulativeView({ workcenterGroup, startDate, endDate });
      cumulativeRows.value = result.rows;
      cumulativeTrend.value = result.trend;
      dailyRows.value = [];
    }
  }

  /** Hand the spool-hit response to DuckDB-WASM and render the computed rows. */
  async function _activateAndRender(data: ReportSpoolHit, snapshot: QuerySnapshot): Promise<void> {
    await duckdb.activate(
      data.spool_download_url,
      data.spec_workcenter_map || [],
      data.targets_map || [],
      data.package_lf_map || [],
      data.workcenter_merge_map || [],
      data.daily_plan_map || [],
    );
    await _recompute(snapshot.mode, snapshot.start_date, snapshot.end_date, snapshot.workcenter_group);
  }

  async function runQuery(): Promise<void> {
    if (loading.value) return;
    error.value = '';
    loading.value = true;
    hasQueried.value = true;
    _resetAsyncProgress();
    duckdb.deactivate();
    const mode = filters.mode;
    const { start_date, end_date } = _resolveSnapshotDates(mode, new Date());
    const snapshot: QuerySnapshot = { mode, start_date, end_date, workcenter_group: filters.workcenter_group };
    try {
      const data = await _fetchReport(snapshot);
      if (!data) {
        // Cancelled mid-poll or the poll failed — error.value (if any) is
        // already set by _pollForCompletion(); table renders empty, not an error.
        _clearRows();
        return;
      }
      await _activateAndRender(data, snapshot);
      _lastSnapshot = snapshot;
    } catch (err: unknown) {
      _clearRows();
      error.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
    } finally {
      loading.value = false;
      _resetAsyncProgress();
    }
  }

  // ── Mode / station mutation entry points (OD-3 auto-run, OD-4 ignore-mid-poll, OD-7 persist) ──

  /** 4-button mode switch (當日/前日/當月/自訂區間). Auto-runs (OD-3); ignored while a poll is in flight (OD-4). */
  function setMode(mode: ProductionAchievementMode): void {
    if (loading.value) return; // OD-4: mid-poll change is a pure no-op
    if (filters.mode === mode) return; // Reversibility: re-selecting the current mode is free (no new fetch)
    filters.mode = mode;
    if (mode === 'range' && (!filters.start_date || !filters.end_date)) {
      const todayStr = formatLocalDate(new Date());
      if (!filters.start_date) filters.start_date = todayStr;
      if (!filters.end_date) filters.end_date = todayStr;
    }
    persistState(filters.mode, filters.workcenter_group);
    void runQuery();
  }

  /**
   * Station-group single-select. Auto-runs (OD-3); ignored while a poll is in
   * flight (OD-4). When a spool is already active, this is a pure client-side
   * re-filter against the cached DuckDB tables — the canonical spool key is
   * date-range only (PA-08), so no new /report fetch is needed.
   */
  function setWorkcenterGroup(group: string): void {
    if (loading.value) return; // OD-4
    if (filters.workcenter_group === group) return;
    filters.workcenter_group = group;
    persistState(filters.mode, filters.workcenter_group);
    if (duckdb.isActive.value && _lastSnapshot) {
      void _recompute(_lastSnapshot.mode, _lastSnapshot.start_date, _lastSnapshot.end_date, group);
    } else {
      void runQuery();
    }
  }

  /** 自訂區間 date inputs. Auto-runs (OD-3); ignored while a poll is in flight (OD-4). */
  function setRangeDates(startDate: string, endDate: string): void {
    if (loading.value) return; // OD-4
    filters.start_date = startDate;
    filters.end_date = endDate;
    void runQuery();
  }

  async function saveTarget(payload: { shift_code: string; workcenter_group: string; target_qty: number }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await apiPut<null>('/api/production-achievement/targets', payload);
      await fetchTargets();
      // Re-render immediately from the refreshed target list. A target-value
      // PUT never changes the spooled report data (only PA-07's join input)
      // -- when DuckDB is already active for this session, recompute
      // client-side (zero Oracle/spool cost) instead of re-issuing the async report.
      if (hasQueried.value) {
        if (duckdb.isActive.value && _lastSnapshot) {
          const targetsMap: TargetsMapRow[] = targets.value.map((t) => ({
            shift_code: t.shift_code,
            workcenter_group: t.workcenter_group,
            target_qty: t.target_qty,
          }));
          await duckdb.updateTargetsMap(targetsMap);
          await _recompute(_lastSnapshot.mode, _lastSnapshot.start_date, _lastSnapshot.end_date, _lastSnapshot.workcenter_group);
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

  return {
    filters,
    filterOptions,
    dailyRows,
    cumulativeRows,
    cumulativeTrend,
    viewKind,
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
    setMode,
    setWorkcenterGroup,
    setRangeDates,
    saveTarget,
    cancelQuery,
  };
}
