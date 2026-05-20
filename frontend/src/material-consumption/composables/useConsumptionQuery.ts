/**
 * useConsumptionQuery — composable for material-consumption page
 * Change: material-part-consumption
 *
 * API surface:
 *   submitQuery()  → POST /api/material-consumption/query (sync, always)
 *   applyView()    → GET  /api/material-consumption/view?query_id&granularity[&types[]=...] (NO Oracle re-query — MC-03)
 *   submitDetail() → POST /api/material-consumption/detail (sync 200 or async 202)
 *   fetchPage()    → GET  /api/material-consumption/detail/page?query_id=X&page=N
 *   exportCsv()    → POST /api/material-consumption/export (streaming download)
 */

import { ref } from 'vue';
import { apiGet, apiPost } from '../../core/api';

// --- Types ---
export interface ConsumptionKpi {
  total_consumed: number;
  total_required: number;
  efficiency_pct: number;
  lot_count: number;
  workorder_count: number;
}

export interface TrendItem {
  period: string;
  material_part: string;
  total_consumed: number;
}

export interface TypeBreakdownItem {
  period: string;
  pj_type: string | null;
  total_consumed: number;
}

export interface DetailRow {
  material_part?: string;
  containerid?: string;
  pj_workorder?: string;
  workcentername?: string;
  materiallotname?: string;
  qty_required?: number;
  qty_consumed?: number;
  pj_type?: string;
  txn_date?: string;
  [key: string]: unknown;
}

export interface DetailPagination {
  page: number;
  total_pages: number;
  total_rows: number;
  per_page: number;
}

export type Granularity = 'day' | 'week' | 'month' | 'quarter';

export interface QueryParams {
  material_parts: string[];
  start_date: string;
  end_date: string;
  granularity?: Granularity;
}

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 150; // ~5 minutes

export function useConsumptionQuery() {
  // --- Summary query state ---
  const queryId = ref<string | null>(null);
  const kpi = ref<ConsumptionKpi | null>(null);
  const trend = ref<TrendItem[]>([]);
  const typeBreakdown = ref<TypeBreakdownItem[]>([]);
  const isSummaryLoading = ref(false);
  /** isViewLoading — true only during granularity regroup (GET /view); never page-level */
  const isViewLoading = ref(false);
  const summaryError = ref('');
  const currentGranularity = ref<Granularity>('week');

  // --- Detail query state ---
  const detailQueryId = ref<string | null>(null);
  const detailRows = ref<DetailRow[]>([]);
  const detailPagination = ref<DetailPagination>({ page: 1, total_pages: 0, total_rows: 0, per_page: 20 });
  const isDetailLoading = ref(false);
  const detailError = ref('');
  const isDetailAsync = ref(false);
  const pollingJobId = ref<string | null>(null);

  let _pollingTimer: ReturnType<typeof setTimeout> | null = null;
  let _pollingAttempts = 0;

  function _stopPolling() {
    if (_pollingTimer !== null) {
      clearTimeout(_pollingTimer);
      _pollingTimer = null;
    }
    pollingJobId.value = null;
  }

  function _resetSummary() {
    queryId.value = null;
    kpi.value = null;
    trend.value = [];
    typeBreakdown.value = [];
    summaryError.value = '';
  }

  function _resetDetail() {
    _stopPolling();
    detailQueryId.value = null;
    detailRows.value = [];
    detailPagination.value = { page: 1, total_pages: 0, total_rows: 0, per_page: 20 };
    detailError.value = '';
    isDetailAsync.value = false;
  }

  /**
   * submitQuery — POST /api/material-consumption/query
   * Resets ALL state before sending (AC per test: resets_on_new_query_submit)
   */
  async function submitQuery(params: QueryParams): Promise<void> {
    _resetSummary();
    _resetDetail();
    isSummaryLoading.value = true;
    currentGranularity.value = params.granularity ?? 'week';

    try {
      const result = await apiPost<{
        query_id: string;
        kpi: ConsumptionKpi;
        trend: TrendItem[];
        type_breakdown: TypeBreakdownItem[];
      }>('/api/material-consumption/query', params, { timeout: 90000 });

      if (!result.success) {
        summaryError.value = (result as { error?: { message?: string } }).error?.message || '查詢失敗';
        return;
      }

      const data = result.data!;
      queryId.value = data.query_id;
      kpi.value = data.kpi;
      trend.value = data.trend ?? [];
      typeBreakdown.value = data.type_breakdown ?? [];
    } catch (err) {
      summaryError.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
    } finally {
      isSummaryLoading.value = false;
    }
  }

  /**
   * applyView — GET /api/material-consumption/view?query_id=X&granularity=Y[&types[]=...]
   * NEVER re-queries Oracle (MC-03 / AC-3).
   * Accepts optional types filter; builds repeated `types` params via array form
   * so buildUrlWithParams appends repeated keys (backend reads request.args.getlist('types')).
   */
  async function applyView(granularity: Granularity, types?: string[]): Promise<void> {
    if (!queryId.value) return;
    currentGranularity.value = granularity;
    // Use isViewLoading (block-level) — NOT isSummaryLoading (page-level).
    // CSS contract Loading 三層: page-level overlays are for initial global wait only.
    isViewLoading.value = true;
    summaryError.value = '';

    try {
      const params: Record<string, unknown> = {
        query_id: queryId.value,
        granularity,
      };
      if (types && types.length > 0) {
        params['types'] = types; // array → repeated &types=A&types=B via buildUrlWithParams
      }

      const result = await apiGet<{
        trend: TrendItem[];
        type_breakdown: TypeBreakdownItem[];
        kpi: ConsumptionKpi;
      }>(`/api/material-consumption/view`, {
        params,
        timeout: 30000,
      });

      if (!result.success) {
        const errCode = (result as { error?: { code?: string; message?: string } }).error;
        if (errCode?.code === 'CACHE_EXPIRED') {
          summaryError.value = '快取已過期，請重新查詢';
        } else {
          summaryError.value = errCode?.message || '切換粒度/類型失敗';
        }
        return;
      }

      const data = result.data!;
      trend.value = data.trend ?? [];
      typeBreakdown.value = data.type_breakdown ?? [];
      if (data.kpi) kpi.value = data.kpi;
    } catch (err) {
      summaryError.value = err instanceof Error ? err.message : '切換粒度/類型失敗，請稍後再試';
    } finally {
      isViewLoading.value = false;
    }
  }

  /**
   * _pollDetailJob — polls GET /api/material-consumption/detail/job/<id>
   * until status='completed' or 'failed', then fetches page 1.
   */
  function _pollDetailJob(jobId: string) {
    _pollingAttempts = 0;

    function poll() {
      if (pollingJobId.value !== jobId) return; // stale, discard
      _pollingAttempts++;

      if (_pollingAttempts > POLL_MAX_ATTEMPTS) {
        isDetailLoading.value = false;
        _stopPolling();
        detailError.value = '查詢逾時，請重試';
        return;
      }

      apiGet<{ status: string; query_id?: string }>(
        `/api/material-consumption/detail/job/${jobId}`,
        { timeout: 10000 }
      )
        .then((res) => {
          if (pollingJobId.value !== jobId) return;
          const data = res.success ? res.data : undefined;
          const status = String(data?.status || '').toLowerCase();

          if (status === 'completed') {
            detailQueryId.value = data!.query_id ?? null;
            _stopPolling();
            // Fetch first page from spool
            void fetchPage(1);
          } else if (status === 'failed') {
            isDetailLoading.value = false;
            _stopPolling();
            detailError.value = '非同步查詢失敗，請重試';
          } else {
            // pending or running — continue polling
            _pollingTimer = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {
          if (pollingJobId.value === jobId) {
            _pollingTimer = setTimeout(poll, POLL_INTERVAL_MS);
          }
        });
    }

    _pollingTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }

  /**
   * submitDetail — POST /api/material-consumption/detail
   * Returns 200 (sync inline) or 202 (async job).
   */
  async function submitDetail(params: QueryParams): Promise<void> {
    _resetDetail();
    isDetailLoading.value = true;
    isDetailAsync.value = false;
    detailError.value = '';

    try {
      const result = await apiPost<{
        async?: boolean;
        job_id?: string;
        query_id?: string;
        rows?: DetailRow[];
        pagination?: DetailPagination;
      }>('/api/material-consumption/detail', params, { timeout: 90000 });

      if (!result.success) {
        detailError.value = (result as { error?: { message?: string } }).error?.message || '查詢失敗';
        isDetailLoading.value = false;
        return;
      }

      const data = result.data!;

      if (data.async && data.job_id) {
        // 202 async — start polling
        isDetailAsync.value = true;
        pollingJobId.value = data.job_id;
        _pollDetailJob(data.job_id);
        // isDetailLoading stays true until polling resolves
      } else {
        // 200 sync inline
        detailQueryId.value = data.query_id ?? null;
        detailRows.value = data.rows ?? [];
        detailPagination.value = data.pagination ?? { page: 1, total_pages: 1, total_rows: detailRows.value.length, per_page: 20 };
        isDetailLoading.value = false;
      }
    } catch (err) {
      detailError.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
      isDetailLoading.value = false;
    }
  }

  /**
   * fetchPage — GET /api/material-consumption/detail/page?query_id=X&page=N
   */
  async function fetchPage(page: number): Promise<void> {
    if (!detailQueryId.value) return;
    isDetailLoading.value = true;
    detailError.value = '';

    try {
      const result = await apiGet<{
        rows: DetailRow[];
        pagination: DetailPagination;
      }>('/api/material-consumption/detail/page', {
        params: { query_id: detailQueryId.value, page },
        timeout: 30000,
      });

      if (!result.success) {
        detailError.value = (result as { error?: { message?: string } }).error?.message || '載入失敗';
        return;
      }

      const data = result.data!;
      detailRows.value = data.rows ?? [];
      detailPagination.value = data.pagination ?? detailPagination.value;
    } catch (err) {
      detailError.value = err instanceof Error ? err.message : '載入失敗，請稍後再試';
    } finally {
      isDetailLoading.value = false;
    }
  }

  /**
   * exportCsv — POST /api/material-consumption/export → streaming CSV download
   * Uses fetch directly for blob handling (same pattern as material-trace).
   */
  async function exportCsv(params: QueryParams): Promise<void> {
    if (!detailQueryId.value) return;

    try {
      const response = await fetch('/api/material-consumption/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, query_id: detailQueryId.value }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({})) as Record<string, unknown>;
        detailError.value =
          ((data.error as Record<string, unknown> | undefined)?.message as string | undefined) || '匯出失敗';
        return;
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'material_consumption.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      detailError.value = err instanceof Error ? err.message : '匯出失敗，請稍後再試';
    }
  }

  return {
    // Summary
    queryId,
    kpi,
    trend,
    typeBreakdown,
    isSummaryLoading,
    isViewLoading,
    summaryError,
    currentGranularity,
    submitQuery,
    applyView,

    // Detail
    detailQueryId,
    detailRows,
    detailPagination,
    isDetailLoading,
    detailError,
    isDetailAsync,
    pollingJobId,
    submitDetail,
    fetchPage,
    exportCsv,
  };
}
