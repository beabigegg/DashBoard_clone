## MODIFIED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic, and SHALL prefer materialized Pareto snapshots over full detail regrouping.

The batch Pareto endpoint SHALL use DuckDB SQL runtime as the sole computation path. The `_allow_legacy_fallback()` gate and pandas DataFrame regrouping fallback SHALL be removed.

#### Scenario: Batch Pareto response structure
- **WHEN** `GET /api/reject-history/batch-pareto` is called with valid `query_id`
- **THEN** response SHALL be `{ success: true, data: { dimensions: { reason: {...}, package: {...}, type: {...}, workflow: {...}, workcenter: {...}, equipment: {...} } } }`
- **THEN** each dimension object SHALL include `items` array with schema (`reason`, `metric_value`, `pct`, `cumPct`, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `count`)

#### Scenario: Batch Pareto uses DuckDB only — no legacy fallback
- **WHEN** batch Pareto is called and a parquet spool file exists for the query_id
- **THEN** the endpoint SHALL compute all 6 dimension Paretos via DuckDB SQL runtime
- **THEN** the endpoint SHALL NOT call `_allow_legacy_fallback()` or fall back to pandas DataFrame regrouping
- **THEN** if spool is missing, the endpoint SHALL return HTTP 410 `cache_expired`

#### Scenario: Cross-filter exclude-self logic
- **WHEN** `sel_reason=A&sel_type=X` is provided
- **THEN** reason Pareto SHALL be computed with type=X filter applied (but NOT reason=A filter)
- **THEN** type Pareto SHALL be computed with reason=A filter applied (but NOT type=X filter)
- **THEN** package/workflow/workcenter/equipment Paretos SHALL be computed with both reason=A AND type=X filters applied

#### Scenario: Empty selections return unfiltered Paretos
- **WHEN** batch-pareto is called with no `sel_*` parameters
- **THEN** all 6 dimensions SHALL return their full Pareto distribution (subject to `pareto_scope`)

### Requirement: Reject dataset cache execute_primary_query SHALL use spool → DuckDB for response building
The `execute_primary_query()` function SHALL build its primary response via DuckDB SQL runtime (`apply_view()`) instead of pandas `_build_primary_response()`.

#### Scenario: Primary query builds response from DuckDB
- **WHEN** `execute_primary_query()` completes Oracle query and spool write
- **THEN** the system SHALL call `apply_view()` with the query_id and default pagination to compute summary, trend, detail, and available_filters
- **THEN** `execute_primary_query()` SHALL NOT call `_build_primary_response()`, `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, or `_derive_trend_from_analytics()` as pandas functions
- **THEN** `execute_primary_query()` SHALL NOT call `_get_cached_df()` to load a full DataFrame from Redis

#### Scenario: Cache hit reuses spool via DuckDB
- **WHEN** `execute_primary_query()` detects a cached spool file for the query_id
- **THEN** the system SHALL call `apply_view()` (DuckDB path) instead of `_build_response_from_cache()` (pandas path)
- **THEN** `_get_cached_df()` SHALL NOT be called

### Requirement: Reject export-cached SHALL use DuckDB only — no legacy fallback
The export-cached endpoint SHALL use DuckDB SQL runtime as the sole computation path.

#### Scenario: Export uses DuckDB only
- **WHEN** `GET /api/reject-history/export-cached` is called with valid `query_id`
- **THEN** the endpoint SHALL compute export data via DuckDB SQL runtime
- **THEN** the endpoint SHALL NOT call `_allow_legacy_fallback()` or fall back to pandas DataFrame computation
- **THEN** if spool is missing, the endpoint SHALL return HTTP 410 `cache_expired`

## REMOVED Requirements

### Requirement: Reject dataset cache pandas derive functions
**Reason**: `_build_primary_response()`, `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, `_derive_trend_from_analytics()` are replaced by DuckDB SQL runtime in `apply_view()`. `_build_response_from_cache()` pandas path is also removed.
**Migration**: All primary response computation is performed by DuckDB SQL runtime via `apply_view()`.

### Requirement: Reject dataset cache legacy fallback gate
**Reason**: `_allow_legacy_fallback()` function and its flag constants (`_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED`, `_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED`) are removed. All paths now use DuckDB exclusively.
**Migration**: Batch pareto and export endpoints use DuckDB SQL runtime directly. If DuckDB spool is missing, return HTTP 410 instead of falling back to pandas.
