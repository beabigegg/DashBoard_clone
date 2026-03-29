## MODIFIED Requirements

### Requirement: Hold dataset cache SHALL execute a single Oracle query and cache the result
The hold_dataset_cache module SHALL query Oracle via chunked batch queries and cache the result to Parquet spool for subsequent DuckDB-based derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range and hold_type parameters
- **THEN** a deterministic `query_id` SHALL be computed from the primary params (start_date, end_date) using SHA256
- **THEN** if a cached spool file exists for this query_id, it SHALL be used without querying Oracle
- **THEN** if no cache exists, chunked Oracle queries SHALL fetch hold/release records via `decompose_by_time_range()` + `execute_plan()`
- **THEN** chunks SHALL be stream-merged to a Parquet spool file via `merge_chunks_to_spool()`
- **THEN** the spool metadata SHALL be registered in Redis with query_id, row_count, and TTL via `query_spool_store`
- **THEN** the response SHALL include `query_id`, trend, reason_pareto, duration, and list page 1

#### Scenario: Direct-path query result stored via spool (Phase 2)
- **WHEN** `execute_primary_query()` completes via the direct path
- **THEN** `_store_df()` SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** `_store_df()` SHALL NOT call `redis_df_store.redis_store_df()` when `PHASE2_METADATA_ONLY=1`

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis spool metadata namespace SHALL be `hold_dataset`
- **THEN** the Redis key `hold_dataset:{query_id}` (Parquet+base64 payload) SHALL NOT be written when `PHASE2_METADATA_ONLY=1`

### Requirement: Hold dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired.

#### Scenario: Cache expired during view request
- **WHEN** `apply_view()` is called with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: Cache miss after transition from Redis to spool
- **WHEN** `apply_view()` is called with a query_id that has no spool metadata pointer and no Redis DataFrame key
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` (treated as expired/miss)
- **THEN** the client SHALL re-trigger `execute_primary_query()`
