/**
 * useUphPerformanceViews.js
 *
 * Fetches trend, ranking, and detail data from the UPH-Performance spool
 * endpoints (DuckDB-derived views, no Oracle re-query after spool build —
 * data-shape-contract.md §3.29). Mirrors useEapAlarmViews.js.
 *
 * The ranking fetch is intentionally NOT part of fetchAllViews' unconditional
 * fan-out: it is only issued when the caller supplies a non-empty ranking
 * Type selection (interaction-design.md §Confirmed #2 — the ranking block
 * must stay empty/prompting, never auto-queried, until a Type is picked).
 */
import { reactive, ref } from 'vue';
import { apiGet } from '../../core/api';
import { useViewStaleness } from '../../shared-composables/useViewStaleness';

const DEFAULT_PER_PAGE = 50; // contract caps per_page at 200; interaction-design.md §Confirmed #8

export function useUphPerformanceViews() {
  // ── Loading state ──────────────────────────────────────────────────────────
  const loading = reactive({
    trend: false,
    ranking: false,
    detail: false,
    filterOptions: false,
  });

  const error = ref('');

  // ── Trend ──────────────────────────────────────────────────────────────────
  const trend = reactive({
    labels: [],
    series: [],
    group_by: 'family',
  });

  // Default trend group-by per interaction-design.md §Confirmed #3.
  const trendGroupBy = ref('family');

  // ── Ranking ────────────────────────────────────────────────────────────────
  const ranking = reactive({
    items: [],
    pj_types: [],
  });

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
  const { nextRequestId, isStaleRequest: isStale } = useViewStaleness([
    'trend',
    'ranking',
    'detail',
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
    trend.labels = [];
    trend.series = [];
    trend.group_by = trendGroupBy.value;
    ranking.items = [];
    ranking.pj_types = [];
    detail.rows = [];
    detail.meta = { page: 1, per_page: DEFAULT_PER_PAGE, total_count: 0, total_pages: 1 };
    detailPage.value = 1;
    error.value = '';
  }

  // ── Fetch filter options (post-spool, fine-filter axes) ───────────────────

  async function fetchFilterOptions(queryId) {
    if (!queryId) return null;
    loading.filterOptions = true;
    try {
      const resp = await apiGet(`/api/uph-performance/filter-options?query_id=${encodeURIComponent(queryId)}`);
      if (resp && resp.success === false) {
        return null;
      }
      return resp?.data ?? null;
    } catch (err) {
      console.warn('[UPH Performance] fetchFilterOptions error', err);
      return null;
    } finally {
      loading.filterOptions = false;
    }
  }

  // ── Fetch trend ────────────────────────────────────────────────────────────

  async function fetchTrend(queryId, fineParams, groupBy = trendGroupBy.value) {
    if (!queryId) return;
    loading.trend = true;
    const requestId = nextRequestId('trend');
    try {
      const params = { query_id: queryId, group_by: groupBy, ...fineParams };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/uph-performance/trend${qs}`);
      if (isStale('trend', requestId)) return;
      const data = resp?.data;
      if (data) {
        trend.labels = Array.isArray(data.labels) ? data.labels : [];
        trend.series = Array.isArray(data.series) ? data.series : [];
        trend.group_by = data.group_by ?? groupBy;
      }
    } catch (err) {
      if (isStale('trend', requestId)) return;
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得趨勢資料失敗');
    } finally {
      if (!isStale('trend', requestId)) loading.trend = false;
    }
  }

  // ── Fetch ranking (own independent pj_type[] axis) ────────────────────────

  async function fetchRanking(queryId, pjTypes) {
    // interaction-design.md §Confirmed #2: no Type selected -> stay
    // empty/prompting, never issue the request.
    if (!queryId || !Array.isArray(pjTypes) || pjTypes.length === 0) {
      ranking.items = [];
      ranking.pj_types = [];
      return;
    }
    loading.ranking = true;
    const requestId = nextRequestId('ranking');
    try {
      const params = { query_id: queryId, 'pj_type[]': pjTypes };
      const qs = buildQueryParams(params);
      const resp = await apiGet(`/api/uph-performance/ranking${qs}`);
      if (isStale('ranking', requestId)) return;
      const data = resp?.data;
      if (data) {
        ranking.items = Array.isArray(data.items) ? data.items : [];
        ranking.pj_types = Array.isArray(data.pj_types) ? data.pj_types : [];
      }
    } catch (err) {
      if (isStale('ranking', requestId)) return;
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得排行資料失敗');
    } finally {
      if (!isStale('ranking', requestId)) loading.ranking = false;
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
      const resp = await apiGet(`/api/uph-performance/detail${qs}`);
      const data = resp?.data;
      if (data) {
        detail.rows = Array.isArray(data.rows) ? data.rows : [];
        detail.meta = data.meta ?? { page, per_page: effectivePerPage, total_count: 0, total_pages: 1 };
      }
    } catch (err) {
      if (err?.name !== 'AbortError') error.value = String(err?.message || '取得明細資料失敗');
    } finally {
      loading.detail = false;
    }
  }

  // ── Fetch all views at once (trend + detail unconditionally; ranking only
  //    when the caller already has a non-empty ranking Type selection) ──────

  async function fetchAllViews(queryId, fineParams, rankingPjTypes = []) {
    if (!queryId) return;
    error.value = '';
    await Promise.all([
      fetchTrend(queryId, fineParams, trendGroupBy.value),
      fetchDetail(queryId, fineParams, detailPage.value, detailPerPage.value),
      fetchRanking(queryId, rankingPjTypes),
    ]);
  }

  return {
    loading,
    error,
    trend,
    trendGroupBy,
    ranking,
    detail,
    detailPage,
    detailPerPage,
    resetAll,
    fetchFilterOptions,
    fetchTrend,
    fetchRanking,
    fetchDetail,
    fetchAllViews,
  };
}
