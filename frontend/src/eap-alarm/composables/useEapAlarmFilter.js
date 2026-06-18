/**
 * useEapAlarmFilter.js
 *
 * Manages coarse filter state (date range + eqp_types) and fine filter state
 * (alarm_text, alarm_category, eqp_id). Re-syncs _lastCommitted from selection
 * after every fetchFilterOptions call (frontend-patterns.md snapshot-diff rule).
 */
import { reactive, ref } from 'vue';

export function useEapAlarmFilter() {
  // ── Coarse filter (triggers spool) ──────────────────────────────────────────
  const coarseFilter = reactive({
    date_from: '',
    date_to: '',
    machines: [], // RESOURCENAME list; populated at submit time from resource filter
  });

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
    queryId,
    spoolReady,
    setQueryId,
    resetFineFilter,
    resetFilterOptions,
    applyFilterOptions,
    hasFineFilterChanged,
    commitFineFilter,
    buildFineFilterParams,
    setDefaultDateRange,
  };
}
