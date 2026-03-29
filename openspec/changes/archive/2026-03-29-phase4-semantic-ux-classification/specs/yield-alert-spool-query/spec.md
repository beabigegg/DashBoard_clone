## MODIFIED Requirements

### Requirement: Yield Alert view SHALL use DuckDB SQL runtime as primary computation path
The system SHALL provide a DuckDB-based SQL runtime (`yield_alert_sql_runtime.py`) that queries spool parquet files to compute all view aggregations without loading full DataFrames into pandas.

The yield-alert domain is classified as **Type A** per the `query-response-semantic-contract`. On HTTP 410, the client SHALL re-trigger `execute_primary_query()` synchronously.

#### Scenario: DuckDB-first view computation
- **WHEN** `apply_view` is called and a parquet spool file exists for the query_id
- **THEN** the system SHALL execute summary, trend, heatmap, station_summary, package_summary, and alerts computations via DuckDB SQL
- **THEN** the result structure SHALL be identical to the pandas computation path

#### Scenario: DuckDB path computes alerts with SQL-level pagination
- **WHEN** DuckDB SQL runtime computes alerts
- **THEN** filtering, grouping, sorting, and pagination SHALL be performed within DuckDB SQL (not Python-side materialization)
- **THEN** only the requested page of alert rows SHALL be returned to Python

#### Scenario: Spool miss returns None (cache expired)
- **WHEN** `apply_view` is called but no parquet spool file exists for the query_id
- **THEN** `apply_view` SHALL return `None` (route returns HTTP 410 cache_expired)
- **THEN** the system SHALL log the fallback reason at DEBUG level
- **THEN** the pandas fallback path SHALL NOT be invoked

#### Scenario: Type A client re-triggers sync query on 410
- **WHEN** the yield-alert view endpoint returns HTTP 410
- **THEN** the client SHALL call `execute_primary_query()` synchronously (no 202 / polling flow)
- **THEN** upon receiving a 200 response, the client SHALL load the view with the returned data
- **THEN** the view endpoint SHALL NOT dispatch any background job as a side-effect of the 410
