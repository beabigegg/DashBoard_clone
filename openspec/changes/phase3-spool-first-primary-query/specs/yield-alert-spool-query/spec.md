## MODIFIED Requirements

### Requirement: Yield Alert view SHALL use DuckDB SQL runtime as primary computation path
The system SHALL provide a DuckDB-based SQL runtime (`yield_alert_sql_runtime.py`) that queries spool parquet files to compute all view aggregations without loading full DataFrames into pandas.

#### Scenario: DuckDB-first view computation
- **WHEN** `apply_view` is called and a parquet spool file exists for the query_id
- **THEN** the system SHALL execute summary, trend, heatmap, station_summary, package_summary, and alerts computations via DuckDB SQL
- **THEN** the result structure SHALL be identical to the previous pandas computation path

#### Scenario: DuckDB path computes alerts with SQL-level pagination
- **WHEN** DuckDB SQL runtime computes alerts
- **THEN** filtering, grouping, sorting, and pagination SHALL be performed within DuckDB SQL (not Python-side materialization)

#### Scenario: DuckDB runtime failure or spool miss returns cache_expired
- **WHEN** `apply_view` is called but no parquet spool file exists for the query_id, or the DuckDB runtime encounters an error
- **THEN** the system SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT fall back to the pandas computation path
- **THEN** the client SHALL re-trigger `execute_primary_query()`

#### Scenario: DuckDB disabled via feature flag
- **WHEN** `YIELD_ALERT_SQL_VIEW_ENABLED=0`
- **THEN** the system SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT use the pandas path as a fallback
