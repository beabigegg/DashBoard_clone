# event-fetcher-unified Specification

## Purpose
TBD - created by archiving change unified-lineage-engine. Update Purpose after archive.
## Requirements
### Requirement: EventFetcher SHALL provide unified cached event querying across domains
`EventFetcher` SHALL encapsulate batch event queries with L1/L2 layered cache and rate limit bucket configuration, supporting domains: `history`, `materials`, `rejects`, `holds`, `jobs`, `upstream_history`, `downstream_rejects`.

#### Scenario: Cache miss for event domain query
- **WHEN** `EventFetcher` is called for a domain with container IDs and no cache exists
- **THEN** the domain query SHALL execute against Oracle via `read_sql_df_slow()` (non-pooled dedicated connection)
- **THEN** each batch query SHALL use `timeout_seconds=60`
- **THEN** the result SHALL be stored in L2 Redis cache with key format `evt:{domain}:{sorted_cids_hash}` if CID count is within cache threshold
- **THEN** L1 memory cache SHALL also be populated if CID count is within cache threshold

#### Scenario: Cache hit for event domain query
- **WHEN** `EventFetcher` is called for a domain and L2 Redis cache contains a valid entry
- **THEN** the cached result SHALL be returned without executing Oracle query
- **THEN** DB connection pool SHALL NOT be consumed

#### Scenario: Rate limit bucket per domain
- **WHEN** `EventFetcher` is used from a route handler
- **THEN** each domain SHALL have a configurable rate limit bucket aligned with `configured_rate_limit()` pattern
- **THEN** rate limit configuration SHALL be overridable via environment variables

#### Scenario: Large CID set exceeds cache threshold
- **WHEN** the normalized CID count exceeds `CACHE_SKIP_CID_THRESHOLD` (default 10000, env: `EVENT_FETCHER_CACHE_SKIP_CID_THRESHOLD`)
- **THEN** EventFetcher SHALL skip both L1 and L2 cache writes
- **THEN** a warning log SHALL be emitted with domain name, CID count, and threshold value
- **THEN** the query result SHALL still be returned to the caller

#### Scenario: Batch concurrency default
- **WHEN** EventFetcher processes batches for a domain with >1000 CIDs
- **THEN** the default `EVENT_FETCHER_MAX_WORKERS` SHALL be 2 (env: `EVENT_FETCHER_MAX_WORKERS`)

### Requirement: EventFetcher SHALL separate records payload from quality metadata
`EventFetcher` SHALL return domain records and completeness metadata as separate structures, and SHALL NOT inject metadata entries into the `CONTAINERID -> records` map.

#### Scenario: Truncation metadata is separated from records
- **WHEN** total fetched rows for a domain reaches `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL stop adding more records for that domain
- **THEN** EventFetcher SHALL return `quality_meta.status = "truncated"` with row-limit details
- **THEN** returned records map SHALL contain only container-id keys mapped to record arrays

#### Scenario: Normal domain query has complete metadata
- **WHEN** a domain query completes without truncation/failure
- **THEN** EventFetcher SHALL return `quality_meta.status = "complete"`
- **THEN** EventFetcher SHALL still return records map in the same structural shape used by callers

### Requirement: EventFetcher truncation SHALL remain configurable and observable
Truncation behavior SHALL remain controlled by environment configuration and visible in logs/metadata.

#### Scenario: Configurable total-row guard
- **WHEN** operator sets `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL enforce the configured limit at runtime
- **THEN** returned `quality_meta` SHALL include the effective limit value

#### Scenario: Truncation observability
- **WHEN** truncation is triggered
- **THEN** a warning log SHALL include domain, observed rows, and row limit
- **THEN** caller-facing metadata SHALL expose the same truncation context

### Requirement: EventFetcher SHALL support spool-oriented execution for migrated callers
EventFetcher and its callers SHALL support writing large domain results into spool-oriented stage outputs so that large result sets do not need to remain fully materialized in memory.

#### Scenario: Migrated caller uses spool-oriented path
- **WHEN** a caller has been migrated to the unified spool pipeline
- **THEN** EventFetcher output SHALL be suitable for stage spool persistence and downstream DuckDB processing

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

### Requirement: EventFetcher row guard retirement SHALL be gated
The existing total-row truncation guard SHALL only be removed after the relevant callers are fully migrated to spool-safe execution.

#### Scenario: Legacy caller still depends on in-memory result assembly
- **WHEN** a caller still assembles large event results in memory (e.g., `fetch_events()` direct call)
- **THEN** the existing row guard (`EVENT_FETCHER_MAX_TOTAL_ROWS`) SHALL remain for that path

#### Scenario: Spool-safe path complete — MSD compat job and trace job MSD branch
- **WHEN** `_execute_msd_compat_job()` and `_execute_trace_events_job()` MSD branch call `fetch_events_to_parquet()` to stream directly to spool
- **THEN** the row truncation guard SHALL NOT be applied for those callers
- **THEN** `fetch_events_to_parquet()` SHALL be the designated spool-write entry point with no row cap
