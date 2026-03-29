## MODIFIED Requirements

### Requirement: Resource dataset cache SHALL execute a single Oracle query and cache the result
The resource_dataset_cache module SHALL query Oracle via chunked batch queries and cache the result to Parquet spool for subsequent DuckDB-based derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range, granularity, and resource filter parameters
- **THEN** a deterministic `query_id` SHALL be computed from all primary params using SHA256
- **THEN** if a cached spool file exists for this query_id, it SHALL be used without querying Oracle
- **THEN** if no cache exists, chunked Oracle queries SHALL fetch shift-status records via `decompose_by_time_range()` + `execute_plan()`
- **THEN** chunks SHALL be stream-merged to a Parquet spool file via `merge_chunks_to_spool()`
- **THEN** the spool metadata SHALL be registered in Redis with query_id, row_count, and TTL via `query_spool_store`
- **THEN** the response SHALL include `query_id`, summary (KPI, trend, heatmap, comparison), and detail page 1

#### Scenario: Direct-path query result stored via spool (Phase 2)
- **WHEN** `execute_primary_query()` completes via the direct path (non-engine)
- **THEN** `_store_df()` SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** `_store_df()` SHALL NOT call `redis_df_store.redis_store_df()` when `PHASE2_METADATA_ONLY=1`

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis spool metadata namespace SHALL be `resource_dataset`
- **THEN** the Redis key `resource_dataset:{query_id}` (Parquet+base64 payload) SHALL NOT be written when `PHASE2_METADATA_ONLY=1`

### Requirement: Resource dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired or the view engine cannot compute a result.

The resource-history domain is classified as **Type A** per the `query-response-semantic-contract`. On HTTP 410, the client SHALL re-trigger `execute_primary_query()` synchronously.

#### Scenario: Cache expired during view request
- **WHEN** a view is requested with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: DuckDB runtime failure during view request
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool miss, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
- **THEN** the system SHALL NOT call `_get_cached_df()` or any `_derive_*()` pandas function

#### Scenario: Type A client re-triggers sync query on 410
- **WHEN** the resource-history view endpoint returns HTTP 410
- **THEN** the client SHALL call `execute_primary_query()` synchronously (no 202 / polling flow)
- **THEN** upon receiving a 200 response, the client SHALL load the view with the returned data
- **THEN** the view endpoint SHALL NOT dispatch any background job as a side-effect of the 410
