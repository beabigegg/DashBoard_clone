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
 *
 * The legacy shift-keyed target-value editor (GET/PUT
 * /api/production-achievement/targets) was removed from this page's UI —
 * targets_map is still fetched inline with the report response and handed to
 * DuckDB (see ReportSpoolHit/_activateAndRender below) but is no longer
 * user-editable here.
 */
import { computed, reactive, ref } from 'vue';
import { apiGet, apiPost } from '../../core/api';
import { unwrapApiData } from '../../core/unwrap-api-result';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import { useProductionAchievementDuckDB } from './useProductionAchievementDuckDB';
import type {
  SpecWorkcenterMapRow,
  TargetsMapRow,
  PackageLfMapRow,
  WorkcenterMergeMapRow,
  PlanMapRow,
  DailyViewRow,
  CumulativeViewRow,
  CumulativeTrendPoint,
  ProductionSourceMode,
} from './useProductionAchievementDuckDB';

export type ProductionAchievementMode = 'today' | 'yesterday' | 'month' | 'range';
export type { ProductionSourceMode } from './useProductionAchievementDuckDB';

export interface FilterState {
  mode: ProductionAchievementMode;
  /** PA-18: 產出 (output) vs 轉出 (moveout) data source, TAB-switched. */
  source: ProductionSourceMode;
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
  plan_map: PlanMapRow[];
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
const DEFAULT_SOURCE: ProductionSourceMode = 'output';
const DEFAULT_WORKCENTER_GROUP = '焊接_DB';
const VALID_MODES: ProductionAchievementMode[] = ['today', 'yesterday', 'month', 'range'];
const VALID_SOURCES: ProductionSourceMode[] = ['output', 'moveout'];

// OD-7: survives a full page navigation to /production-achievement-settings
// and back (separate mini-app — no in-memory store can bridge that round-trip).
const PERSIST_KEY = 'production-achievement:last-report-state';

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
  source: ProductionSourceMode;
  workcenter_group: string;
}

function readPersistedState(): PersistedReportState {
  try {
    const raw = sessionStorage.getItem(PERSIST_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<PersistedReportState>;
      const mode = VALID_MODES.includes(parsed.mode as ProductionAchievementMode) ? (parsed.mode as ProductionAchievementMode) : DEFAULT_MODE;
      const source = VALID_SOURCES.includes(parsed.source as ProductionSourceMode) ? (parsed.source as ProductionSourceMode) : DEFAULT_SOURCE;
      const workcenter_group =
        typeof parsed.workcenter_group === 'string' && parsed.workcenter_group ? parsed.workcenter_group : DEFAULT_WORKCENTER_GROUP;
      return { mode, source, workcenter_group };
    }
  } catch {
    // sessionStorage unavailable (e.g. private browsing quota) — fall back to defaults
  }
  return { mode: DEFAULT_MODE, source: DEFAULT_SOURCE, workcenter_group: DEFAULT_WORKCENTER_GROUP };
}

function persistState(mode: ProductionAchievementMode, source: ProductionSourceMode, workcenter_group: string): void {
  try {
    sessionStorage.setItem(PERSIST_KEY, JSON.stringify({ mode, source, workcenter_group }));
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
    source: persisted.source,
    workcenter_group: persisted.workcenter_group,
    start_date: '',
    end_date: '',
  });

  const filterOptions = reactive<{ workcenter_groups: string[] }>({
    workcenter_groups: [],
  });

  // PA-19: parent_group (大項) -> set of子站 (merged_workcenter_group) under it,
  // rebuilt from each report response's workcenter_merge_map. A selection whose
  // parent has >1子站 (電鍍/切割) is rendered EXPANDED in the detail table.
  const _parentChildren = new Map<string, Set<string>>();

  function _rebuildParentChildren(rows: WorkcenterMergeMapRow[]): void {
    _parentChildren.clear();
    for (const r of rows) {
      const parent = r.parent_group || r.merged_workcenter_group;
      if (!parent) continue;
      if (!_parentChildren.has(parent)) _parentChildren.set(parent, new Set());
      _parentChildren.get(parent)!.add(r.merged_workcenter_group);
    }
  }

  function _isExpanded(group: string): boolean {
    const children = _parentChildren.get(group);
    return !!children && children.size > 1;
  }

  /** Whether the currently-selected station renders as an expanded 大項 (PA-19). */
  const isExpandedSelection = computed(() => _isExpanded(filters.workcenter_group));

  const dailyRows = ref<DailyViewRow[]>([]);
  const cumulativeRows = ref<CumulativeViewRow[]>([]);
  const cumulativeTrend = ref<CumulativeTrendPoint[]>([]);
  const loading = ref(false);
  const error = ref('');
  const hasQueried = ref(false);

  const viewKind = computed<'daily' | 'cumulative'>(() =>
    filters.mode === 'today' || filters.mode === 'yesterday' ? 'daily' : 'cumulative',
  );

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
    source: ProductionSourceMode;
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

  /**
   * @param forceRefresh clears the ACTUAL-output spool for this exact
   *   query_id server-side (always takes the 202 enqueue branch — see
   *   production_achievement_routes.py's api_get_report docstring).
   * @param refreshPlan independently forces the Oracle plan/target cache
   *   (PA-11, CACHE_TTL_PRODUCTION_ACHIEVEMENT_PLAN) to bypass its TTL and
   *   re-query Oracle. Kept SEPARATE from forceRefresh: the tail re-fetch
   *   inside _pollForCompletion below must never re-send force_refresh=true
   *   (that would re-clear the spool THAT job just finished computing and
   *   loop forever) but still needs to force a fresh plan_map so 重新查詢
   *   never leaves 實際產出 fresh while the achievement-rate denominator
   *   stays stale.
   */
  async function _fetchReportOnce(snapshot: QuerySnapshot, forceRefresh = false, refreshPlan = false): Promise<ReportSpoolHit | ReportAsyncEnqueued> {
    const params: Record<string, string> = {
      start_date: snapshot.start_date,
      end_date: snapshot.end_date,
      workcenter_group: snapshot.workcenter_group,
      source: snapshot.source,
    };
    if (forceRefresh) params.force_refresh = 'true';
    if (refreshPlan) params.refresh_plan = 'true';
    const response = await apiGet<ReportSpoolHit | ReportAsyncEnqueued>('/api/production-achievement/report', {
      timeout: API_TIMEOUT,
      params,
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
    refreshPlan = false,
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

    // Never re-send force_refresh=true here — the spool this job JUST
    // computed would be immediately re-cleared, re-enqueuing forever.
    // refreshPlan carries forward independently (see _fetchReportOnce's doc).
    const data = await _fetchReportOnce(snapshot, false, refreshPlan);

    if (isAsyncEnqueued(data)) {
      if (attempt >= MAX_TAIL_REENQUEUE_ATTEMPTS) {
        _resetAsyncProgress();
        error.value = '查詢完成但結果尚未就緒，請稍後重試';
        return null;
      }
      return _pollForCompletion(data, snapshot, refreshPlan, attempt + 1);
    }
    return data as ReportSpoolHit;
  }

  async function _fetchReport(snapshot: QuerySnapshot, forceRefresh = false): Promise<ReportSpoolHit | null> {
    const data = await _fetchReportOnce(snapshot, forceRefresh);
    if (isAsyncEnqueued(data)) {
      // A force-refreshed request's tail re-fetch must still force a fresh
      // plan_map once it lands on the 200 branch (see _pollForCompletion).
      return _pollForCompletion(data, snapshot, forceRefresh);
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
    // PA-19: a selection whose 大項 has >1子站 (電鍍/切割) renders expanded
    // (rows split per子站 + 大項小計 computed in the view layer).
    const expand = _isExpanded(workcenterGroup);
    if (mode === 'today' || mode === 'yesterday') {
      // today/yesterday are always a single day (start_date === end_date,
      // see _resolveSnapshotDates) — outputDate scopes computeDailyView to
      // exactly that day so the preceding day's overnight N-shift tail
      // (captured by this query's own fetch window, PA-03) never bleeds in.
      dailyRows.value = await duckdb.computeDailyView({ workcenterGroup, outputDate: startDate, expand });
      cumulativeRows.value = [];
      cumulativeTrend.value = [];
    } else {
      const result = await duckdb.computeCumulativeView({ workcenterGroup, startDate, endDate, expand });
      cumulativeRows.value = result.rows;
      cumulativeTrend.value = result.trend;
      dailyRows.value = [];
    }
  }

  /** Hand the spool-hit response to DuckDB-WASM and render the computed rows. */
  async function _activateAndRender(data: ReportSpoolHit, snapshot: QuerySnapshot): Promise<void> {
    _rebuildParentChildren(data.workcenter_merge_map || []);
    await duckdb.activate(
      data.spool_download_url,
      data.spec_workcenter_map || [],
      data.targets_map || [],
      data.package_lf_map || [],
      data.workcenter_merge_map || [],
      data.plan_map || [],
      snapshot.source,
    );
    await _recompute(snapshot.mode, snapshot.start_date, snapshot.end_date, snapshot.workcenter_group);
  }

  async function runQuery(options?: { forceRefresh?: boolean }): Promise<void> {
    if (loading.value) return;
    error.value = '';
    loading.value = true;
    hasQueried.value = true;
    _resetAsyncProgress();
    duckdb.deactivate();
    const mode = filters.mode;
    const { start_date, end_date } = _resolveSnapshotDates(mode, new Date());
    const snapshot: QuerySnapshot = { mode, source: filters.source, start_date, end_date, workcenter_group: filters.workcenter_group };
    try {
      const data = await _fetchReport(snapshot, options?.forceRefresh ?? false);
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
    persistState(filters.mode, filters.source, filters.workcenter_group);
    void runQuery();
  }

  /**
   * PA-18: 產出 / 轉出 data-source TAB. Switching source = a wholly different
   * dataset (different Oracle source table + spool namespace), so this always
   * triggers a full re-fetch + re-activate, never a client-side re-filter.
   * Ignored while a poll is in flight (OD-4).
   */
  function setSource(source: ProductionSourceMode): void {
    if (loading.value) return; // OD-4
    if (filters.source === source) return;
    filters.source = source;
    persistState(filters.mode, filters.source, filters.workcenter_group);
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
    persistState(filters.mode, filters.source, filters.workcenter_group);
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

  /**
   * Manual 重新查詢 button (當日/前日/當月 tabs only). Unconditionally
   * re-fetches the CURRENT mode's date window from Oracle -- ``force_refresh``
   * makes the server discard any existing spool for that query_id before the
   * hit check, so this can never resolve to a stale cached snapshot the way
   * the plain 200 spool-hit path can (see production_achievement_daily_cache.py
   * root-cause fix: the scheduled warmup only refreshes "today" on its own
   * hourly cycle -- this is the user-facing "don't wait for it" escape hatch,
   * and it's the only way to force a fresh fetch for 前日/當月 at all, since
   * those aren't covered by the warmup scheduler). Same OD-4 no-op-while-
   * loading guard as every other entry point -- runQuery() itself enforces it.
   */
  function refreshQuery(): Promise<void> {
    return runQuery({ forceRefresh: true });
  }

  /**
   * PA-17: pre-check `can_edit_targets` before navigating to
   * /production-achievement-settings, so a not-whitelisted user gets an
   * inline message instead of a wasted round-trip into a page they can only
   * read. A network/parse failure is treated the same as an explicit deny
   * ('error', a distinct reason string so the caller can show a different
   * message) -- fail-closed, matching can_edit_targets()'s own contract.
   * Does NOT change /production-achievement-settings' own route-level
   * visibility (still readable via direct URL by any released user) -- this
   * is a client-side UX gate on the button only.
   */
  async function checkSettingsAccess(): Promise<'allowed' | 'denied' | 'error'> {
    try {
      const res = await apiGet<{ can_edit_targets: boolean }>('/api/production-achievement/permissions/me');
      if (res.success && res.data) {
        return res.data.can_edit_targets ? 'allowed' : 'denied';
      }
      return 'error';
    } catch {
      return 'error';
    }
  }

  return {
    filters,
    filterOptions,
    dailyRows,
    cumulativeRows,
    cumulativeTrend,
    viewKind,
    isExpandedSelection,
    loading,
    error,
    hasQueried,
    asyncJobProgress,
    fetchFilterOptions,
    runQuery,
    refreshQuery,
    setMode,
    setSource,
    setWorkcenterGroup,
    setRangeDates,
    cancelQuery,
    checkSettingsAccess,
  };
}
