## MODIFIED Requirements

### Requirement: Yield Alert SHALL spool primary query results to parquet disk cache
The system SHALL persist `execute_primary_query` results as parquet files via `query_spool_store` to enable out-of-core DuckDB queries.

`execute_primary_query()` SHALL only be responsible for Oracle → spool 落盤 and returning `query_id` + metadata. All view computation (summary, trend, heatmap, alerts, etc.) SHALL be deferred to `apply_view()` via DuckDB SQL runtime.

#### Scenario: Successful spool write after primary query
- **WHEN** `execute_primary_query` completes and returns a non-empty detail DataFrame
- **THEN** the system SHALL call `store_spooled_df` with namespace `yield_alert_dataset` and the computed `query_id`
- **THEN** the parquet file SHALL be retrievable via `get_spool_file_path` using the same namespace and query_id

#### Scenario: Primary query returns query_id only — no pandas view computation
- **WHEN** `execute_primary_query()` completes spool write successfully
- **THEN** the response SHALL include `query_id` and metadata (cache_hit, max_query_days, linkage_ready)
- **THEN** `execute_primary_query()` SHALL NOT call `_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()`, or `_compute_filter_options()`
- **THEN** the route SHALL call `apply_view()` to compute the full view result via DuckDB SQL runtime

#### Scenario: Spool write failure does not block query
- **WHEN** `store_spooled_df` fails (disk full, permission error)
- **THEN** the system SHALL log a warning and continue with existing Redis/process cache storage
- **THEN** the primary query response SHALL still return a valid `query_id`

## REMOVED Requirements

### Requirement: Yield Alert pandas view computation helpers in execute_primary_query path
**Reason**: `_build_summary_and_trend()`, `_build_heatmap_data()`, `_build_station_summary()`, `_build_package_summary()`, `_build_alerts_view()`, `_compute_filter_options()` were used by `execute_primary_query()` to compute view data inline. These are replaced by DuckDB SQL runtime via `apply_view()`. Pandas helper functions `_dedup_tx_df()`, `_bucket_date_str()`, `_vectorized_bucket()`, `_apply_dimension_filters()`, `_apply_reason_policy()`, `_to_numeric()` SHALL be removed only if no other callers remain (verify with grep before deletion).
**Migration**: Route calls `apply_view(query_id, ...)` after `execute_primary_query()` returns. DuckDB SQL runtime computes summary, trend, heatmap, station_summary, package_summary, alerts, and filter_options from spool parquet.
