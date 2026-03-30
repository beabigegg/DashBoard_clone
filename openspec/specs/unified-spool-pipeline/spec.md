# unified-spool-pipeline Specification

## Purpose
Define the common RQ -> Parquet spool -> DuckDB execution model for heavy non-realtime reports.

## Requirements
### Requirement: Non-realtime reports SHALL converge on RQ→Parquet→DuckDB execution
All non-realtime report queries (reject-history, yield-alert, resource-history, hold-overview, production-history, MSD trace, query-tool trace, material-trace, **job-query, MSD station-detection**) SHALL ultimately execute heavy Oracle work in RQ workers and persist intermediate/final results to parquet spool files. Subsequent aggregation, filtering, pagination, sorting, and export SHALL read from parquet via DuckDB where practical.

#### Scenario: Spool hit
- **WHEN** a valid spool exists for a report query
- **THEN** the route SHALL reuse that spool and avoid re-querying Oracle

#### Scenario: Spool miss
- **WHEN** a report query has no valid spool
- **THEN** the system SHALL execute the Oracle work through the unified spool pipeline
- **THEN** the externally visible HTTP behavior MAY be either compatibility-preserving sync bootstrap or `202 + polling`, depending on the report's existing API contract and migration state

#### Scenario: job_query engine path uses spool
- **WHEN** `job_query_service` uses the batch engine path (long date range via `should_decompose_by_time`)
- **THEN** the engine result SHALL be merged via `merge_chunks_to_spool()` into a parquet spool file
- **THEN** the result SHALL be read from spool via DuckDB, not from a Redis-cached DataFrame

#### Scenario: msd_detect engine path uses spool
- **WHEN** `mid_section_defect_service._fetch_station_detection()` uses the batch engine path (long date range)
- **THEN** the engine result SHALL be merged via `merge_chunks_to_spool()` into a parquet spool file
- **THEN** the result SHALL be read from spool via DuckDB, not from a pandas DataFrame merge

### Requirement: Unified spool pipeline SHALL support multi-stage jobs
Reports that require multiple Oracle stages SHALL execute those stages within a single logical pipeline with stage-aware progress and stage-level spool metadata.

#### Scenario: Multi-stage execution
- **WHEN** a report requires seed, lineage, events, and aggregation stages
- **THEN** each stage SHALL produce its own spool artifact or registered stage output
- **THEN** the pipeline SHALL expose stage progress through shared async job metadata

### Requirement: Unified spool pipeline SHALL preserve compatibility contracts until migration completes
The adoption of the unified spool pipeline SHALL NOT by itself authorize removal of existing endpoints or changes to response semantics that are still consumed by frontend code, AI function registry entries, tests, or documented API contracts.

#### Scenario: Existing synchronous bootstrap contract
- **WHEN** a route currently returns first-page data synchronously
- **THEN** the route MAY keep that external behavior while moving its internal execution to the unified spool pipeline

#### Scenario: Endpoint retirement
- **WHEN** a legacy endpoint is proposed for removal
- **THEN** all known consumers, tests, and contract documents SHALL be migrated first

### Requirement: Hard limits SHALL only be removed after the corresponding legacy path is retired
Row/CID/RSS guards that currently protect in-memory or sync paths SHALL remain until the relevant query path is fully migrated to the spool-safe execution model.

#### Scenario: Trace events guard retirement
- **WHEN** trace events are guaranteed to execute through RQ/spool-safe paths
- **THEN** CID and sync RSS rejection guards MAY be removed

#### Scenario: Legacy path still active
- **WHEN** a compatibility or sync path still exists
- **THEN** existing protection limits SHALL NOT be removed prematurely

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
