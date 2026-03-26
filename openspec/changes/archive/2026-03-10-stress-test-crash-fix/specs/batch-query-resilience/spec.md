## MODIFIED Requirements

### Requirement: reject_dataset_cache SHALL propagate partial failure metadata to API response
The cache service SHALL read batch execution metadata and include partial failure information in the API response `meta` field.

#### Scenario: Partial failure metadata included in response
- **WHEN** `execute_primary_query()` uses the batch engine path and `get_batch_progress()` returns `has_partial_failure=True`
- **THEN** the response `meta` dict SHALL include `has_partial_failure: true`
- **THEN** the response `meta` dict SHALL include `failed_chunk_count` as an integer
- **THEN** if `failed_ranges` is present, the response `meta` dict SHALL include `failed_ranges` as a list of `{start, end}` objects

#### Scenario: Metadata read before redis_clear_batch
- **WHEN** `execute_primary_query()` calls `get_batch_progress()`
- **THEN** the call SHALL occur after merge (whether via `merge_chunks()` or `merge_chunks_to_spool()`) and before `redis_clear_batch()`

#### Scenario: No partial failure on successful query
- **WHEN** all chunks complete successfully
- **THEN** the response `meta` dict SHALL NOT include `has_partial_failure`

#### Scenario: Cache-hit path restores partial failure flag
- **WHEN** a cached DataFrame is returned (cache hit) and a partial failure flag was stored during the original query
- **THEN** the response `meta` dict SHALL include the same `has_partial_failure`, `failed_chunk_count`, and `failed_ranges` as the original response

#### Scenario: Partial failure flag TTL matches data storage layer
- **WHEN** partial failure is detected and the query result is spilled to parquet spool
- **THEN** the partial failure flag SHALL be stored with TTL equal to `_REJECT_ENGINE_SPOOL_TTL_SECONDS` (default 21600 seconds)
- **WHEN** partial failure is detected and the query result is stored in L1/L2 Redis cache
- **THEN** the partial failure flag SHALL be stored with TTL equal to `_CACHE_TTL` (default 900 seconds)
