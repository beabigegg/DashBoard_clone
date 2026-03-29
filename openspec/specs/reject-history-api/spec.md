## MODIFIED Requirements

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic, and SHALL prefer materialized Pareto snapshots over full detail regrouping.

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

#### Scenario: Cache-only computation
- **WHEN** `query_id` does not exist in cache
- **THEN** the endpoint SHALL return HTTP 400 with error message indicating cache miss
- **THEN** the endpoint SHALL NOT fall back to Oracle query

#### Scenario: Materialized snapshot preferred
- **WHEN** a valid and fresh materialized Pareto snapshot exists for the request context
- **THEN** the endpoint SHALL return results from that snapshot
- **THEN** the endpoint SHALL avoid full lot-level DataFrame regrouping for the same request

#### Scenario: Materialized miss fallback behavior
- **WHEN** materialized snapshot is unavailable, stale, or build fails
- **THEN** the endpoint SHALL fall back to legacy cache DataFrame computation
- **THEN** the response schema and filter semantics SHALL remain unchanged

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

## Delta: phase3-spool-first-primary-query

### DuckDB as sole view engine for `apply_view`

- The `_REJECT_CACHE_SQL_VIEW_FALLBACK_LEGACY_ENABLED` runtime flag has been removed. The pandas legacy view path is permanently retired.
- `apply_view` SHALL use DuckDB SQL runtime (`reject_cache_sql_runtime.try_compute_view_from_spool`) as the sole compute path.
- **Spool miss**: if DuckDB returns `None`, `apply_view` returns `None` → `GET /api/reject-history/view` returns HTTP 410 `cache_expired`.
- The `batch-pareto` and `export-cached` paths retain their own `_allow_legacy_fallback()` guard and are unaffected by this change.
