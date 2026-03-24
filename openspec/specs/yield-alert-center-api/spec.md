## ADDED Requirements

### Requirement: Yield Alert Center API SHALL provide ERP-based yield aggregates
The API SHALL compute yield baseline metrics from `ERP_WIP_MOVETXN` and `ERP_WIP_MOVETXN_DETAIL` and expose consistent aggregate results for requested time windows and dimensions.

#### Scenario: Default aggregate query
- **WHEN** client requests yield summary without optional grouping
- **THEN** API SHALL return at least `transaction_qty`, `scrap_qty`, and `yield_pct`
- **THEN** `yield_pct` SHALL be computed from ERP quantities in the same response context

#### Scenario: Dimension aggregate query
- **WHEN** client requests grouping by supported dimensions (`department`, `line`, `package`, `type`, `function`, `operation`)
- **THEN** API SHALL return per-group aggregates using the requested dimension keys
- **THEN** API SHALL return totals that reconcile with ungrouped results for the same filters

### Requirement: Yield Alert Center API SHALL expose alert candidate records
The API SHALL output alert candidates based on configurable yield risk criteria using ERP aggregate windows.

#### Scenario: Alert candidate list
- **WHEN** client requests alert candidates for a valid time range
- **THEN** API SHALL return a paginated list including alert key fields (`date_bucket`, `workorder`, `reason_code`, `scrap_qty`, `yield_pct`, `risk_level`)
- **THEN** response SHALL include deterministic sorting and pagination metadata

#### Scenario: No alerts in range
- **WHEN** no records satisfy alert criteria for the requested range
- **THEN** API SHALL return success with an empty list
- **THEN** response SHALL include zero-count pagination metadata without error

### Requirement: Yield Alert Center API SHALL enforce query safety boundaries
The API SHALL prevent unbounded high-cardinality Oracle scans through explicit window limits, bounded response size, and interactive memory guards.

#### Scenario: Exceeding time window policy
- **WHEN** client requests a date range larger than configured maximum window
- **THEN** API SHALL reject the request with a validation error
- **THEN** response SHALL include a machine-readable reason indicating time-window violation

#### Scenario: Page size guardrail
- **WHEN** client requests `per_page` above configured maximum
- **THEN** API SHALL cap or reject according to policy
- **THEN** response SHALL expose effective page size in pagination metadata

#### Scenario: Memory guard rejection on primary query
- **WHEN** `execute_primary_query` returns a DataFrame exceeding `YIELD_ALERT_VIEW_MAX_INPUT_MB` or projected RSS exceeds `YIELD_ALERT_VIEW_MAX_PROJECTED_RSS_MB`
- **THEN** API SHALL return HTTP 503 with `SERVICE_UNAVAILABLE` error code
- **THEN** response SHALL include a human-readable message explaining the memory constraint
- **THEN** response SHALL include `Retry-After: 30` header

#### Scenario: Memory guard rejection on view query
- **WHEN** `apply_view` pandas fallback path detects DataFrame or projected RSS exceeding configured limits
- **THEN** API SHALL return HTTP 503 with `SERVICE_UNAVAILABLE` error code
- **THEN** response SHALL include a human-readable message explaining the memory constraint

### Requirement: Yield Alert Center API SHALL support performance-aware result reuse
The API SHALL support cache-aware execution for repeated equivalent queries, with parquet spool as the primary storage tier for view computations.

#### Scenario: Cache hit response
- **WHEN** the same normalized query parameters are requested within freshness window
- **THEN** API SHALL return cached aggregate/alert results
- **THEN** response metadata SHALL indicate cache hit status

#### Scenario: Cache miss response
- **WHEN** no reusable cache entry exists
- **THEN** API SHALL execute Oracle query path and return computed results
- **THEN** response metadata SHALL indicate cache miss status

#### Scenario: Parquet spool enables out-of-core view computation
- **WHEN** a parquet spool file exists for the query_id
- **THEN** `apply_view` SHALL compute results via DuckDB without loading the full DataFrame into process memory
- **THEN** peak RSS during view computation SHALL be bounded by DuckDB's memory-mapped execution model

### Requirement: Yield Alert overload signaling SHALL align with heavy-query contract
Yield Alert memory-pressure and overload responses SHALL follow the same retryable contract used by other heavy-query endpoints.

#### Scenario: Primary query overload response contract
- **WHEN** `POST /api/yield-alert/query` returns overload due to memory guard or heavy-query rejection
- **THEN** response SHALL use HTTP `503 SERVICE_UNAVAILABLE`
- **THEN** response SHALL include `Retry-After` and machine-readable overload code/meta

#### Scenario: View query overload response contract
- **WHEN** `GET /api/yield-alert/view` returns overload due to memory guard
- **THEN** response SHALL preserve retryable overload semantics consistent with query endpoint
- **THEN** client SHALL be able to apply unified retry policy across heavy-query pages

### Requirement: Yield Alert Center API SHALL expose a reason-detail endpoint
The API SHALL provide `GET /api/yield-alert/reason-detail` as a direct-query endpoint that does not depend on an existing `query_id` or dataset cache.

#### Scenario: Endpoint availability
- **WHEN** the yield alert feature flag is enabled
- **THEN** `GET /api/yield-alert/reason-detail` SHALL be accessible and rate-limited by `_QUERY_RATE_LIMIT`
- **WHEN** the yield alert feature flag is disabled
- **THEN** the endpoint SHALL return HTTP 404 with `{ success: false, error: "yield_alert_disabled" }`

#### Scenario: Delegated query execution
- **WHEN** the endpoint receives valid `workorder` and `date_bucket` parameters
- **THEN** it SHALL delegate to `query_reason_detail(workorder=..., date_bucket=...)` in `yield_alert_service.py`
- **THEN** it SHALL return the result as `{ success: true, data: { items: [...], workorder: "...", date_bucket: "..." } }`

## REMOVED Requirements

### Requirement: Yield Alert Center API drilldown-context endpoint is the primary drill path
**Reason**: 「查看追溯」跳轉行為被 inline reason-detail 取代，drilldown-context 不再是使用者互動的主要入口。
**Migration**: 前端改呼叫 `GET /api/yield-alert/reason-detail`；`/api/yield-alert/drilldown-context` endpoint 仍保留在後端（不刪除）供未來使用，但前端不再觸發。

## Delta: 2026-03-24-yield-alert-streaming-spool

### Primary query pipeline changes (`POST /api/yield-alert/query`)

- `execute_primary_query` now uses streaming write pipeline when `YIELD_ALERT_STREAMING_SPOOL_ENABLED=true` (default).
- Peak memory reduced from ~600MB to ~5MB by streaming Oracle rows via `read_sql_df_slow_iter` → `ParquetWriter` → `register_spool_file`.
- query_id-level single-flight distributed lock prevents duplicate Oracle queries for the same conditions.
- When spool write or register fails: returns `503 SERVICE_UNAVAILABLE` with `Retry-After: 30` and `error_code: SERVICE_UNAVAILABLE`. No query marker is published.
- Empty-result queries (0 rows) store a lightweight cache marker (`empty_result=true, spool_ready=false`) to prevent repeated Oracle re-queries.
- Query date metadata (`start_date`, `end_date`) is persisted in the L1 cache payload.

### Redis L2 detail removed

- `detail_df` is no longer stored in Redis. Only `linkage_df` (~20KB) remains in Redis.
- Cache validity is now determined by: L1 payload marker exists AND (`empty_result=true` OR spool file exists on disk).

### Linkage query changes (`POST /api/yield-alert/analyze`)

- `execute_linkage_query` now uses DuckDB `SELECT DISTINCT "WORKORDER" FROM read_parquet(spool_path)` to extract workorders instead of loading full 662K-row detail DataFrame from Redis.
- Memory for linkage query reduced from ~200MB to ~1MB.
- If spool is not available: returns `linkage_ready: false` with `linkage_not_ready_reason: spool_not_available`.
- Date range (`start_date`, `end_date`) for Oracle reject linkage query now sourced from payload metadata (not from detail_df min/max).

### Rollout/rollback

- Feature flag: `YIELD_ALERT_STREAMING_SPOOL_ENABLED` (env var, default `true`). Set to `false` to use legacy path.
