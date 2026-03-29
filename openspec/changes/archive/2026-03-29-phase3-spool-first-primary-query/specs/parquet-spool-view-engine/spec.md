## MODIFIED Requirements

### Requirement: DuckDB SQL runtime modules SHALL compute view results from Parquet spool out-of-core
Each dataset that has a Parquet spool SHALL have a corresponding SQL runtime module that computes view results using DuckDB `read_parquet()` without loading the full dataset into memory.

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

### Requirement: DuckDB SQL runtime modules SHALL be gated by feature flags
Each SQL runtime module SHALL be controlled by a boolean feature flag that defaults to enabled.

#### Scenario: Feature flag controls view path selection
- **WHEN** the feature flag (e.g., `RESOURCE_HISTORY_SQL_VIEW_ENABLED`) is set to `false`
- **THEN** the view query SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT use the Pandas-based derivation path as a fallback
- **WHEN** the feature flag is set to `true` (default)
- **THEN** the view query SHALL attempt the DuckDB SQL runtime path
