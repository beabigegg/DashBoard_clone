## 1. Backend — Batch Pareto with Cross-Filter

- [x] 1.1 Add `_apply_cross_filter(df, selections, exclude_dim)` helper in `reject_dataset_cache.py` — applies all dimension selections except `exclude_dim` using `_DIM_TO_DF_COLUMN` mapping
- [x] 1.2 Add `compute_batch_pareto()` function in `reject_dataset_cache.py` — iterates all 6 dimensions from cached DataFrame (no Oracle query), applies policy → supplementary → trend-date → cross-filter, supports `pareto_display_scope=top20` truncation for applicable dimensions, returns `{"dimensions": {...}}`
- [x] 1.3 Add `_parse_multi_pareto_selections()` helper in `reject_history_routes.py` — parses `sel_reason`, `sel_package`, `sel_type`, `sel_workflow`, `sel_workcenter`, `sel_equipment` from query params
- [x] 1.4 Add `GET /api/reject-history/batch-pareto` endpoint in `reject_history_routes.py` — cache-only (no Oracle fallback), accepts `pareto_display_scope` param, calls `compute_batch_pareto()`

## 2. Backend — Multi-Dimension Detail/Export Filter

- [x] 2.1 Extend `_apply_pareto_selection_filter()` in `reject_dataset_cache.py` to accept `pareto_selections: dict` (multi-dimension AND logic), keeping backward compat with single `pareto_dimension`/`pareto_values`
- [x] 2.2 Update `apply_view()` and `export_csv_from_cache()` in `reject_dataset_cache.py` to pass multi-dimension selections
- [x] 2.3 Update `view` and `export-cached` endpoints in `reject_history_routes.py` to parse and forward `sel_*` params

## 3. Frontend — State Refactor (App.vue)

- [x] 3.1 Replace single-dimension state (`paretoDimension`, `selectedParetoValues`, `dimensionParetoItems`, `dimensionParetoLoading`) with `paretoSelections` reactive object and `paretoData` reactive object; keep `paretoDisplayScope` ref for global TOP20/ALL toggle
- [x] 3.2 Add `fetchBatchPareto()` function — calls `GET /api/reject-history/batch-pareto` with `sel_*` params, updates all 6 `paretoData` entries
- [x] 3.3 Rewrite `onParetoItemToggle(dimension, value)` — toggle in `paretoSelections[dimension]`, call `fetchBatchPareto()` + `refreshView()`, reset page
- [x] 3.4 Remove dead code: `allParetoItems`, `filteredParetoItems`, `activeParetoItems` computed, `fetchDimensionPareto()`, `refreshDimensionParetoIfActive()`, `onDimensionChange()`, `PARETO_DIMENSION_LABELS`; keep `PARETO_TOP20_DIMENSIONS` and `paretoDisplayScope` for global TOP20/ALL toggle
- [x] 3.5 Update `activeFilterChips` computed — loop all 6 dimensions, generate chip per selected value with dimension label
- [x] 3.6 Update chip removal handler to call `onParetoItemToggle(dim, value)`

## 4. Frontend — URL State

- [x] 4.1 Update `updateUrlState()` — replace `pareto_dimension`/`pareto_values` with `sel_reason`, `sel_package`, etc. array params; keep `pareto_display_scope` for TOP20/ALL
- [x] 4.2 Update `restoreFromUrl()` — parse `sel_*` params into `paretoSelections` object
- [x] 4.3 Update `buildViewParams()` in `reject-history-filters.js` — replace `paretoDimension`/`paretoValues` with `paretoSelections` dict, emit `sel_*` params

## 5. Frontend — Components

- [x] 5.1 Simplify `ParetoSection.vue` — remove dimension selector dropdown and `DIMENSION_OPTIONS`; keep per-chart TOP20 truncation logic (controlled by parent via `displayScope` prop); add dimension label map; emit `item-toggle` with value only (parent handles dimension routing)
- [x] 5.2 Create `ParetoGrid.vue` — 3-column grid container rendering 6 `ParetoSection` instances, props: `paretoData`, `paretoSelections`, `loading`, `metricLabel`, `selectedDates`; emit `item-toggle(dimension, value)`
- [x] 5.3 Update `App.vue` template — replace single `<ParetoSection>` with `<ParetoGrid>`

## 6. Frontend — Styling

- [x] 6.1 Add `.pareto-grid` CSS class in `style.css` — 3-column grid with responsive breakpoints (2-col at ≤1200px, 1-col at ≤768px)
- [x] 6.2 Adjust `.pareto-chart-wrap` height from 340px to ~240px for compact multi-chart display
- [x] 6.3 Adjust `.pareto-layout` for vertical stack (chart above table) in grid context

## 7. Integration & Wire-Up

- [x] 7.1 Wire `fetchBatchPareto()` into `loadAllData()` flow — call after primary query completes
- [x] 7.2 Wire supplementary filter changes and trend-date changes to trigger `fetchBatchPareto()`
- [x] 7.3 Wire export button to include all 6 dimension selections in export request

## 8. Testing

- [x] 8.1 Add unit tests for `compute_batch_pareto()` cross-filter logic in `tests/test_reject_dataset_cache.py`
- [x] 8.2 Add route tests for `GET /api/reject-history/batch-pareto` endpoint in `tests/test_reject_history_routes.py`
- [x] 8.3 Add tests for multi-dimension `_apply_pareto_selection_filter()` in `tests/test_reject_dataset_cache.py`
