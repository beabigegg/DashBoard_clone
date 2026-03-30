## MODIFIED Requirements

### Requirement: Hard limits SHALL only be removed after the corresponding legacy path is retired
Row/CID/RSS guards that currently protect in-memory or sync paths SHALL remain until the relevant query path is fully migrated to the spool-safe execution model.

#### Scenario: EventFetcher row guard retired for spool-write callers
- **WHEN** `_execute_msd_compat_job()` and `_execute_trace_events_job()` MSD branch have been fully migrated to call `fetch_events_to_parquet()` (streaming, no in-memory accumulation)
- **THEN** `EVENT_FETCHER_MAX_TOTAL_ROWS` guard SHALL be considered retired for those callers
- **THEN** `fetch_events()` direct callers (non-spool interactive paths) SHALL still enforce the guard

#### Scenario: material_trace MB guard retired for spool-write path
- **WHEN** `execute_to_spool()` has been migrated to `_execute_batched_query_to_parquet()` streaming path
- **THEN** `MATERIAL_TRACE_MAX_RESULT_MB` (256 MB DataFrame guard) SHALL be considered retired for the spool-write path
- **THEN** `_check_memory_guard()` SHALL remain active for interactive query paths (`forward_query`, `reverse_query`, `export_csv`)

#### Scenario: Guard still active for non-migrated paths
- **WHEN** any path still assembles full Oracle results in memory before writing to spool
- **THEN** the corresponding row/MB guard SHALL remain until that path completes migration

## ADDED Requirements

### Requirement: MSD events spool SHALL be assembled via streaming multi-domain merge
When the MSD trace job writes events from multiple domains to a single spool file, the merge SHALL be performed as a streaming operation.

#### Scenario: Multi-domain streaming spool merge
- **WHEN** `_write_msd_events_spool_from_paths()` is called with per-domain parquet paths
- **THEN** each domain parquet SHALL be read via `pq.ParquetFile.iter_batches()` and written to the output spool without loading all domains simultaneously into memory
- **THEN** the resulting spool SHALL be registered with `register_stage_spool_file()` for DuckDB downstream access

### Requirement: MSD trace job SHALL derive aggregation from DuckDB spool after streaming write
Once the MSD events spool has been written by the streaming path, the job SHALL use `MsdDuckdbRuntime` for aggregation rather than in-memory `build_trace_aggregation_from_events()`.

#### Scenario: Aggregation from freshly written spool
- **WHEN** `_build_job_msd_aggregation()` is called after `_write_msd_events_spool_from_paths()` completes successfully
- **THEN** it SHALL attempt `MsdDuckdbRuntime(trace_query_id).get_summary()` first
- **THEN** on spool hit it SHALL return the DuckDB summary with `domain_quality_meta` injected
- **THEN** the in-memory `build_trace_aggregation_from_events()` path SHALL NOT be executed when spool is available
