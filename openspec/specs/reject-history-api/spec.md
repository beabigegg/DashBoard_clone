## MODIFIED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic, and SHALL prefer materialized Pareto snapshots over full detail regrouping.

The batch Pareto endpoint SHALL use DuckDB SQL runtime as the sole computation path. The `_allow_legacy_fallback()` gate and pandas DataFrame regrouping fallback SHALL be removed.

#### Scenario: Batch Pareto response structure
- **WHEN** `GET /api/reject-history/batch-pareto` is called with valid `query_id`
- **THEN** response SHALL be `{ success: true, data: { dimensions: { reason: {...}, package: {...}, type: {...}, workflow: {...}, workcenter: {...}, equipment: {...} } } }`
- **THEN** each dimension object SHALL include `items` array with schema (`reason`, `metric_value`, `pct`, `cumPct`, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `count`)

#### Scenario: Cross-filter exclude-self logic
- **WHEN** `sel_reason=A&sel_type=X` is provided
- **THEN** reason Pareto SHALL be computed with type=X filter applied (but NOT reason=A filter)
- **THEN** type Pareto SHALL be computed with reason=A filter applied (but NOT type=X filter)
- **THEN** package/workflow/workcenter/equipment Paretos SHALL be computed with both reason=A AND type=X filters applied

#### Scenario: Empty selections return unfiltered Paretos
- **WHEN** batch-pareto is called with no `sel_*` parameters
- **THEN** all 6 dimensions SHALL return their full Pareto distribution (subject to `pareto_scope`)

#### Scenario: Batch Pareto uses DuckDB only — no legacy fallback
- **WHEN** batch Pareto is called and a parquet spool file exists for the query_id
- **THEN** the endpoint SHALL compute all 6 dimension Paretos via DuckDB SQL runtime
- **THEN** the endpoint SHALL NOT call `_allow_legacy_fallback()` or fall back to pandas DataFrame regrouping
- **THEN** if spool is missing, the endpoint SHALL return HTTP 410 `cache_expired`

#### Scenario: Materialized snapshot preferred
- **WHEN** a valid and fresh materialized Pareto snapshot exists for the request context
- **THEN** the endpoint SHALL return results from that snapshot
- **THEN** the endpoint SHALL avoid full lot-level DataFrame regrouping for the same request

#### Scenario: Supplementary and policy filters apply
- **WHEN** batch-pareto is called with supplementary filters (packages, workcenter_groups, reason) and policy toggles
- **THEN** all 6 dimension Paretos SHALL be computed after applying policy and supplementary filters first (before cross-filter)

#### Scenario: Display scope (TOP20) support
- **WHEN** `pareto_display_scope=top20` is provided
- **THEN** applicable dimensions (type, workflow, equipment) SHALL truncate results to top 20 items after sorting
- **WHEN** `pareto_display_scope` is omitted or `all`
- **THEN** all items SHALL be returned (subject to `pareto_scope` filter)

#### Scenario: Query endpoint rate limited
- **WHEN** `POST /api/reject-history/query` is called
- **THEN** the request SHALL be subject to `reject-history-query` rate limit bucket
- **THEN** exceeding the rate limit SHALL return HTTP 429 with `Retry-After` header

## ADDED Requirements

### Requirement: Reject History API SHALL expose materialized Pareto freshness metadata
The API SHALL surface stable metadata so operators and clients can identify whether Pareto responses came from materialized snapshots or fallback paths.

#### Scenario: Materialized hit metadata
- **WHEN** batch pareto response is served from materialized snapshot
- **THEN** response metadata SHALL indicate materialized source and snapshot freshness/version identifiers

#### Scenario: Fallback metadata
- **WHEN** response uses legacy fallback due to snapshot miss/stale/build failure
- **THEN** response metadata SHALL include a stable fallback reason code

### Requirement: Reject dataset cache direct-path SHALL store results via spool metadata, not Redis DataFrame payload
The reject_dataset_cache module's direct-path write function (`_store_df()`) SHALL use `store_spooled_df()` to persist query results, eliminating Parquet+base64 Redis storage for the direct query path.

#### Scenario: Direct-path result stored as spool (Phase 2 enabled)
- **WHEN** `_store_df(query_id, df)` is called with `PHASE2_METADATA_ONLY=1`
- **THEN** the system SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** the system SHALL NOT call `_redis_store_df(query_id, df)`
- **THEN** the L1 in-process marker SHALL be set for the query_id

#### Scenario: Direct-path cache load reads from spool
- **WHEN** `_load_df_on_demand(query_id)` is called with `PHASE2_METADATA_ONLY=1` and a spool file exists
- **THEN** the system SHALL return the DataFrame via `load_spooled_df(_REDIS_NAMESPACE, query_id)`
- **THEN** the system SHALL NOT call `redis_load_df()` as the primary lookup

#### Scenario: Engine-path spool write unaffected
- **WHEN** `_store_query_result()` is called for large engine-path results (existing spill logic)
- **THEN** behavior SHALL be unchanged — `store_spooled_df()` / `register_spool_file()` continue to operate as before
- **THEN** the `PHASE2_METADATA_ONLY` flag SHALL NOT affect engine-path spill behavior

#### Scenario: Direct-path rollback (Phase 2 disabled)
- **WHEN** `_store_df(query_id, df)` is called with `PHASE2_METADATA_ONLY=0`
- **THEN** the system SHALL call `_redis_store_df(query_id, df)` (Phase 1 baseline behavior)

### Requirement: Reject History API overload responses SHALL be retryable and contract-consistent
Memory-pressure or heavy-query front-door rejection on reject-history endpoints SHALL use a consistent service-unavailable contract.

#### Scenario: Primary query front-door rejection
- **WHEN** heavy-query guard rejects `POST /api/reject-history/query` before execution
- **THEN** endpoint SHALL return HTTP `503 SERVICE_UNAVAILABLE`
- **THEN** response SHALL include `Retry-After` header and a machine-readable overload code

#### Scenario: Cached/view path memory rejection
- **WHEN** memory guard rejects `GET /api/reject-history/view` or `GET /api/reject-history/export-cached`
- **THEN** endpoint SHALL return retryable overload semantics instead of validation semantics
- **THEN** clients SHALL be able to distinguish overload from parameter-validation failures

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

### Requirement: DuckDB spool runtime SHALL derive AFFECTED_LOT_COUNT from CONTAINERID

When the spool parquet file uses per-LOT granularity (i.e., `CONTAINERID` column is present but `AFFECTED_LOT_COUNT` column is absent), the DuckDB spool runtime SHALL compute `AFFECTED_LOT_COUNT` as `COUNT(DISTINCT "CONTAINERID")` instead of falling back to literal `0`.

This applies to both the view analytics query and the batch-pareto query in `reject_cache_sql_runtime.py`.

#### Scenario: Per-LOT parquet without AFFECTED_LOT_COUNT column
- **WHEN** the spool parquet contains `CONTAINERID` but does not contain `AFFECTED_LOT_COUNT`
- **THEN** the system SHALL use `COUNT(DISTINCT "CONTAINERID")` to compute the affected LOT count in analytics and pareto queries

#### Scenario: Pre-aggregated parquet with AFFECTED_LOT_COUNT column
- **WHEN** the spool parquet contains an `AFFECTED_LOT_COUNT` column
- **THEN** the system SHALL use `SUM(COALESCE("AFFECTED_LOT_COUNT", 0))` as before (backward compatibility)

#### Scenario: Parquet with neither CONTAINERID nor AFFECTED_LOT_COUNT
- **WHEN** the spool parquet contains neither `CONTAINERID` nor `AFFECTED_LOT_COUNT`
- **THEN** the system SHALL fall back to literal `0`

## REMOVED Requirements

### Requirement: Reject dataset cache pandas derive functions
**Reason**: `_build_primary_response()`, `_derive_analytics_raw()`, `_derive_summary_from_analytics()`, `_derive_trend_from_analytics()` are replaced by DuckDB SQL runtime in `apply_view()`. `_build_response_from_cache()` pandas path is also removed.
**Migration**: All primary response computation is performed by DuckDB SQL runtime via `apply_view()`.

### Requirement: Reject dataset cache legacy fallback gate
**Reason**: `_allow_legacy_fallback()` function and its flag constants (`_REJECT_CACHE_SQL_BATCH_PARETO_FALLBACK_LEGACY_ENABLED`, `_REJECT_CACHE_SQL_EXPORT_FALLBACK_LEGACY_ENABLED`) are removed. All paths now use DuckDB exclusively.
**Migration**: Batch pareto and export endpoints use DuckDB SQL runtime directly. If DuckDB spool is missing, return HTTP 410 instead of falling back to pandas.

## Delta: phase3-spool-first-primary-query

### DuckDB as sole view engine for `apply_view`

- The `_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED` runtime flag has been removed. The pandas legacy view path is permanently retired.
- `apply_view` SHALL use DuckDB SQL runtime (`reject_cache_sql_runtime.try_compute_view_from_spool`) as the sole compute path.
- **Spool miss**: if DuckDB returns `None`, `apply_view` returns `None` → `GET /api/reject-history/view` returns HTTP 410 `cache_expired`.
- ~~The `batch-pareto` and `export-cached` paths retain their own `_allow_legacy_fallback()` guard and are unaffected by this change.~~ **Superseded by Phase 5**: `_allow_legacy_fallback()` is removed; batch-pareto and export-cached now use DuckDB exclusively.

## Delta: phase4-semantic-ux-classification

### ADDED Requirements

### Requirement: Reject History API SHALL implement Type B async polling semantic contract on view miss
The reject-history domain is classified as **Type B** per the `query-response-semantic-contract`. When a view request results in a 410 `cache_expired` response, the complete end-to-end contract is:

1. Client receives HTTP 410 from the view endpoint
2. Client POSTs to the async query endpoint (`/reject/query`) with original query parameters
3. Server enqueues RQ job and returns HTTP 202 with `job_id`
4. Client polls job status until job completes
5. Client requests the view again with the same `query_id` (or new `query_id` from job result)

The `apply_view()` function SHALL NOT auto-dispatch the async job on miss. The view endpoint only handles view computation; primary query dispatch is the client's responsibility.

#### Scenario: View miss triggers Type B async re-query flow
- **WHEN** the client calls the reject view endpoint with a `query_id` whose spool has expired
- **THEN** the server SHALL return HTTP 410 `{ success: false, error: "cache_expired" }`
- **THEN** the client SHALL POST to `/api/reject/query` with original date and filter parameters
- **THEN** the server SHALL enqueue an RQ job and return HTTP 202 with `{ job_id, async: true }`
- **THEN** the client SHALL poll `/api/reject/query/status/<job_id>` until `status == "completed"`
- **THEN** the client SHALL request the view endpoint again using the completed job's `query_id`

#### Scenario: View endpoint does not dispatch on miss
- **WHEN** `apply_view(query_id)` returns `None` in the reject view route
- **THEN** the route SHALL call `cache_expired_error()` and return HTTP 410
- **THEN** the route SHALL NOT call `enqueue_job()` or `execute_primary_query()`
- **THEN** no RQ job SHALL be created as a side-effect of the view request

#### Scenario: Async path unchanged — 202 on fresh query
- **WHEN** the client POSTs a new query to `/api/reject/query` with a long date range and async is available
- **THEN** `should_use_async()` SHALL return `True`
- **THEN** the server SHALL enqueue an RQ job and return HTTP 202 with `job_id`
- **THEN** this behavior SHALL be unchanged by Phase 4
