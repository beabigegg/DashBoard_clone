# batch-query-resilience Specification

## Purpose
Batch query engine resilience features: failed chunk range tracking, transient error retry, and partial failure metadata propagation to API consumers.
## Requirements
### Requirement: BatchQueryEngine SHALL track failed chunk time ranges in progress metadata
The engine SHALL record the time ranges of failed chunks in Redis progress metadata so consumers can report which date intervals have missing data.

#### Scenario: Failed chunk range recorded in sequential path
- **WHEN** a chunk with `chunk_start` and `chunk_end` keys fails during sequential execution
- **THEN** `_update_progress()` SHALL store a `failed_ranges` field in the Redis HSET metadata
- **THEN** `failed_ranges` SHALL be a JSON array of objects, each with `start` and `end` string keys
- **THEN** the array SHALL contain one entry per failed chunk

#### Scenario: Failed chunk range recorded in parallel path
- **WHEN** a chunk with `chunk_start` and `chunk_end` keys fails during parallel execution
- **THEN** the failed chunk's time range SHALL be appended to `failed_ranges` in the same format as the sequential path

#### Scenario: No failed ranges when all chunks succeed
- **WHEN** all chunks complete successfully
- **THEN** the `failed_ranges` field SHALL NOT be present in Redis metadata

#### Scenario: ID-batch chunks produce no failed_ranges entries
- **WHEN** a chunk created by `decompose_by_ids()` (containing only an `ids` key, no `chunk_start`/`chunk_end`) fails
- **THEN** no entry SHALL be appended to `failed_ranges` for that chunk
- **THEN** `has_partial_failure` SHALL still be set to `True`
- **THEN** `failed` count SHALL still be incremented

#### Scenario: get_batch_progress returns failed_ranges
- **WHEN** `get_batch_progress()` is called after execution with failed chunks
- **THEN** the returned dict SHALL include `failed_ranges` as a JSON string parseable to a list of `{start, end}` objects

### Requirement: BatchQueryEngine SHALL retry transient chunk failures once
The engine SHALL retry chunk execution once for transient errors (Oracle timeout, connection errors) but SHALL NOT retry deterministic failures (memory guard, Redis store).

#### Scenario: Oracle timeout retried once
- **WHEN** `_execute_single_chunk()` raises an exception matching Oracle timeout patterns (`DPY-4024`, `ORA-01013`)
- **THEN** the chunk SHALL be retried exactly once
- **WHEN** the retry succeeds
- **THEN** the chunk SHALL be marked as successful

#### Scenario: Connection error retried once
- **WHEN** `_execute_single_chunk()` raises `TimeoutError`, `ConnectionError`, or `OSError`
- **THEN** the chunk SHALL be retried exactly once

#### Scenario: Retry exhausted marks chunk as failed
- **WHEN** a chunk fails on both the initial attempt and the retry
- **THEN** the chunk SHALL be marked as failed
- **THEN** `has_partial_failure` SHALL be set to `True`

#### Scenario: Memory guard failure NOT retried
- **WHEN** a chunk's DataFrame exceeds `BATCH_CHUNK_MAX_MEMORY_MB`
- **THEN** the chunk SHALL return `False` immediately without retry
- **THEN** the query function SHALL have been called exactly once for that chunk

#### Scenario: Redis store failure NOT retried
- **WHEN** `redis_store_chunk()` returns `False`
- **THEN** the chunk SHALL return `False` immediately without retry

### Requirement: reject_dataset_cache SHALL propagate partial failure metadata to API response
The cache service SHALL read batch execution metadata and include partial failure information in the API response `meta` field.

#### Scenario: Partial failure metadata included in response
- **WHEN** `execute_primary_query()` uses the batch engine path and `get_batch_progress()` returns `has_partial_failure=True`
- **THEN** the response `meta` dict SHALL include `has_partial_failure: true`
- **THEN** the response `meta` dict SHALL include `failed_chunk_count` as an integer
- **THEN** if `failed_ranges` is present, the response `meta` dict SHALL include `failed_ranges` as a list of `{start, end}` objects

#### Scenario: Metadata read before redis_clear_batch
- **WHEN** `execute_primary_query()` calls `get_batch_progress()`
- **THEN** the call SHALL occur after `merge_chunks()` and before `redis_clear_batch()`

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

### Requirement: reject_dataset_cache batch primary execution SHALL avoid paginated replay loops
Batch chunk execution for reject-history primary query SHALL avoid page-by-page replay against paginated list SQL semantics.

#### Scenario: Chunk execution avoids offset iteration
- **WHEN** batch engine executes a reject-history chunk in `execute_primary_query()`
- **THEN** chunk execution SHALL NOT iterate through `offset` pages to assemble full chunk data
- **THEN** chunk execution SHALL retrieve chunk data via the dedicated primary SQL path

#### Scenario: Chunk bind contract excludes pagination parameters
- **WHEN** chunk query parameters are prepared for batch execution
- **THEN** `offset` and `limit` SHALL NOT be required bind variables for normal chunk retrieval

### Requirement: Partial-failure resilience SHALL remain intact after source decoupling
Decoupling from paginated list SQL SHALL NOT regress partial-failure metadata behavior.

#### Scenario: Failed chunks still produce partial-failure metadata
- **WHEN** one or more reject-history chunks fail during batch execution
- **THEN** response `meta` SHALL still report partial-failure indicators according to existing resilience contract

#### Scenario: Successful chunks still merge and continue
- **WHEN** some chunks succeed and others fail
- **THEN** the system SHALL continue to merge successful chunks and return partial results
- **THEN** progress metadata SHALL remain available for diagnostics

