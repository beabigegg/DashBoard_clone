## ADDED Requirements

### Requirement: resource_dataset_cache SHALL propagate partial failure metadata to query result
`resource_dataset_cache.execute_primary_query()` SHALL read `get_batch_progress()` after each `execute_plan` call and include any `has_partial_failure` information in the returned result dict under `_meta`.

#### Scenario: Base chunk partial failure surfaced in result
- **WHEN** one or more base spool chunks fail during `execute_plan`
- **THEN** `execute_primary_query()` SHALL call `get_batch_progress("resource", engine_hash)`
- **THEN** the result dict SHALL contain `_meta.partial_failure.has_partial_failure = true`
- **THEN** the result dict SHALL contain `_meta.partial_failure.failed_chunk_count` as integer
- **THEN** the result dict SHALL contain `_meta.partial_failure.failed_ranges` as list of `{start, end}`
- **THEN** a WARNING log SHALL be emitted with the failed ranges

#### Scenario: OEE chunk partial failure surfaced in result
- **WHEN** one or more OEE spool chunks fail during `execute_plan`
- **THEN** `execute_primary_query()` SHALL call `get_batch_progress("resource_oee", oee_engine_hash)`
- **THEN** the result dict SHALL include partial failure info under `_meta.partial_failure`
- **THEN** if both base and OEE have partial failures the metadata SHALL merge both counts

#### Scenario: No partial failure info when all chunks succeed
- **WHEN** all base and OEE chunks succeed
- **THEN** `_meta` SHALL NOT contain a `partial_failure` key

#### Scenario: Cache-hit path does not re-surface stale partial failure
- **WHEN** `execute_primary_query()` returns early due to full spool cache hit (both base + OEE available)
- **THEN** the partial failure check SHALL be skipped
- **THEN** the result SHALL NOT include `_meta.partial_failure`

### Requirement: hold_dataset_cache SHALL propagate partial failure metadata to query result
`hold_dataset_cache` SHALL read `get_batch_progress()` after `execute_plan` and include partial failure info in `_meta`.

#### Scenario: Hold chunk partial failure surfaced
- **WHEN** one or more hold chunks fail during `execute_plan`
- **THEN** the cache service SHALL surface `_meta.partial_failure` in the result dict
- **THEN** a WARNING log SHALL be emitted

#### Scenario: No partial failure on success
- **WHEN** all hold chunks complete successfully
- **THEN** `_meta` SHALL NOT contain `partial_failure`

### Requirement: job_query_service SHALL propagate partial failure metadata to query result
`job_query_service` SHALL read `get_batch_progress()` after `execute_plan` and include partial failure info in the returned result.

#### Scenario: Job chunk partial failure surfaced
- **WHEN** one or more job query chunks fail
- **THEN** the service SHALL include `_meta.partial_failure` in the result
- **THEN** a WARNING log SHALL be emitted

### Requirement: production_history_service SHALL propagate partial failure metadata to query result
`production_history_service` SHALL read `get_batch_progress()` after `execute_plan` and include partial failure info in the returned result.

#### Scenario: Production history chunk partial failure surfaced
- **WHEN** one or more production history chunks fail
- **THEN** the service SHALL include `_meta.partial_failure` in the result
- **THEN** a WARNING log SHALL be emitted

### Requirement: mid_section_defect_service SHALL propagate partial failure metadata to query result
`mid_section_defect_service` SHALL read `get_batch_progress()` after `execute_plan` and include partial failure info in the returned result.

#### Scenario: MSD detection chunk partial failure surfaced
- **WHEN** one or more MSD detection chunks fail
- **THEN** the service SHALL include `_meta.partial_failure` in the result
- **THEN** a WARNING log SHALL be emitted

---

## E2E Test Requirements

### Requirement: Partial failure propagation SHALL be verified by unit tests per service
Each service that calls `execute_plan` SHALL have a pytest unit test confirming that `has_partial_failure=True` in the batch progress metadata is surfaced in the result `_meta`.

#### Scenario: Unit test — resource_dataset_cache surfaces base chunk failure in _meta
- **WHEN** `execute_plan` for the base path has `get_batch_progress` returning `has_partial_failure=True, failed_chunk_count=1, failed_ranges=[{start, end}]`
- **THEN** `execute_primary_query()` result SHALL contain `_meta["partial_failure"]["has_partial_failure"] == True`
- **THEN** `_meta["partial_failure"]["failed_ranges"]` SHALL be a non-empty list

#### Scenario: Unit test — resource_dataset_cache OEE chunk failure in _meta
- **WHEN** `execute_plan` for the OEE path returns partial failure
- **THEN** `_meta["partial_failure"]` SHALL include OEE failure information

#### Scenario: Unit test — hold_dataset_cache surfaces chunk failure in _meta
- **WHEN** hold chunk partial failure is present
- **THEN** result `_meta["partial_failure"]["has_partial_failure"]` SHALL be True

#### Scenario: Unit test — job_query_service surfaces chunk failure in _meta
- **WHEN** job chunk partial failure is present
- **THEN** result `_meta["partial_failure"]["has_partial_failure"]` SHALL be True

#### Scenario: Unit test — production_history_service surfaces chunk failure in _meta
- **WHEN** production history chunk partial failure is present
- **THEN** result `_meta["partial_failure"]["has_partial_failure"]` SHALL be True

#### Scenario: Unit test — mid_section_defect_service surfaces chunk failure in _meta
- **WHEN** MSD detection chunk partial failure is present
- **THEN** result `_meta["partial_failure"]["has_partial_failure"]` SHALL be True

#### Scenario: Unit test — no partial failure when all chunks succeed
- **WHEN** `get_batch_progress` returns `has_partial_failure=False`
- **THEN** result `_meta` SHALL NOT contain a `partial_failure` key for any service

### Requirement: Partial failure warning log SHALL be verified
A pytest unit test SHALL assert that `logger.warning` is called when partial failure is detected in any service.

#### Scenario: Unit test — warning emitted on base chunk failure
- **WHEN** `execute_primary_query()` detects partial failure in resource base chunks
- **THEN** a `logging.WARNING` level message SHALL be emitted containing the `failed_ranges` information

#### Scenario: Unit test — no warning emitted on success
- **WHEN** all chunks complete successfully
- **THEN** no WARNING log about partial failure SHALL be emitted

### Requirement: reject_dataset_cache partial failure e2e SHALL verify API response includes _meta
An e2e test in `tests/e2e/test_reject_history_e2e.py` (or `tests/test_reject_dataset_cache.py`) SHALL verify that partial failure metadata reaches the API response.

#### Scenario: E2E — reject query response includes partial_failure in _meta when chunk fails
- **WHEN** a reject history batch query has one failed chunk
- **THEN** the `GET /api/reject-history/query` or `POST` response body
- **THEN** SHALL include a `meta` (or `_meta`) field with `has_partial_failure: true`

## MODIFIED Requirements

### Requirement: reject_dataset_cache SHALL propagate partial failure metadata to API response
The cache service SHALL read batch execution metadata and include partial failure information in the API response `meta` field.

#### Scenario: Partial failure metadata included in response
- **WHEN** `execute_primary_query()` uses the batch engine path and `get_batch_progress()` returns `has_partial_failure=True`
- **THEN** the response `meta` dict SHALL include `has_partial_failure: true`
- **THEN** the response `meta` dict SHALL include `failed_chunk_count` as an integer
- **THEN** if `failed_ranges` is present, the response `meta` dict SHALL include `failed_ranges` as a list of `{start, end}` objects
- **THEN** a WARNING log SHALL be emitted listing the failed ranges

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
