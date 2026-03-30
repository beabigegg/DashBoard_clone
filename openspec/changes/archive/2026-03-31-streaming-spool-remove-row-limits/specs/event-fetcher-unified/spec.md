## ADDED Requirements

### Requirement: EventFetcher SHALL provide a streaming spool-write path without row guard
`EventFetcher` SHALL expose `_stream_batches_to_writer()` and an updated `fetch_events_to_parquet()` that stream Oracle results directly to a parquet file via `pyarrow.ParquetWriter`, without accumulating all rows in memory and without applying `EVENT_FETCHER_MAX_TOTAL_ROWS`.

#### Scenario: Streaming spool write for normal domain
- **WHEN** `fetch_events_to_parquet(container_ids, domain, dest_path)` is called for any domain except `jobs`
- **THEN** data SHALL be streamed via `read_sql_df_slow_iter` → `pyarrow.ParquetWriter` without an in-memory row accumulation
- **THEN** `EVENT_FETCHER_MAX_TOTAL_ROWS` row guard SHALL NOT be applied
- **THEN** the function SHALL return `(row_count: int, quality_meta: Dict)` where `quality_meta.status` is `"complete"` when no failures occurred

#### Scenario: Streaming spool write for jobs domain
- **WHEN** `fetch_events_to_parquet(container_ids, "jobs", dest_path)` is called
- **THEN** each row's `CONTAINERIDS` string SHALL be expanded so that one row is emitted per matching container ID
- **THEN** the expanded rows SHALL be written directly to the parquet file without full in-memory accumulation

#### Scenario: Empty result produces valid empty parquet
- **WHEN** `fetch_events_to_parquet()` returns zero rows for a domain
- **THEN** an empty parquet file SHALL be written to `dest_path`
- **THEN** the function SHALL return `(0, quality_meta)` with `quality_meta.status = "complete"`

#### Scenario: Partial batch failure in streaming path
- **WHEN** one or more batch queries fail during `fetch_events_to_parquet()`
- **THEN** rows from successful batches SHALL still be written to the parquet file
- **THEN** the returned `quality_meta.status` SHALL be `"partial"` with failure details

## MODIFIED Requirements

### Requirement: EventFetcher row guard retirement SHALL be gated
The existing total-row truncation guard SHALL only be removed after the relevant callers are fully migrated to spool-safe execution.

#### Scenario: Legacy caller still depends on in-memory result assembly
- **WHEN** a caller still assembles large event results in memory (e.g., `fetch_events()` direct call)
- **THEN** the existing row guard (`EVENT_FETCHER_MAX_TOTAL_ROWS`) SHALL remain for that path

#### Scenario: Spool-safe path complete — MSD compat job and trace job MSD branch
- **WHEN** `_execute_msd_compat_job()` and `_execute_trace_events_job()` MSD branch call `fetch_events_to_parquet()` to stream directly to spool
- **THEN** the row truncation guard SHALL NOT be applied for those callers
- **THEN** `fetch_events_to_parquet()` SHALL be the designated spool-write entry point with no row cap
