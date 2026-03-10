# streaming-chunk-merge Specification

## Purpose
Reduce reject-history merge peak memory by streaming chunk merge output directly to parquet spool.

## Requirements
### Requirement: BatchQueryEngine SHALL provide streaming merge to parquet spool
A `merge_chunks_to_spool()` function SHALL write chunk data incrementally to a parquet spool file using `iterate_chunks()`, avoiding full in-memory accumulation.

#### Scenario: Streaming merge writes incrementally
- **WHEN** `merge_chunks_to_spool()` is called with a valid `cache_prefix` and `query_hash`
- **THEN** it SHALL iterate chunks via `iterate_chunks()` one at a time
- **THEN** each chunk SHALL be written to a parquet file via `pyarrow.ParquetWriter`
- **THEN** at most one chunk DataFrame SHALL be held in memory at any time

#### Scenario: Schema inferred from first chunk
- **WHEN** the first non-empty chunk is yielded
- **THEN** `merge_chunks_to_spool()` SHALL infer the parquet schema from that chunk's `pyarrow.Table`
- **THEN** the `ParquetWriter` SHALL be opened with that schema

#### Scenario: max_total_rows enforcement
- **WHEN** `max_total_rows` is provided
- **THEN** `merge_chunks_to_spool()` SHALL track cumulative row count across chunks
- **WHEN** cumulative rows exceed `max_total_rows` and `overflow_mode="error"`
- **THEN** it SHALL raise `MergeChunksMaxRowsExceeded` with `observed_rows` and `chunk_index`
- **WHEN** cumulative rows exceed `max_total_rows` and `overflow_mode="truncate"`
- **THEN** it SHALL truncate the current chunk and stop processing further chunks

#### Scenario: Empty result
- **WHEN** all chunks are empty or missing
- **THEN** `merge_chunks_to_spool()` SHALL return `(None, 0)` without creating a spool file

#### Scenario: Return value
- **WHEN** merge completes successfully with data
- **THEN** `merge_chunks_to_spool()` SHALL return `(spool_path, total_rows)` where `spool_path` is the absolute path to the written parquet file

#### Scenario: Spool file cleanup on failure
- **WHEN** an exception occurs during streaming write
- **THEN** the partially written spool file SHALL be deleted in a `finally` block

### Requirement: reject_dataset_cache SHALL use streaming merge for engine path
The `execute_primary_query()` function SHALL use `merge_chunks_to_spool()` instead of `merge_chunks()` for the batch engine path.

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

### Requirement: Gunicorn max_requests SHALL be tuned for RSS-guard-driven recycling
The `GUNICORN_MAX_REQUESTS` configuration SHALL be raised to reduce unnecessary worker recycling during sustained load.

#### Scenario: Default configuration
- **WHEN** `.env` is loaded
- **THEN** `GUNICORN_MAX_REQUESTS` SHALL be 5000
- **THEN** `GUNICORN_MAX_REQUESTS_JITTER` SHALL be 1000

#### Scenario: Worker recycling frequency reduced
- **WHEN** the system is under sustained load
- **THEN** workers SHALL recycle after 4000-6000 requests (5000 +/- 1000 jitter) instead of 900-1500
