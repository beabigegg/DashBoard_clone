## MODIFIED Requirements

### Requirement: reject_dataset_cache SHALL use streaming merge for engine path
The `execute_primary_query()` function SHALL use `merge_chunks_to_spool()` instead of `merge_chunks()` for the batch engine path. **Additionally, `job_query_service` and `mid_section_defect_service` SHALL use `merge_chunks_to_spool()` for their batch engine paths.**

#### Scenario: Engine path uses streaming merge
- **WHEN** `execute_primary_query()` uses the batch engine path (`use_engine=True`)
- **THEN** it SHALL call `merge_chunks_to_spool()` instead of `merge_chunks()`
- **THEN** the resulting spool file SHALL be registered in the existing spool metadata store

#### Scenario: Partial failure metadata preserved
- **WHEN** streaming merge is used
- **THEN** `get_batch_progress()` SHALL be called after `merge_chunks_to_spool()` and before `redis_clear_batch()`
- **THEN** partial failure metadata SHALL be propagated to the response `meta` dict identically to the previous merge_chunks path

#### Scenario: Direct path unchanged
- **WHEN** `execute_primary_query()` uses the direct path (`use_engine=False`)
- **THEN** the existing logic SHALL remain unchanged

#### Scenario: Existing merge_chunks preserved
- **WHEN** other callers (non-reject) use `merge_chunks()`
- **THEN** the original `merge_chunks()` function SHALL remain available and unchanged

#### Scenario: job_query engine path uses streaming merge
- **WHEN** `job_query_service` detects a long date range via `should_decompose_by_time()`
- **THEN** it SHALL call `merge_chunks_to_spool()` instead of `merge_chunks()`
- **THEN** it SHALL register the spool file via `register_spool_file()`
- **THEN** it SHALL NOT call `redis_store_df()` for the merged result

#### Scenario: msd_detect engine path uses streaming merge
- **WHEN** `mid_section_defect_service._fetch_station_detection()` detects a long date range
- **THEN** it SHALL call `merge_chunks_to_spool()` instead of `merge_chunks()`
- **THEN** it SHALL register the spool file via `register_spool_file()`
- **THEN** the result SHALL be read from parquet via DuckDB for downstream consumption
