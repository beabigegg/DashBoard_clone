/**
 * useEapAlarmViews.js
 *
 * Fetches summary, pareto, trend, and detail data from the EAP ALARM spool
 * endpoints (DuckDB-computed, no Oracle re-query). All fine-filter aware.
 */
import { reactive, ref } from 'vue';
import { apiGet } from '../../core/api';
import { useViewStaleness } from '../../shared-composables/useViewStaleness';

const DEFAULT_PER_PAGE = 20;

export function useEapAlarmViews() {
  // ── Loading state ──────────────────────────────────────────────────────────
  const loading = reactive({
    summary: false,
    pareto: false,
    trend: false,
    detail: false,
    filterOptions: false,
  });

  const error = ref('');

  // ── Summary ────────────────────────────────────────────────────────────────
  const summary = reactive({
    total_alarm_count: 0,
    affected_equipment_count: 0,
    affected_lot_count: 0,
    affected_product_line_count: 0,
    unresolved_count: 0,
    avg_duration_minutes: null,
  });

  // ── Pareto ─────────────────────────────────────────────────────────────────
  const pareto = reactive({
    items: [],
    total: 0,
  });

  // Pareto group dimension (backend closed enum: alarm_text/eqp_id/eqp_type/
  // lot_id/pj_type/product_line/pj_bop)
  const paretoDim = ref('alarm_text');

  // ── Trend ──────────────────────────────────────────────────────────────────
  const trend = reactive({
    labels: [],
    series: [],
  });

  const trendGranularity = ref('day');
  // Trend stack dimension (same closed enum as paretoDim)
  const trendGroupBy = ref('alarm_text');

  // ── Detail ─────────────────────────────────────────────────────────────────
  const detail = reactive({
    rows: [],
    meta: {
      page: 1,
      per_page: DEFAULT_PER_PAGE,
      total_count: 0,
      total_pages: 1,
    },
  });

  const detailPage = ref(1);
  const detailPerPage = ref(DEFAULT_PER_PAGE);

  // ── Request staleness (per-endpoint to avoid cross-fetch cancellation) ──
  // Shared composable: a per-key counter so a fast endpoint never invalidates
  // a slow sibling's in-flight request (see useViewStaleness).
  const { nextRequestId, isStaleRequest: isStale } = useViewStaleness([
    'summary',
    'pareto',
    'trend',
  ]);

  // ── Helpers ────────────────────────────────────────────────────────────────

  function buildQueryParams(params) {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const v of value) {
          qs.append(key, v);
        }
      } else if (value !== undefined && value !== null && value !== '') {
        qs.append(key, String(value));
      }
    }
    return qs.toString() ? `?${qs.toString()}` : '';
  }

  function resetAll() {
    summary.total_alarm_count = 0;
    summary.affected_equipment_count = 0;
    summary.affected_lot_count = 0;
    summary.affected_product_line_count = 0;
    summary.unresolved_count = 0;
    summary.avg_duration_minutes = null;
    pareto.items = [];
    pareto.total = 0;
    trend.labels = [];
    trend.series = [];
    detail.rows = [];
    detail.meta = { page: 1, per_page: DEFAULT_PER_PAGE, total_count: 0, total_pages: 1 };
    detailPage.value = 1;
    error.value = '';
  }

  // ── Fetch filter options ──────────────────────────────────────────────────

  async function fetchFilterOptions(queryId) {
    if (!queryId) return null;
    loading.filterOptions = true;
    try {
      const resp = await apiGet(`/api/eap-alarm/filter-options?query_id=${encodeURIComponent(queryId)}`);
      const respObj = resp;
      if (respObj && respObj.success === false) {
        return null;
      }
      return respObj?.data ?? null;
    } catch (err) {
      console.warn('[EAP ALARM] fetchFilterOptions error', err);
      return null;
    } finally {
      loading.filterOptions = false;
    }
  }

  // ── Fetch summary ──────────────────────────────────────────────────────────

  async function fetchSummary(queryId, fineParams) {
    if (!queryId) return;
    loading.summary = true;
    const requestId = nextRequestId('summary');
    try {
      const params = { query_id: queryId, ...fineParams };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/eap-alarm/summary${qs}`);
      if (isStale('summary', requestId)) return;
      const data = resp?.data;
      if (data) {
        summary.total_alarm_count = data.total_alarm_count ?? 0;
        summary.affected_equipment_count = data.affected_equipment_count ?? 0;
        summary.affected_lot_count = data.affected_lot_count ?? 0;
        summary.affected_product_line_count = data.affected_product_line_count ?? 0;
        summary.unresolved_count = data.unresolved_count ?? 0;
        summary.avg_duration_minutes = data.avg_duration_minutes ?? null;
      }
    } catch (err) {
      if (isStale('summary', requestId)) return;
      const msg = String(err?.message || '取得摘要失敗');
      if (err?.name !== 'AbortError') error.value = msg;
    } finally {
      if (!isStale('summary', requestId)) loading.summary = false;
    }
  }

  // ── Fetch pareto ───────────────────────────────────────────────────────────

  async function fetchPareto(queryId, fineParams, dim = paretoDim.value) {
    if (!queryId) return;
    loading.pareto = true;
    const requestId = nextRequestId('pareto');
    try {
      const params = { query_id: queryId, dim, ...fineParams };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/eap-alarm/pareto${qs}`);
      if (isStale('pareto', requestId)) return;
      const data = resp?.data;
      if (data) {
        pareto.items = Array.isArray(data.items) ? data.items : [];
        pareto.total = data.total ?? 0;
      }
    } catch (err) {
      if (isStale('pareto', requestId)) return;
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得 Pareto 失敗');
    } finally {
      if (!isStale('pareto', requestId)) loading.pareto = false;
    }
  }

  // ── Fetch trend ────────────────────────────────────────────────────────────

  async function fetchTrend(queryId, fineParams, granularity = 'day', groupBy = trendGroupBy.value) {
    if (!queryId) return;
    loading.trend = true;
    const requestId = nextRequestId('trend');
    try {
      const params = { query_id: queryId, granularity, group_by: groupBy, ...fineParams };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/eap-alarm/trend${qs}`);
      if (isStale('trend', requestId)) return;
      const data = resp?.data;
      if (data) {
        trend.labels = Array.isArray(data.labels) ? data.labels : [];
        trend.series = Array.isArray(data.series) ? data.series : [];
      }
    } catch (err) {
      if (isStale('trend', requestId)) return;
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得趨勢失敗');
    } finally {
      if (!isStale('trend', requestId)) loading.trend = false;
    }
  }

  // ── Fetch detail ───────────────────────────────────────────────────────────

  async function fetchDetail(queryId, fineParams, page = 1, perPage = DEFAULT_PER_PAGE) {
    if (!queryId) return;
    loading.detail = true;
    try {
      const effectivePerPage = Math.min(perPage, 200);
      const params = { query_id: queryId, page, per_page: effectivePerPage, ...fineParams };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/eap-alarm/detail${qs}`);
      const data = resp?.data;
      if (data) {
        detail.rows = Array.isArray(data.rows) ? data.rows : [];
        detail.meta = data.meta ?? { page, per_page: effectivePerPage, total_count: 0, total_pages: 1 };
      }
    } catch (err) {
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得明細失敗');
    } finally {
      loading.detail = false;
    }
  }

  // ── Fetch all views at once ────────────────────────────────────────────────

  async function fetchAllViews(queryId, fineParams) {
    if (!queryId) return;
    error.value = '';
    await Promise.all([
      fetchSummary(queryId, fineParams),
      fetchPareto(queryId, fineParams, paretoDim.value),
      fetchTrend(queryId, fineParams, trendGranularity.value, trendGroupBy.value),
      fetchDetail(queryId, fineParams, detailPage.value, detailPerPage.value),
    ]);
  }

  return {
    loading,
    error,
    summary,
    pareto,
    paretoDim,
    trend,
    trendGranularity,
    trendGroupBy,
    detail,
    detailPage,
    detailPerPage,
    resetAll,
    fetchFilterOptions,
    fetchSummary,
    fetchPareto,
    fetchTrend,
    fetchDetail,
    fetchAllViews,
  };
}
