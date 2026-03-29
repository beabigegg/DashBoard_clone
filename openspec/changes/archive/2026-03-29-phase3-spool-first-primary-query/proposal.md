## Why

Phase 2 removed large Redis payloads, but the view request path in resource/hold/yield-alert/reject domains still contains a pandas `_get_cached_df() → _derive_*()` fallback that loads the entire spool file into memory as a DataFrame whenever DuckDB fails. These fallbacks keep high per-request RAM consumption possible and maintain dual-path complexity. DuckDB SQL runtimes already exist for all four domains; Phase 3 retires the pandas fallback to make DuckDB the sole view engine.

## What Changes

- `resource_dataset_cache.py`: Remove `_get_cached_df() → _derive_summary() / _derive_detail()` from `apply_view()`; DuckDB runtime (`resource_history_sql_runtime.py`) becomes the only compute path
- `hold_dataset_cache.py`: Remove `_get_cached_df() → _derive_all_views()` from `apply_view()`; DuckDB runtime (`hold_history_sql_runtime.py`) becomes the only compute path
- `yield_alert_dataset_cache.py`: Remove pandas fallback block (L1497–1623) from `apply_view()`; `yield_alert_sql_runtime.py` becomes the only compute path
- `reject_dataset_cache.py`: Remove `_get_cached_df() → pandas derive` from view path; `reject_cache_sql_runtime.py` becomes the only compute path
- `production-history`: No change — already spool + DuckDB only, no pandas derive in view path
- **BREAKING**: `apply_view()` returns `cache_expired` (410) when DuckDB runtime returns no result, instead of falling back to pandas

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `parquet-spool-view-engine`: Remove "DuckDB SQL runtime unavailable → pandas fallback" scenario; DuckDB runtime SHALL be the sole view compute path; spool miss or runtime failure SHALL return `cache_expired`
- `resource-dataset-cache`: `apply_view()` SHALL NOT call `_get_cached_df()` or any pandas `_derive_*()` function; DuckDB runtime is sole engine
- `hold-dataset-cache`: `apply_view()` SHALL NOT call `_get_cached_df()` or `_derive_all_views()`; DuckDB runtime is sole engine
- `yield-alert-spool-query`: Remove "DuckDB fallback to pandas on spool miss" scenario; pandas fallback path SHALL be retired
- `reject-history-api`: Remove pandas derive fallback from view path; `reject_cache_sql_runtime.py` is sole engine

## Impact

- **Services**: `resource_dataset_cache.py`, `hold_dataset_cache.py`, `yield_alert_dataset_cache.py`, `reject_dataset_cache.py`
- **Dead code removal**: `_derive_summary()`, `_derive_detail()`, `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()` in resource; `_derive_all_views()` and sub-functions in hold; pandas fallback block in yield-alert; pandas derive block in reject view path
- **RAM impact**: Eliminates up to 20–100 MB per-worker DataFrame materialization on DuckDB miss; all view derivation becomes out-of-core SQL
- **Error semantics**: DuckDB failure or spool miss → `{ success: false, error: "cache_expired" }` (410); no silent pandas fallback
- **Tests**: Tests mocking the pandas derive path become obsolete; DuckDB runtime mock tests take over
