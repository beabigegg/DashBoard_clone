## MODIFIED Requirements

### Requirement: Resource dataset cache SHALL execute a single Oracle query and cache the result
The resource_dataset_cache module SHALL query Oracle once for the full shift-status fact set and cache it for subsequent derivations. For date ranges exceeding 60 days, the query SHALL be decomposed into monthly chunks via `BatchQueryOrchestrator`.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range, granularity, and resource filter parameters
- **THEN** a deterministic `query_id` SHALL be computed from all primary params using SHA256
- **THEN** if a cached DataFrame exists for this query_id (L1 or L2), it SHALL be used without querying Oracle
- **THEN** if no cache exists, a single Oracle query SHALL fetch all shift-status records from `DW_MES_RESOURCESTATUS_SHIFT` for the filtered resources and date range
- **THEN** the result DataFrame SHALL be stored in both L1 (ProcessLevelCache) and L2 (Redis as parquet/base64)
- **THEN** the response SHALL include `query_id`, summary (KPI, trend, heatmap, comparison), and detail page 1

#### Scenario: Long date range triggers batch decomposition
- **WHEN** the date range exceeds 60 days (configurable via `BATCH_QUERY_TIME_THRESHOLD_DAYS`)
- **THEN** the query SHALL be decomposed into ~31-day monthly chunks via `BatchQueryOrchestrator.decompose_by_time_range()`
- **THEN** each chunk SHALL execute independently via `read_sql_df_slow` with the chunk's date sub-range
- **THEN** chunk results SHALL be stored individually in Redis and merged via `pd.concat`
- **THEN** the merged DataFrame SHALL be stored in the existing L1+L2 cache under the original query_id

#### Scenario: Short date range uses direct query
- **WHEN** the date range is 60 days or fewer
- **THEN** the existing single-query path SHALL be used without batch decomposition

#### Scenario: Cache TTL and eviction
- **WHEN** a DataFrame is cached
- **THEN** the cache TTL SHALL be 900 seconds (15 minutes)
- **THEN** L1 cache max_size SHALL be 8 entries with LRU eviction
- **THEN** the Redis namespace SHALL be `resource_dataset`

#### Scenario: Redis parquet helpers use shared module
- **WHEN** DataFrames are stored or loaded from Redis
- **THEN** the module SHALL use `redis_df_store.redis_store_df()` and `redis_df_store.redis_load_df()` from the shared `core/redis_df_store.py` module
- **THEN** inline `_redis_store_df` / `_redis_load_df` functions SHALL be removed
