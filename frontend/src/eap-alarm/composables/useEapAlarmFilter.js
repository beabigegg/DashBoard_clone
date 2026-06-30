/**
 * useEapAlarmFilter.js
 *
 * Manages coarse filter state (date range + eqp_types + lot_ids + product_dims)
 * and fine filter state (alarm_text, alarm_category, eqp_id). Re-syncs
 * _lastCommitted from selection after every fetchFilterOptions call
 * (frontend-patterns.md snapshot-diff rule).
 */
import { reactive, ref, onMounted } from 'vue';
import { apiGet } from '../../core/api';

export function useEapAlarmFilter() {
  // ── Coarse filter (triggers spool) ──────────────────────────────────────────
  const coarseFilter = reactive({
    date_from: '',
    date_to: '',
    machines: [],    // RESOURCENAME list; populated at submit time from resource filter
    lot_ids: [],     // LOT_ID IN (...) filter; text input parsed by newline
    pj_types: [],    // product dim: PJ type
    product_lines: [], // product dim: package / product line
    pj_bops: [],     // product dim: BOP
  });

  // ── Product filter options (from /api/eap-alarm/product-filter-options) ─────
  const productFilterOptions = ref({
    pj_types: [],
    product_lines: [],
    pj_bops: [],
    updated_at: null,
  });

  const productOptionsLoading = ref(false);

  // ── Fine filter (DuckDB only, no Oracle re-query) ──────────────────────────
  const fineFilter = reactive({
    alarm_text: [],
    eqp_id: [],
  });

  // ── Fine filter options (populated after spool) ──────────────────────────
  const filterOptions = reactive({
    alarm_text_options: [],
    equipment_id_options: [],
  });

  // ── Snapshot-diff: tracks last committed fine filter to detect changes ───
  let _lastCommitted = {
    alarm_text: [],
    eqp_id: [],
  };

  // ── Query state ────────────────────────────────────────────────────────────
  const queryId = ref('');
  const spoolReady = ref(false);

  function setQueryId(id) {
    queryId.value = id;
    spoolReady.value = Boolean(id);
  }

  function resetFineFilter() {
    fineFilter.alarm_text = [];
    fineFilter.eqp_id = [];
    _syncLastCommitted();
  }

  function resetFilterOptions() {
    filterOptions.alarm_text_options = [];
    filterOptions.equipment_id_options = [];
  }

  /**
   * Re-sync _lastCommitted from the current fine filter selection.
   * Must be called after every fetchFilterOptions (snapshot-diff rule).
   */
  function _syncLastCommitted() {
    _lastCommitted = {
      alarm_text: [...fineFilter.alarm_text],
      eqp_id: [...fineFilter.eqp_id],
    };
  }

  /**
   * Apply fetched filter options and re-sync _lastCommitted.
   * Called by the view composable after GET /api/eap-alarm/filter-options.
   */
  function applyFilterOptions(options) {
    filterOptions.alarm_text_options = Array.isArray(options.alarm_text_options)
      ? options.alarm_text_options
      : [];
    filterOptions.equipment_id_options = Array.isArray(options.equipment_id_options)
      ? options.equipment_id_options
      : [];
    _syncLastCommitted();
  }

  /**
   * Returns true if the current fine filter differs from _lastCommitted
   * (used to decide whether to trigger DuckDB recompute).
   */
  function hasFineFilterChanged() {
    const a = _lastCommitted;
    const b = fineFilter;
    const arrEq = (x, y) =>
      x.length === y.length && x.every((v, i) => v === y[i]);
    return !arrEq(a.alarm_text, b.alarm_text) || !arrEq(a.eqp_id, b.eqp_id);
  }

  function commitFineFilter() {
    _syncLastCommitted();
  }

  function buildFineFilterParams() {
    const params = { query_id: queryId.value };
    if (fineFilter.alarm_text.length > 0) {
      params['alarm_text[]'] = fineFilter.alarm_text;
    }
    if (fineFilter.eqp_id.length > 0) {
      params['equipment_id[]'] = fineFilter.eqp_id;
    }
    return params;
  }

  /**
   * Build POST body params for the coarse spool request.
   * Omits empty arrays so the backend does not receive spurious empty dims.
   * machines maps to the "machines" key (backward-compat with existing API).
   */
  function buildCoarseParams() {
    const params = {
      date_from: coarseFilter.date_from,
      date_to: coarseFilter.date_to,
    };
    if (coarseFilter.machines.length > 0) {
      params.machines = coarseFilter.machines;
    }
    if (coarseFilter.lot_ids.length > 0) {
      params.lot_ids = coarseFilter.lot_ids;
    }
    if (coarseFilter.pj_types.length > 0) {
      params.pj_types = coarseFilter.pj_types;
    }
    if (coarseFilter.product_lines.length > 0) {
      params.product_lines = coarseFilter.product_lines;
    }
    if (coarseFilter.pj_bops.length > 0) {
      params.pj_bops = coarseFilter.pj_bops;
    }
    return params;
  }

  /**
   * Parse a raw textarea string (one LOT ID per line) into a clean array.
   * Splits on newline, trims each entry, and drops empty strings.
   */
  function parseLotIdText(raw) {
    return raw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  /**
   * Load product-filter-options from the backend on mount.
   * Cold-cache empty arrays are safe — just leaves MultiSelects empty.
   */
  async function loadProductFilterOptions() {
    productOptionsLoading.value = true;
    try {
      const result = await apiGet('/api/eap-alarm/product-filter-options', { timeout: 30000 });
      const data = result?.data ?? {};
      productFilterOptions.value = {
        pj_types: Array.isArray(data.pj_types) ? data.pj_types : [],
        product_lines: Array.isArray(data.product_lines) ? data.product_lines : [],
        pj_bops: Array.isArray(data.pj_bops) ? data.pj_bops : [],
        updated_at: data.updated_at ?? null,
      };
    } catch {
      // non-fatal: cold cache — leave options as empty arrays
    } finally {
      productOptionsLoading.value = false;
    }
  }

  onMounted(() => {
    loadProductFilterOptions();
  });

  function setDefaultDateRange() {
    const today = new Date();
    const end = new Date(today);
    end.setDate(end.getDate() - 1);
    const start = new Date(end);
    start.setDate(start.getDate() - 6); // 7-day default
    const fmt = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    };
    coarseFilter.date_from = fmt(start);
    coarseFilter.date_to = fmt(end);
  }

  return {
    coarseFilter,
    fineFilter,
    filterOptions,
    productFilterOptions,
    productOptionsLoading,
    queryId,
    spoolReady,
    setQueryId,
    resetFineFilter,
    resetFilterOptions,
    applyFilterOptions,
    hasFineFilterChanged,
    commitFineFilter,
    buildFineFilterParams,
    buildCoarseParams,
    parseLotIdText,
    setDefaultDateRange,
  };
}
