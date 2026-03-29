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
- **THEN** the system SHALL call `apply_view()` with the query_id, granularity, and resource filter to compute the response via DuckDB SQL runtime
- **THEN** the response SHALL include `query_id`, summary (KPI, trend, heatmap, comparison), and detail page 1
- **THEN** `execute_primary_query()` SHALL NOT call `_derive_summary()`, `_derive_detail()`, or any `_derive_*()` pandas function
- **THEN** `execute_primary_query()` SHALL NOT call `_get_cached_df()` to load a full DataFrame from Redis

#### Scenario: Bootstrap render failure after spool creation
- **WHEN** `execute_primary_query()` completes its Oracle/spool stage but `apply_view()` cannot produce a valid result for the bootstrap response
- **THEN** the function SHALL return an explicit failure response
- **THEN** the function SHALL NOT return a synthetic empty summary/detail payload with HTTP 200 semantics

#### Scenario: Direct-path query result stored via spool (Phase 2)
- **WHEN** `execute_primary_query()` completes via the direct path (non-engine)
- **THEN** `_store_df()` SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** `_store_df()` SHALL NOT call `redis_df_store.redis_store_df()` when `PHASE2_METADATA_ONLY=1`

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis spool metadata namespace SHALL be `resource_dataset`
- **THEN** the Redis key `resource_dataset:{query_id}` (Parquet+base64 payload) SHALL NOT be written when `PHASE2_METADATA_ONLY=1`
