---
change-id: fix-admin-dashboard
schema-version: 0.1.0
last-changed: 2026-05-19
risk: medium
tier: 1
---

# Test Plan: fix-admin-dashboard

## Acceptance Criteria → Test Mapping

| criterion id | description (short) | test family | test file path | test name | tier |
|---|---|---|---|---|---|
| AC-1 | `query_logs_all` removes `WHERE synced=0` filter | unit | tests/test_log_store.py | `test_query_logs_all_returns_synced_and_unsynced` | 0 |
| AC-1 | `count_logs` removes `WHERE synced=0` filter | unit | tests/test_log_store.py | `test_count_logs_includes_synced_rows` | 0 |
| AC-1 | `/admin/api/logs` (SQLite-only) returns synced rows | integration | tests/test_admin_routes_logs.py | `test_api_logs_sqlite_only_includes_synced` | 1 |
| AC-2 | `cleanup_synced` default 24h retains recent synced sessions | unit | tests/test_login_session_store.py | `test_cleanup_synced_retains_within_24h` | 0 |
| AC-2 | `cleanup_synced` deletes synced rows older than 24h | unit | tests/test_login_session_store.py | `test_cleanup_synced_deletes_beyond_24h` | 0 |
| AC-2 | `log_store.cleanup_synced` default raised to 24h | unit | tests/test_log_store.py | `test_log_store_cleanup_synced_default_is_24h` | 0 |
| AC-3 | TRUNCATE guard skips when target table has rows | unit | tests/test_sync_worker.py | `test_truncate_guard_skips_when_rows_exist` | 0 |
| AC-3 | TRUNCATE guard fires only when target table is empty | unit | tests/test_sync_worker.py | `test_truncate_guard_executes_when_table_empty` | 0 |
| AC-3 | Migration version check prevents re-execution | unit | tests/test_sync_worker.py | `test_migration_skipped_when_version_current` | 0 |
| AC-4 | Merge pagination: correct slice when offset=0 | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_offset_zero` | 1 |
| AC-4 | Merge pagination: correct slice at merge boundary | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_across_source_boundary` | 1 |
| AC-4 | Merge pagination: offset > total returns empty logs | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_offset_exceeds_total` | 1 |
| AC-4 | Merge pagination: total reflects combined count | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_total_is_combined` | 1 |
| AC-4 | Merge pagination: MySQL empty, SQLite rows | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_mysql_empty` | 1 |
| AC-4 | Merge pagination: SQLite empty, MySQL rows | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_sqlite_empty` | 1 |
| AC-4 | Merge pagination: both sources empty | data-boundary | tests/test_admin_routes_logs.py | `test_merge_pagination_both_empty` | 1 |
| AC-5 | performance-detail redis includes `evicted_keys` | contract | tests/test_admin_routes_perf.py | `test_perf_detail_redis_evicted_keys_present` | 1 |
| AC-5 | performance-detail redis includes `expired_keys` | contract | tests/test_admin_routes_perf.py | `test_perf_detail_redis_expired_keys_present` | 1 |
| AC-5 | performance-detail redis includes `mem_fragmentation_ratio` | contract | tests/test_admin_routes_perf.py | `test_perf_detail_redis_fragmentation_present` | 1 |
| AC-5 | performance-detail redis includes `slowlog` (top-5) | contract | tests/test_admin_routes_perf.py | `test_perf_detail_redis_slowlog_top5` | 1 |
| AC-5 | performance-detail redis section null when Redis unavailable | resilience | tests/test_admin_routes_perf.py | `test_perf_detail_redis_null_when_unavailable` | 1 |
| AC-6 | performance-detail duckdb includes `temp_dir_bytes` | contract | tests/test_admin_routes_perf.py | `test_perf_detail_duckdb_temp_dir_bytes` | 1 |
| AC-6 | performance-detail duckdb includes `memory_limit_state` | contract | tests/test_admin_routes_perf.py | `test_perf_detail_duckdb_memory_limit_state` | 1 |
| AC-6 | performance-detail duckdb degrades to null when unavailable | resilience | tests/test_admin_routes_perf.py | `test_perf_detail_duckdb_null_when_unavailable` | 1 |
| AC-7 | `/admin/api/logs` 200 with no MySQL config | resilience | tests/test_admin_routes_logs.py | `test_api_logs_no_500_mysql_not_configured` | 1 |
| AC-7 | `/admin/api/performance-detail` 200 with no MySQL/Redis | resilience | tests/test_admin_routes_perf.py | `test_perf_detail_no_500_all_externals_off` | 1 |
| AC-7 | `/admin/api/user-usage-kpi` 200 with MySQL unavailable | resilience | tests/test_admin_routes.py | `test_user_usage_kpi_no_500_mysql_unavailable` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 — pre-merge, <30s | LogStore, LoginSessionStore, SyncWorker in isolation with in-memory SQLite |
| contract | Tier 1 — pre-merge | Response shape assertions for new performance-detail keys via Flask test client |
| integration | Tier 1 — pre-merge | Flask test client + real in-memory SQLite store; MySQL mocked at `get_mysql_connection` boundary |
| data-boundary | Tier 1 — pre-merge | Pagination edge cases for merge mode; see matrix below |
| resilience | Tier 1 — pre-merge | MySQL/Redis/DuckDB absent or raising; assert no 500s, well-formed envelope |

## Data-Boundary Pagination Matrix (AC-4)

| scenario | sqlite_count | mysql_count | offset | limit | expected_len | expected_total |
|---|---|---|---|---|---|---|
| normal page 1 | 5 | 5 | 0 | 5 | 5 | 10 |
| across merge boundary | 5 | 5 | 3 | 5 | 5 | 10 |
| offset equals total | 5 | 5 | 10 | 5 | 0 | 10 |
| offset exceeds total | 3 | 3 | 20 | 5 | 0 | 6 |
| mysql empty | 5 | 0 | 0 | 5 | 5 | 5 |
| sqlite empty | 0 | 5 | 0 | 5 | 5 | 5 |
| both empty | 0 | 0 | 0 | 5 | 0 | 0 |
| limit=1 page through all | 3 | 3 | 2 | 1 | 1 | 6 |

## New Test Files Needed

- `tests/test_log_store.py` — extend or create; covers AC-1, AC-2 (log_store.cleanup_synced)
- `tests/test_login_session_store.py` — extend or create; covers AC-2
- `tests/test_sync_worker.py` — extend or create; covers AC-3
- `tests/test_admin_routes_logs.py` — extend existing file; covers AC-1 (integration), AC-4, AC-7
- `tests/test_admin_routes_perf.py` — new file; covers AC-5, AC-6, AC-7 (perf-detail)
- `tests/test_admin_routes.py` — extend; covers AC-7 (`user-usage-kpi`)

## Out of Scope

- MySQL integration with a real server (Tier 3 nightly, not pre-merge)
- Redis SLOWLOG with a real Redis server (Tier 3 nightly)
- DuckDB temp-dir alerting thresholds or monitoring logic
- Frontend / admin-pages UI rendering for new fields
- E2E via Playwright
- Soak or stress testing

## Notes

- Unit tests use `:memory:` SQLite paths; no file I/O, no real MySQL/Redis connections.
- Mock at the `get_mysql_connection` and `get_redis_client` boundaries only; never mock internal SQLite methods.
- The TRUNCATE guard (AC-3) must be tested with a mock MySQL connection that returns row counts; real MySQL not required.
- Existing `tests/test_admin_routes_logs.py::TestApiLogsMergedSort` tests merged sort; extend, do not duplicate.
- SyncWorker cleanup default values must be asserted as constants (e.g., `cleanup_synced(older_than_hours=24)`) to catch accidental regression.
