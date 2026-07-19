/**
 * useUphPerformanceFilter.js
 *
 * Manages coarse filter state (date range + families + workcenter_names +
 * packages + pj_types + equipment_ids; triggers a new spool) and fine filter
 * state (equipment_id/workcenter_name/package/pj_type; re-slices the existing
 * spool via DuckDB-derived views, no re-spool — mirrors useEapAlarmFilter.js).
 *
 * The ranking block's Type filter (`ctrl-ranking-type-filter`) is intentionally
 * NOT part of either coarseFilter or fineFilter here — interaction-design.md
 * §Confirmed #2/#7 requires it to be a wholly separate widget instance/state
 * that never shares selection with `ctrl-type-select-global`. It defaults to
 * an empty array (none selected) and is exposed as its own `rankingTypeFilter`
 * ref so the ranking block stays empty/prompting until the engineer picks a
 * Type — it is never read from or written to `coarseFilter.pj_types` /
 * `fineFilter.pj_type`.
 */
import { reactive, ref, onMounted } from 'vue';
import { apiGet } from '../../core/api';

export function useUphPerformanceFilter() {
  // ── Coarse filter (triggers spool) ──────────────────────────────────────────
  const coarseFilter = reactive({
    date_from: '',
    date_to: '',
    families: [],        // DB/WB category: closed enum subset of {GDBA, GWBA}; empty = both (UPH-02)
    models: [],          // 機型 (RESOURCEFAMILYNAME, e.g. DBA_AD832UR) — real machine models, cascaded from families
    workcenter_names: [], // 工作站 (WORKCENTERNAME) — dropdown from machine-options, cascaded
    packages: [],         // product dim: Package (PRODUCTLINENAME) — backed by product-filter-options
    pj_types: [],         // product dim: Type (PJ_TYPE) — backed by product-filter-options
    equipment_ids: [],    // 機台 (RESOURCENAME) — dropdown from machine-options, cascaded, max 200 (UPH contract)
  });

  // ── Machine options (from /api/uph-performance/machine-options, DW_MES_RESOURCE) ─
  // Cascadable pre-query dropdown source: family (DB/WB) -> model -> workcenter
  // -> equipment. Replaces the old GDBA/GWBA-only 機型 select + free-text
  // 工作站 / 機台 textareas.
  const machineOptions = ref({
    families: [],     // [{code:'GDBA', label:'Die-Bond'}, ...]
    models: [],       // [{family:'GDBA', model:'DBA_AD832UR'}, ...]
    workcenters: [],  // ['焊接_DB', ...]
    equipment: [],    // [{equipment_id, family, model, workcenter}, ...]
  });
  const machineOptionsLoading = ref(false);
  const machineOptionsError = ref('');

  // ── Product filter options (from /api/uph-performance/product-filter-options) ─
  const productFilterOptions = ref({
    pj_types: [],
    product_lines: [],
  });

  const productOptionsLoading = ref(false);
  // Confirmed #6: on 500, show an inline warning near Package/Type dropdowns;
  // other filters stay usable (state-coarse-options-degraded).
  const productOptionsError = ref('');

  // ── Fine filter (DuckDB-derived views only, no Oracle re-query) ────────────
  const FINE_FILTER_PARAM_MAP = {
    equipment_id: 'equipment_id[]',
    workcenter_name: 'workcenter_name[]',
    package: 'package[]',
    pj_type: 'pj_type[]',
  };
  const FINE_FILTER_KEYS = Object.keys(FINE_FILTER_PARAM_MAP);

  const fineFilter = reactive({
    equipment_id: [],
    workcenter_name: [],
    package: [],
    pj_type: [],
  });

  // ── Ranking's OWN independent Type filter (never shared with the above) ───
  const rankingTypeFilter = ref([]);

  // ── Fine filter options (populated after spool via GET /filter-options) ───
  const FILTER_OPTION_KEYS = [
    'equipment_id_options',
    'workcenter_name_options',
    'package_options',
    'pj_type_options',
  ];

  const filterOptions = reactive({
    equipment_id_options: [],
    workcenter_name_options: [],
    package_options: [],
    pj_type_options: [],
  });

  // ── Snapshot-diff: tracks last committed fine filter to detect changes ───
  let _lastCommitted = {
    equipment_id: [],
    workcenter_name: [],
    package: [],
    pj_type: [],
  };

  // ── Query state ────────────────────────────────────────────────────────────
  const queryId = ref('');
  const spoolReady = ref(false);

  function setQueryId(id) {
    queryId.value = id;
    spoolReady.value = Boolean(id);
  }

  function resetFineFilter() {
    for (const key of FINE_FILTER_KEYS) {
      fineFilter[key] = [];
    }
    _syncLastCommitted();
  }

  function resetFilterOptions() {
    for (const key of FILTER_OPTION_KEYS) {
      filterOptions[key] = [];
    }
  }

  function resetRankingTypeFilter() {
    rankingTypeFilter.value = [];
  }

  /**
   * Re-sync _lastCommitted from the current fine filter selection.
   * Must be called after every fetchFilterOptions (snapshot-diff rule,
   * frontend-patterns.md).
   */
  function _syncLastCommitted() {
    _lastCommitted = Object.fromEntries(
      FINE_FILTER_KEYS.map((key) => [key, [...fineFilter[key]]]),
    );
  }

  /**
   * Apply fetched filter options and re-sync _lastCommitted.
   * Called by the view composable after GET /api/uph-performance/filter-options.
   */
  function applyFilterOptions(options) {
    for (const key of FILTER_OPTION_KEYS) {
      filterOptions[key] = Array.isArray(options[key]) ? options[key] : [];
    }
    _syncLastCommitted();
  }

  /**
   * Returns true if the current fine filter differs from _lastCommitted
   * (used to decide whether to trigger a DuckDB-derived-view recompute).
   */
  function hasFineFilterChanged() {
    const arrEq = (x, y) =>
      x.length === y.length && x.every((v, i) => v === y[i]);
    return FINE_FILTER_KEYS.some(
      (key) => !arrEq(_lastCommitted[key] ?? [], fineFilter[key]),
    );
  }

  function commitFineFilter() {
    _syncLastCommitted();
  }

  function buildFineFilterParams() {
    const params = { query_id: queryId.value };
    for (const key of FINE_FILTER_KEYS) {
      if (fineFilter[key].length > 0) {
        params[FINE_FILTER_PARAM_MAP[key]] = fineFilter[key];
      }
    }
    return params;
  }

  /**
   * Build the ranking endpoint's OWN independent query params. Returns null
   * when no Type is selected — interaction-design.md §Confirmed #2: the
   * ranking block must stay empty/prompting (never auto-query) until the
   * engineer picks at least one Type here.
   */
  function buildRankingParams() {
    if (rankingTypeFilter.value.length === 0) return null;
    return { query_id: queryId.value, 'pj_type[]': rankingTypeFilter.value };
  }

  /**
   * Build POST body params for the coarse spool request.
   * Omits empty arrays so the backend does not receive spurious empty dims.
   */
  function buildCoarseParams() {
    const params = {
      date_from: coarseFilter.date_from,
      date_to: coarseFilter.date_to,
    };
    if (coarseFilter.families.length > 0) {
      params.families = coarseFilter.families;
    }
    if (coarseFilter.models.length > 0) {
      params.models = coarseFilter.models;
    }
    if (coarseFilter.workcenter_names.length > 0) {
      params.workcenter_names = coarseFilter.workcenter_names;
    }
    if (coarseFilter.packages.length > 0) {
      params.packages = coarseFilter.packages;
    }
    if (coarseFilter.pj_types.length > 0) {
      params.pj_types = coarseFilter.pj_types;
    }
    if (coarseFilter.equipment_ids.length > 0) {
      params.equipment_ids = coarseFilter.equipment_ids;
    }
    return params;
  }

  /**
   * Parse a raw textarea string (one value per line) into a clean array.
   * Splits on newline, trims each entry, and drops empty strings. Used for
   * workcenter_names / equipment_ids — neither has a pre-query options
   * endpoint in the API contract, so both are free-text multi-value entry
   * (mirrors eap-alarm's LOT ID textarea pattern) rather than a MultiSelect
   * backed by an undocumented endpoint.
   */
  function parseMultiLineText(raw) {
    return raw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  /**
   * Load product-filter-options (Package/Type pre-query dropdowns) on mount.
   * On failure (500), surface an inline warning (state-coarse-options-degraded,
   * confirmed #6) instead of blocking the rest of the page.
   */
  async function loadProductFilterOptions() {
    productOptionsLoading.value = true;
    productOptionsError.value = '';
    try {
      const result = await apiGet('/api/uph-performance/product-filter-options', { timeout: 30000 });
      const data = result?.data ?? {};
      productFilterOptions.value = {
        pj_types: Array.isArray(data.pj_types) ? data.pj_types : [],
        product_lines: Array.isArray(data.product_lines) ? data.product_lines : [],
      };
    } catch (err) {
      productOptionsError.value = String(err?.message || '無法載入 Package / Type 選項，其餘篩選器仍可使用');
    } finally {
      productOptionsLoading.value = false;
    }
  }

  /**
   * Load machine-options (機型 / 工作站 / 機台 cascadable dropdowns) on mount
   * from DW_MES_RESOURCE. On failure, surface an inline warning; the date
   * range + Package/Type filters stay usable (mirrors product-filter-options'
   * degrade path).
   */
  async function loadMachineOptions() {
    machineOptionsLoading.value = true;
    machineOptionsError.value = '';
    try {
      const result = await apiGet('/api/uph-performance/machine-options', { timeout: 30000 });
      const data = result?.data ?? {};
      machineOptions.value = {
        families: Array.isArray(data.families) ? data.families : [],
        models: Array.isArray(data.models) ? data.models : [],
        workcenters: Array.isArray(data.workcenters) ? data.workcenters : [],
        equipment: Array.isArray(data.equipment) ? data.equipment : [],
      };
    } catch (err) {
      machineOptionsError.value = String(err?.message || '無法載入 機型 / 工作站 / 機台 選項，可改用日期與 Package / Type 篩選');
    } finally {
      machineOptionsLoading.value = false;
    }
  }

  onMounted(() => {
    loadProductFilterOptions();
    loadMachineOptions();
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
    rankingTypeFilter,
    filterOptions,
    productFilterOptions,
    productOptionsLoading,
    productOptionsError,
    machineOptions,
    machineOptionsLoading,
    machineOptionsError,
    loadMachineOptions,
    queryId,
    spoolReady,
    setQueryId,
    resetFineFilter,
    resetFilterOptions,
    resetRankingTypeFilter,
    applyFilterOptions,
    hasFineFilterChanged,
    commitFineFilter,
    buildFineFilterParams,
    buildRankingParams,
    buildCoarseParams,
    parseMultiLineText,
    loadProductFilterOptions,
    setDefaultDateRange,
  };
}
