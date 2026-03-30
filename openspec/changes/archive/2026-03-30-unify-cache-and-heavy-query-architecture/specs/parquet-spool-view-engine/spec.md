## MODIFIED Requirements

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

## ADDED Requirements

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
