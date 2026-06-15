import { ref, reactive } from 'vue';
import { apiGet, apiPost } from '../../core/api';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import type {
  DowntimeKpiShape,
  DailyTrendRow,
  BigCategoryRow,
  TopReasonRow,
  EquipmentDetailRow,
  EventDetailRow,
  Pagination,
  FilterOptions,
  ChartFilter,
} from '../types';
import type { TaxonomyShape } from './useDowntimeDuckDB';

const API_TIMEOUT = 360000;

/** Async-job progress state surfaced to App.vue for the AsyncQueryProgress component. */
export interface DowntimeAsyncJobProgress {
  active: boolean;
  jobId: string | null;
  status: string | null;
  progress: string;
  pct: number;
  elapsedSeconds: number;
}

interface SummaryData {
  summary: DowntimeKpiShape;
  daily_trend: DailyTrendRow[];
  big_category: BigCategoryRow[];
  top_reasons: TopReasonRow[];
}

interface EventDetailData {
  rows: EventDetailRow[];
  pagination: Pagination;
}

const defaultKpi: DowntimeKpiShape = {
  total_hours: 0,
  udt_hours: 0,
  sdt_hours: 0,
  egt_hours: 0,
  event_count: 0,
  avg_event_min: 0,
};

/**
 * useDowntimeData — two-phase data fetching for downtime-analysis.
 *
 * Phase 1: POST /api/downtime-analysis/query → get query_id + initial view data
 * Phase 2: GET /api/downtime-analysis/view?query_id=... for granularity re-group
 *
 * Handles 410 cache_expired → re-query.
 */
export function useDowntimeData() {
  const queryId = ref('');

  /** Present when server responds with browser-DuckDB shape (flag on). */
  const duckdbSpoolUrls = ref<{
    base_spool_url: string;
    jobs_spool_url: string;
    taxonomy: TaxonomyShape;
    resource_lookup: Record<string, { resource_name: string | null; workcenter: string | null; family: string | null }>;
  } | null>(null);

  const loading = reactive({
    initial: false,
    querying: false,
    equipment: false,
    events: false,
    options: false,
  });

  const error = ref('');

  /** Async job progress state — driven by pollJobUntilComplete when the route returns 202. */
  const asyncJobProgress = reactive<DowntimeAsyncJobProgress>({
    active: false,
    jobId: null,
    status: null,
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

  /**
   * Cancel the currently running async job.
   * Aborts the polling loop; the progress bar will be dismissed by the caller.
   * Also calls the abandon endpoint so the server-side job is terminated.
   */
  async function cancelAsyncJob(): Promise<void> {
    const jobId = asyncJobProgress.jobId;
    if (_jobAbortController) {
      _jobAbortController.abort();
      _jobAbortController = null;
    }
    _stopElapsedTimer();
    asyncJobProgress.active = false;
    asyncJobProgress.jobId = null;

    // Best-effort abandon — do not surface errors to the user
    if (jobId) {
      try {
        await apiPost(`/api/job/${jobId}/abandon`, {}, { silent: true, timeout: 10000 });
      } catch {
        // Non-fatal: abandon is best-effort
      }
    }
  }

  const summaryData = reactive<SummaryData>({
    summary: { ...defaultKpi },
    daily_trend: [],
    big_category: [],
    top_reasons: [],
  });

  const equipmentData = reactive<{ rows: EquipmentDetailRow[]; pagination: Pagination }>({
    rows: [],
    pagination: { page: 1, page_size: 20, total_rows: 0, total_pages: 0 },
  });

  const eventData = reactive<EventDetailData>({
    rows: [],
    pagination: { page: 1, page_size: 20, total_rows: 0, total_pages: 0 },
  });

  const filterOptions = reactive<FilterOptions>({
    workcenter_groups: [],
    families: [],
    resources: [],
    package_groups: [],
    big_categories: [],
    reasons: [],
  });

  /**
   * Load filter options from GET /api/downtime-analysis/options.
   */
  async function loadOptions(): Promise<void> {
    loading.options = true;
    error.value = '';
    try {
      const response = await apiGet('/api/downtime-analysis/options', {
        timeout: API_TIMEOUT,
        silent: true,
      });
      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (data) {
        filterOptions.workcenter_groups = Array.isArray(data.workcenter_groups) ? (data.workcenter_groups as string[]) : [];
        filterOptions.families = Array.isArray(data.families) ? (data.families as string[]) : [];
        filterOptions.resources = Array.isArray(data.resources) ? (data.resources as string[]) : [];
        filterOptions.package_groups = Array.isArray(data.package_groups) ? (data.package_groups as string[]) : [];
        filterOptions.big_categories = Array.isArray(data.big_categories) ? (data.big_categories as string[]) : [];
        filterOptions.reasons = Array.isArray(data.reasons) ? (data.reasons as string[]) : [];
      }
    } catch (err) {
      error.value = (err as Error)?.message || '載入篩選選項失敗';
    } finally {
      loading.options = false;
    }
  }

  /**
   * Execute primary query: POST /api/downtime-analysis/query
   *
   * Three possible response shapes:
   *   1. HTTP 202 `{async: true, job_id, status_url}` — long-range RQ async path:
   *      poll the job status URL until finished, then read result.query_id and
   *      load both parquet spools (browser-DuckDB path).
   *   2. HTTP 200 with `{base_spool_url, jobs_spool_url, taxonomy}` — short-range
   *      browser-DuckDB path (DOWNTIME_BROWSER_DUCKDB=true or short range): caller
   *      activates DuckDB-WASM.
   *   3. HTTP 200 legacy shape with `{summary, daily_trend, big_category, top_reasons}` —
   *      flag-off / sync fallback: apply view data directly.
   *
   * AC-5: the sync (200) path is byte-identical to the pre-change behavior.
   */
  async function executePrimaryQuery(body: Record<string, unknown>): Promise<void> {
    // Cancel any in-progress async job before starting a new query
    if (_jobAbortController) {
      _jobAbortController.abort();
      _jobAbortController = null;
    }
    asyncJobProgress.active = false;
    asyncJobProgress.jobId = null;
    asyncJobProgress.pct = 0;
    asyncJobProgress.progress = '';
    asyncJobProgress.status = null;
    asyncJobProgress.elapsedSeconds = 0;
    _stopElapsedTimer();

    loading.querying = true;
    loading.initial = true;
    error.value = '';

    try {
      const response = await apiPost('/api/downtime-analysis/query', body, {
        timeout: API_TIMEOUT,
        silent: true,
      });

      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (!data) {
        error.value = '查詢回應格式錯誤';
        return;
      }

      // ── Async 202 path ────────────────────────────────────────────────────
      // Route returned {async: true, job_id, status_url} — long-range RQ job.
      if (data.async === true && data.job_id) {
        const jobId = String(data.job_id);
        // status_url includes the correct ?prefix= for this job type
        const statusUrl = String(data.status_url || `/api/job/${jobId}`);

        asyncJobProgress.active = true;
        asyncJobProgress.jobId = jobId;
        asyncJobProgress.status = 'queued';
        asyncJobProgress.progress = '';
        asyncJobProgress.pct = 0;
        asyncJobProgress.elapsedSeconds = 0;
        _startElapsedTimer();

        // Suspend loading.querying while polling (the progress bar replaces the
        // generic loading state for the duration of the job).
        loading.querying = false;
        loading.initial = false;

        const controller = new AbortController();
        _jobAbortController = controller;

        try {
          const finalStatus = await pollJobUntilComplete(statusUrl, {
            signal: controller.signal,
            onProgress: (statusResp) => {
              asyncJobProgress.status = statusResp.status;
              asyncJobProgress.progress = (statusResp.progress as string) || (statusResp.stage as string) || '';
              asyncJobProgress.pct = typeof statusResp.pct === 'number' ? statusResp.pct : 0;
            },
          });

          // Job finished: read query_id from the flat job status dict.
          // get_job_status() stores query_id at the top level (not nested under "result").
          const statusObj = finalStatus as Record<string, unknown>;
          const resultQueryId = String(statusObj.query_id || '');
          if (!resultQueryId) {
            error.value = '背景查詢完成但未返回 query_id';
            resetSummaryData();
            return;
          }

          // The job writes to the same two namespaces as the sync path.
          // Construct the spool URLs using the canonical pattern.
          const baseSpoolUrl = `/api/spool/downtime_analysis_base_events/${resultQueryId}.parquet`;
          const jobsSpoolUrl = `/api/spool/downtime_analysis_job_bridge/${resultQueryId}.parquet`;

          queryId.value = resultQueryId;
          duckdbSpoolUrls.value = {
            base_spool_url: baseSpoolUrl,
            jobs_spool_url: jobsSpoolUrl,
            // taxonomy is not in the job status response; use empty structure.
            // The browser-DuckDB composable handles missing taxonomy gracefully.
            taxonomy: {
              map: [],
              prefixes: [],
              egt_category: '',
              fallback: '',
            },
            resource_lookup: {},
          };
          // Reset pre-aggregated summary data — all views come from DuckDB-WASM
          resetSummaryData();
        } catch (err) {
          const e = err as Error & { errorCode?: string };
          if (e?.name === 'AbortError') {
            // User cancelled — leave error blank; App.vue handles UI state
          } else if (e?.errorCode === 'JOB_FAILED') {
            error.value = e?.message || '背景查詢失敗';
            resetSummaryData();
          } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
            error.value = '背景查詢超時，請縮小日期範圍後重試';
            resetSummaryData();
          } else {
            error.value = (e as Error)?.message || '背景查詢發生錯誤';
            resetSummaryData();
          }
        } finally {
          if (_jobAbortController === controller) _jobAbortController = null;
          _stopElapsedTimer();
          asyncJobProgress.active = false;
        }
        return;
      }

      // ── Sync 200 path (unchanged from pre-change behavior, AC-5) ─────────
      queryId.value = String(data.query_id || '');

      // Detect browser-DuckDB shape (flag on): has base_spool_url + jobs_spool_url + taxonomy
      if (data.base_spool_url && data.jobs_spool_url && data.taxonomy) {
        duckdbSpoolUrls.value = {
          base_spool_url: String(data.base_spool_url),
          jobs_spool_url: String(data.jobs_spool_url),
          taxonomy: data.taxonomy as TaxonomyShape,
          resource_lookup: (data.resource_lookup as Record<string, { resource_name: string | null; workcenter: string | null; family: string | null }>) ?? {},
        };
        // Flag-on path: server does NOT return legacy view keys; reset them
        resetSummaryData();
      } else {
        // Flag-off path: legacy shape with summary/daily_trend/big_category/top_reasons
        duckdbSpoolUrls.value = null;
        applyViewResult(data);
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e?.name === 'AbortError') {
        error.value = '查詢逾時，請縮小日期範圍後重試';
      } else {
        error.value = e?.message || '查詢失敗';
      }
      resetSummaryData();
    } finally {
      loading.querying = false;
      loading.initial = false;
    }
  }

  /**
   * Apply granularity view: GET /api/downtime-analysis/view?query_id=&granularity=
   * Handles 410 cache_expired → triggers re-query via callback.
   */
  async function applyView(granularity: string, onCacheExpired?: () => Promise<void>): Promise<void> {
    if (!queryId.value) return;

    loading.querying = true;
    error.value = '';

    try {
      const response = await apiGet('/api/downtime-analysis/view', {
        timeout: API_TIMEOUT,
        silent: true,
        params: { query_id: queryId.value, granularity },
      });

      const resp = response as Record<string, unknown>;
      if (resp?.success === false) {
        const errObj = resp?.error as Record<string, unknown> | string | undefined;
        const code = typeof errObj === 'object' ? errObj?.code : errObj;
        if (code === 'cache_expired' || (resp as Record<string, unknown>)?.status === 410) {
          if (onCacheExpired) {
            await onCacheExpired();
          }
          return;
        }
      }

      const data = resp?.data as Record<string, unknown> | undefined;
      if (data) {
        applyViewResult(data);
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e?.status === 410 || e?.message === 'cache_expired') {
        if (onCacheExpired) {
          await onCacheExpired();
        }
        return;
      }
      error.value = e?.message || '取得檢視資料失敗';
    } finally {
      loading.querying = false;
    }
  }

  /**
   * Load equipment detail: GET /api/downtime-analysis/equipment-detail?query_id=&page=&page_size=
   */
  async function loadEquipmentDetail(page = 1, pageSize = 20): Promise<void> {
    if (!queryId.value) return;

    loading.equipment = true;
    error.value = '';

    try {
      const response = await apiGet('/api/downtime-analysis/equipment-detail', {
        timeout: API_TIMEOUT,
        silent: true,
        params: { query_id: queryId.value, page, page_size: pageSize },
      });

      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (data) {
        equipmentData.rows = Array.isArray(data.equipment_detail) ? (data.equipment_detail as EquipmentDetailRow[]) : [];
        const pag = data.pagination as Partial<Pagination> | undefined;
        equipmentData.pagination = {
          page: Number(pag?.page ?? page),
          page_size: Number(pag?.page_size ?? pageSize),
          total_rows: Number(pag?.total_rows ?? 0),
          total_pages: Number(pag?.total_pages ?? 0),
        };
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e?.status === 410 || e?.message === 'cache_expired') {
        error.value = '快取已過期，請重新查詢';
      } else {
        error.value = e?.message || '載入設備明細失敗';
      }
    } finally {
      loading.equipment = false;
    }
  }

  /**
   * Load event detail: GET /api/downtime-analysis/event-detail?query_id=&page=&page_size=
   */
  async function loadEventDetail(page = 1, pageSize = 20): Promise<void> {
    if (!queryId.value) return;

    loading.events = true;
    error.value = '';

    try {
      const response = await apiGet('/api/downtime-analysis/event-detail', {
        timeout: API_TIMEOUT,
        silent: true,
        params: { query_id: queryId.value, page, page_size: pageSize },
      });

      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (data) {
        eventData.rows = Array.isArray(data.events) ? (data.events as EventDetailRow[]) : [];
        const pag = data.pagination as Partial<Pagination> | undefined;
        eventData.pagination = {
          page: Number(pag?.page ?? page),
          page_size: Number(pag?.page_size ?? pageSize),
          total_rows: Number(pag?.total_rows ?? 0),
          total_pages: Number(pag?.total_pages ?? 0),
        };
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e?.status === 410 || e?.message === 'cache_expired') {
        error.value = '快取已過期，請重新查詢';
      } else {
        error.value = e?.message || '載入事件明細失敗';
      }
    } finally {
      loading.events = false;
    }
  }

  function applyViewResult(data: Record<string, unknown>): void {
    const summary = data.summary as DowntimeKpiShape | undefined;
    summaryData.summary = summary
      ? { ...defaultKpi, ...summary }
      : { ...defaultKpi };

    summaryData.daily_trend = Array.isArray(data.daily_trend) ? (data.daily_trend as DailyTrendRow[]) : [];
    summaryData.big_category = Array.isArray(data.big_category) ? (data.big_category as BigCategoryRow[]) : [];
    summaryData.top_reasons = Array.isArray(data.top_reasons) ? (data.top_reasons as TopReasonRow[]) : [];
  }

  async function exportEquipmentDetailCsv(): Promise<void> {
    if (!queryId.value) return;
    const url = `/api/downtime-analysis/export-equipment-detail?query_id=${encodeURIComponent(queryId.value)}`;
    const response = await fetch(url);
    if (!response.ok) {
      error.value = '設備明細匯出失敗';
      return;
    }
    const blob = await response.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'downtime_equipment_detail.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function exportEventDetailCsv(): Promise<void> {
    if (!queryId.value) return;
    const url = `/api/downtime-analysis/export-event-detail?query_id=${encodeURIComponent(queryId.value)}`;
    const response = await fetch(url);
    if (!response.ok) {
      error.value = '事件明細匯出失敗';
      return;
    }
    const blob = await response.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'downtime_event_detail.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function resetSummaryData(): void {
    summaryData.summary = { ...defaultKpi };
    summaryData.daily_trend = [];
    summaryData.big_category = [];
    summaryData.top_reasons = [];
    equipmentData.rows = [];
    equipmentData.pagination = { page: 1, page_size: 20, total_rows: 0, total_pages: 0 };
    eventData.rows = [];
    eventData.pagination = { page: 1, page_size: 20, total_rows: 0, total_pages: 0 };
  }

  /**
   * Fetch filtered big_category and top_reasons from /view with optional status_types.
   * Updates only summaryData.big_category and summaryData.top_reasons — not summary or daily_trend.
   * Called when KPI card filter changes so BigCategoryChart and TopReasonsTable stay in sync.
   */
  async function loadChartFilterView(statusTypes: string[] | null): Promise<void> {
    if (!queryId.value) return;
    try {
      const params: Record<string, unknown> = { query_id: queryId.value };
      if (statusTypes && statusTypes.length > 0) {
        params.status_types = statusTypes.join(',');
      }
      const response = await apiGet('/api/downtime-analysis/view', {
        timeout: API_TIMEOUT,
        silent: true,
        params,
      });
      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (data) {
        if (Array.isArray(data.big_category)) {
          summaryData.big_category = data.big_category as BigCategoryRow[];
        }
        if (Array.isArray(data.top_reasons)) {
          summaryData.top_reasons = data.top_reasons as TopReasonRow[];
        }
        const s = data.summary as Partial<DowntimeKpiShape> | undefined;
        if (s) {
          if (s.event_count !== undefined) summaryData.summary.event_count = s.event_count;
          if (s.avg_event_min !== undefined) summaryData.summary.avg_event_min = s.avg_event_min;
        }
      }
    } catch {
      // Non-fatal: chart filter view update fails silently
    }
  }

  /**
   * Load all equipment detail in a single full page (page_size=1000, DQ-2).
   * Accepts optional ChartFilter to narrow results by big_category / status_types.
   * Overwrites equipmentData.rows and equipmentData.pagination.
   */
  async function loadAllEquipmentDetail(filter: ChartFilter): Promise<void> {
    if (!queryId.value) return;

    loading.equipment = true;
    error.value = '';

    try {
      const params: Record<string, unknown> = {
        query_id: queryId.value,
        page_size: 1000,
      };
      if (filter.big_category) {
        params.big_category = filter.big_category;
      }
      if (filter.status_types && filter.status_types.length > 0) {
        params.status_types = filter.status_types.join(',');
      }

      const response = await apiGet('/api/downtime-analysis/equipment-detail', {
        timeout: API_TIMEOUT,
        silent: true,
        params,
      });

      const data = (response as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
      if (data) {
        equipmentData.rows = Array.isArray(data.equipment_detail) ? (data.equipment_detail as EquipmentDetailRow[]) : [];
        const pag = data.pagination as Partial<Pagination> | undefined;
        equipmentData.pagination = {
          page: Number(pag?.page ?? 1),
          page_size: Number(pag?.page_size ?? 200),
          total_rows: Number(pag?.total_rows ?? 0),
          total_pages: Number(pag?.total_pages ?? 0),
        };
      }
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e?.status === 410 || e?.message === 'cache_expired') {
        error.value = '快取已過期，請重新查詢';
      } else {
        error.value = e?.message || '載入設備明細失敗';
      }
    } finally {
      loading.equipment = false;
    }
  }

  /**
   * Load events for a single machine+status combination (Tier 3 lazy-load).
   * Returns the events array directly; does NOT overwrite global eventData.
   * Throws an error with message '查詢已過期，請重新查詢' on 410.
   */
  async function loadMachineStatusEvents(
    resourceId: string,
    statusType: string,
    filter: ChartFilter,
  ): Promise<EventDetailRow[]> {
    if (!queryId.value) return [];

    const params: Record<string, unknown> = {
      query_id: queryId.value,
      resource_id: resourceId,
      status_types: statusType,
      page_size: 200,
    };
    if (filter.big_category) {
      params.big_category = filter.big_category;
    }

    const response = await apiGet('/api/downtime-analysis/event-detail', {
      timeout: API_TIMEOUT,
      silent: true,
      params,
    });

    const resp = response as Record<string, unknown>;
    // Handle 410 cache_expired
    if (resp?.success === false) {
      const errObj = resp?.error as Record<string, unknown> | string | undefined;
      const code = typeof errObj === 'object' ? errObj?.code : errObj;
      if (code === 'cache_expired' || resp?.status === 410) {
        throw new Error('查詢已過期，請重新查詢');
      }
    }

    const data = resp?.data as Record<string, unknown> | undefined;
    return Array.isArray(data?.events) ? (data!.events as EventDetailRow[]) : [];
  }

  return {
    queryId,
    duckdbSpoolUrls,
    loading,
    error,
    summaryData,
    equipmentData,
    eventData,
    filterOptions,
    asyncJobProgress,
    loadOptions,
    executePrimaryQuery,
    cancelAsyncJob,
    applyView,
    loadEquipmentDetail,
    loadEventDetail,
    loadAllEquipmentDetail,
    loadChartFilterView,
    loadMachineStatusEvents,
    exportEquipmentDetailCsv,
    exportEventDetailCsv,
    resetSummaryData,
  };
}
