## ADDED Requirements

### Requirement: Yield Alert SHALL spool primary query results to parquet disk cache
The system SHALL persist `execute_primary_query` results as parquet files via `query_spool_store` to enable out-of-core DuckDB queries.

#### Scenario: Successful spool write after primary query
- **WHEN** `execute_primary_query` completes and returns a non-empty detail DataFrame
- **THEN** the system SHALL call `store_spooled_df` with namespace `yield_alert_dataset` and the computed `query_id`
- **THEN** the parquet file SHALL be retrievable via `get_spool_file_path` using the same namespace and query_id

#### Scenario: Spool write failure does not block query
- **WHEN** `store_spooled_df` fails (disk full, permission error)
- **THEN** the system SHALL log a warning and continue with existing Redis/process cache storage
- **THEN** the primary query response SHALL still return a valid `query_id`

### Requirement: Yield Alert view SHALL use DuckDB SQL runtime as primary computation path
The system SHALL provide a DuckDB-based SQL runtime (`yield_alert_sql_runtime.py`) that queries spool parquet files to compute all view aggregations without loading full DataFrames into pandas.

#### Scenario: DuckDB-first view computation
- **WHEN** `apply_view` is called and a parquet spool file exists for the query_id
- **THEN** the system SHALL execute summary, trend, heatmap, station_summary, package_summary, and alerts computations via DuckDB SQL
- **THEN** the result structure SHALL be identical to the pandas computation path

#### Scenario: DuckDB path computes alerts with SQL-level pagination
- **WHEN** DuckDB SQL runtime computes alerts
- **THEN** filtering, grouping, sorting, and pagination SHALL be performed within DuckDB SQL (not Python-side materialization)
- **THEN** only the requested page of alert rows SHALL be returned to Python

#### Scenario: DuckDB fallback to pandas on spool miss
- **WHEN** `apply_view` is called but no parquet spool file exists for the query_id
- **THEN** the system SHALL fall back to the pandas computation path with memory guard protection
- **THEN** the system SHALL log the fallback reason

#### Scenario: DuckDB disabled via feature flag
- **WHEN** environment variable `YIELD_ALERT_SQL_VIEW_ENABLED` is set to `false`
- **THEN** the system SHALL skip the DuckDB path entirely and use the pandas computation path
- **THEN** the pandas path SHALL still be protected by `enforce_dataset_memory_guard`

### Requirement: Yield Alert DuckDB runtime SHALL apply reason exclusion policy equivalently
The DuckDB SQL runtime SHALL apply the same reason exclusion logic as the pandas `_apply_reason_policy` function.

#### Scenario: Excluded reasons filtered in SQL
- **WHEN** DuckDB runtime computes summary, trend, or alerts
- **THEN** rows matching excluded reason tokens (from `_load_excluded_reason_tokens`) SHALL be excluded from scrap aggregation
- **THEN** reversal rows (negative SCRAP_QTY) SHALL be included regardless of reason code

#### Scenario: Unmapped reasons excluded
- **WHEN** a row has REASON_CODE equal to `UNMAPPED_REASON`
- **THEN** the DuckDB SQL SHALL exclude it from scrap aggregation (consistent with pandas `_apply_reason_policy`)

## Delta: 2026-03-24-yield-alert-streaming-spool

### Spool failure contract

- When streaming parquet write or `register_spool_file` fails: the primary query SHALL return `503 SERVICE_UNAVAILABLE` + `Retry-After` + `error_code: SERVICE_UNAVAILABLE`. No query marker is published.
- Callers MUST treat 503 as retryable.

### Empty-result cache semantics

- Zero-row queries now produce a lightweight marker (`empty_result=true, spool_ready=false`) rather than triggering a cache miss.
- DuckDB and pandas fallback paths both return empty success results (not cache miss) for empty-result markers.

### Data source tiering

- Large detail data (662K rows, 5.7MB parquet): spool parquet on disk only. No longer stored in Redis.
- Small linkage data (~20KB): Redis + L1 process cache (unchanged).
- Pandas fallback data source: `pd.read_parquet(spool_path)` (previously: `redis_load_df`).

### Single-flight behavior

- Concurrent requests for the same `query_id` are handled by a distributed lock:
  - Lock owner: runs the query and writes spool.
  - Waiters: poll for up to 30s. If cache becomes available, return it. If timeout, return `503 SERVICE_UNAVAILABLE` with `error_code: SERVICE_UNAVAILABLE`.

### Removed assumptions

- Redis detail fallback (`redis_load_df(detail_cache_key)`) no longer exists. All specs that referenced this fallback are superseded by the spool-only source.
- `_redis_key_exists` check removed from cache validity logic.
