## MODIFIED Requirements

### Requirement: Job query SHALL use BatchQueryEngine for long-range decomposition

The `get_jobs_by_resources()` function SHALL delegate to BatchQueryEngine when the requested date range exceeds the configurable threshold, preventing Oracle timeout on large job queries.

#### Scenario: Long date range triggers engine decomposition
- **WHEN** `get_jobs_by_resources(resource_ids, start_date, end_date)` is called
- **AND** the date range exceeds `BATCH_QUERY_TIME_THRESHOLD_DAYS` (default 60)
- **THEN** the date range SHALL be decomposed via `decompose_by_time_range()`
- **THEN** each chunk SHALL be executed through the existing job SQL with chunk-scoped dates
- **THEN** the existing `_build_resource_filter()` batching SHALL be preserved within each chunk

#### Scenario: Short date range preserves direct path
- **WHEN** the date range is within the threshold
- **THEN** the existing direct query path SHALL be used with zero overhead

### Requirement: Job query results SHALL be cached in Redis

Job query results SHALL be cached using the shared `redis_df_store` module to avoid redundant Oracle queries on repeated requests.

#### Scenario: Cache hit returns stored result
- **WHEN** a job query is executed with identical parameters within the cache TTL
- **THEN** the cached result SHALL be returned without hitting Oracle

#### Scenario: Cache miss triggers fresh query
- **WHEN** no cached result exists for the query parameters
- **THEN** the query SHALL execute against Oracle
- **THEN** the result SHALL be stored in Redis with the configured TTL

### Requirement: Job queries SHALL use read_sql_df_slow execution path
- **WHEN** engine-managed job queries execute
- **THEN** they SHALL use `read_sql_df_slow` (dedicated connection, 300s timeout)
- **THEN** no pooled-query regressions SHALL be introduced
