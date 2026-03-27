## MODIFIED Requirements

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
