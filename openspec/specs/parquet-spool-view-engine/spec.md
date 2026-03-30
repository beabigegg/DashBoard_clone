## Purpose

Define the canonical Parquet spool write and DuckDB view-engine contracts for heavy-query modules. All covered modules SHALL write primary query results to Parquet spool and compute view results out-of-core via DuckDB.

## Requirements

### Requirement: Dataset cache modules SHALL write primary query results to Parquet spool via streaming merge
All covered heavy-query modules that produce reusable result sets SHALL write those results to Parquet spool, using streaming merge for chunked execution paths and spool-safe direct persistence for smaller direct paths.

#### Scenario: Chunked heavy query writes to spool
- **WHEN** a covered heavy-query module executes a chunked Oracle query plan
- **THEN** the module SHALL stream-merge chunk results into a canonical Parquet spool result
- **THEN** peak merge memory SHALL remain proportional to chunk size, not full result size

#### Scenario: Direct heavy query writes to spool
- **WHEN** a covered heavy-query module executes a non-chunked direct query path
- **THEN** the module SHALL still persist the reusable result body to canonical Parquet spool
- **THEN** the direct path SHALL not switch to Redis body storage as an alternative L2 representation

#### Scenario: Streaming merge to spool after chunked query
- **WHEN** `execute_plan()` completes all chunks for a primary query
- **THEN** `merge_chunks_to_spool()` SHALL be called to stream-merge Redis chunks into a single Parquet spool file
- **THEN** peak memory during merge SHALL be proportional to a single chunk, not the full result set
- **THEN** the spool file path and row count SHALL be recorded in Redis metadata

#### Scenario: Spool file registration for DuckDB access
- **WHEN** a spool file is created via `merge_chunks_to_spool()`
- **THEN** the spool file SHALL be registered via `store_spooled_df()` with namespace, query_id, and TTL
- **THEN** the spool metadata SHALL include row_count, file_size_bytes, and columns_hash

### Requirement: DuckDB SQL runtime modules SHALL compute view results from Parquet spool out-of-core
Covered heavy-query modules SHALL use DuckDB-over-Parquet as the canonical runtime for page, view, export, and replayable result computation.

#### Scenario: View and export from spool
- **WHEN** a client requests pagination, filtered views, derived summaries, or export for a reusable heavy-query result
- **THEN** the runtime SHALL resolve the canonical spool and execute through DuckDB or an equivalent spool-safe reader
- **THEN** the runtime SHALL avoid full-result pandas materialization in the web worker as the primary path

#### Scenario: Spool miss or runtime failure
- **WHEN** the canonical spool cannot be resolved or the DuckDB runtime cannot execute
- **THEN** the system SHALL return an explicit expired/unavailable result lifecycle response
- **THEN** the module SHALL not silently fall back to a second canonical result-storage model

#### Scenario: Out-of-core view computation
- **WHEN** a view query is received with a valid query_id
- **THEN** the SQL runtime SHALL locate the spool file via `query_spool_store`
- **THEN** DuckDB SHALL execute SQL queries against the Parquet file using `read_parquet(path)`
- **THEN** the view result SHALL be returned as a Python dict without constructing a Pandas DataFrame

#### Scenario: DuckDB runtime failure or spool miss returns cache_expired
- **WHEN** the SQL runtime cannot execute (DuckDB import failed, spool file missing, or runtime error)
- **THEN** the system SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT fall back to the Pandas-based view derivation
- **THEN** the client SHALL re-trigger `execute_primary_query()` to rebuild the spool

### Requirement: Heavy-query DuckDB runtimes SHALL use a shared bounded runtime policy
All covered DuckDB heavy-query runtimes SHALL use a shared runtime policy for memory and concurrency governance.

#### Scenario: Runtime connection creation
- **WHEN** a heavy-query runtime opens a DuckDB connection
- **THEN** it SHALL apply the shared memory-limit policy
- **THEN** it SHALL apply the shared thread-limit policy
- **THEN** equivalent heavy-query runtimes SHALL not diverge into unrelated per-module defaults

#### Scenario: Runtime observability
- **WHEN** a heavy-query runtime executes a page, view, or export operation
- **THEN** logs and telemetry SHALL identify the canonical query/spool identity and whether the request was a spool hit or lifecycle miss

### Requirement: DuckDB SQL runtime modules SHALL be gated by feature flags
Each SQL runtime module SHALL be controlled by a boolean feature flag that defaults to enabled.

#### Scenario: Feature flag controls view path selection
- **WHEN** the feature flag (e.g., `RESOURCE_HISTORY_SQL_VIEW_ENABLED`) is set to `false`
- **THEN** the view query SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT use the Pandas-based derivation path as a fallback
- **WHEN** the feature flag is set to `true` (default)
- **THEN** the view query SHALL attempt the DuckDB SQL runtime path

### Requirement: Query-level memory guard SHALL NOT reject queries when chunked processing is used
When a dataset cache module uses `batch_query_engine` for chunked queries and `merge_chunks_to_spool()` for streaming output, the query-level `enforce_dataset_memory_guard` SHALL NOT be applied to reject queries.

#### Scenario: Large query processed without rejection
- **WHEN** a primary query would produce a dataset exceeding the previous `max_input_mb` threshold
- **THEN** the system SHALL process it via chunked queries (each chunk ≤ `MAX_ROWS_PER_CHUNK`)
- **THEN** chunks SHALL be stream-merged to Parquet spool without loading the full dataset
- **THEN** the query SHALL NOT be rejected with MemoryError

#### Scenario: Row count and disk space limits are preserved
- **WHEN** the total row count exceeds `MAX_TOTAL_ROWS` (e.g., 200,000)
- **THEN** `merge_chunks_to_spool()` SHALL truncate or error based on `overflow_mode`
- **WHEN** the spool directory exceeds `QUERY_SPOOL_MAX_BYTES` (e.g., 2GB)
- **THEN** spool cleanup SHALL evict expired files before writing new ones

### Requirement: Parquet spool files SHALL be downloadable via HTTP API
The system SHALL provide an HTTP endpoint for frontend clients to download Parquet spool files.

#### Scenario: Successful Parquet download
- **WHEN** a GET request is made to `/api/spool/{namespace}/{query_id}.parquet`
- **THEN** the server SHALL validate the query_id format and check spool metadata exists
- **THEN** the server SHALL stream the Parquet file with `Content-Type: application/octet-stream`
- **THEN** the response SHALL include `Content-Length` and `Content-Disposition` headers

#### Scenario: Expired or missing spool file
- **WHEN** a GET request is made for a query_id whose spool file has expired or does not exist
- **THEN** the server SHALL return HTTP 410 (Gone) with an error message

#### Scenario: Security validation
- **WHEN** a GET request is made to the spool download endpoint
- **THEN** the server SHALL validate the CSRF token
- **THEN** the server SHALL use `query_spool_store` path resolution to prevent directory traversal
- **THEN** the namespace parameter SHALL be validated against a whitelist of known namespaces

### Requirement: Spool store SHALL support multi-file namespace and DuckDB JOIN
The query spool store SHALL support storing multiple parquet files under a single job/session namespace and providing them to DuckDB for JOIN operations.

#### Scenario: Multi-file spool storage
- **WHEN** a multi-stage pipeline (e.g., MSD: seed, lineage, events) produces multiple parquet files
- **THEN** each file SHALL be stored under the same namespace with a stage suffix (e.g., `msd_{hash}_seed.parquet`, `msd_{hash}_lineage.parquet`, `msd_{hash}_events.parquet`)
- **THEN** Redis metadata SHALL track all files belonging to the namespace

#### Scenario: DuckDB reads multiple parquet files
- **WHEN** a DuckDB runtime needs to aggregate across multiple spool files
- **THEN** it SHALL use `duckdb.read_parquet(['file1.parquet', 'file2.parquet'])` or multiple `read_parquet()` calls in a JOIN
- **THEN** DuckDB SHALL handle the JOIN without loading all files into Python memory

#### Scenario: Namespace-level TTL and cleanup
- **WHEN** a spool namespace expires (TTL reached)
- **THEN** ALL parquet files under that namespace SHALL be deleted
- **THEN** the Redis metadata for the namespace SHALL be removed

### Requirement: Spool store capacity SHALL be configurable up to 10 GB
The spool directory capacity limit SHALL be increased and made configurable.

#### Scenario: Increased spool capacity
- **WHEN** the spool store initializes
- **THEN** `QUERY_SPOOL_MAX_BYTES` default SHALL be 10,737,418,240 (10 GB)
- **THEN** the value SHALL be configurable via environment variable

#### Scenario: Spool TTL default changed to 3 hours
- **WHEN** a spool file is stored without explicit TTL
- **THEN** the default TTL SHALL be 10800 seconds (3 hours)
- **THEN** this SHALL be configurable via `SPOOL_TTL_SECONDS` environment variable
