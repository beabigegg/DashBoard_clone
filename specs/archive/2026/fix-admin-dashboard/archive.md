---
change-id: fix-admin-dashboard
closed: 2026-05-19
---

# Archive: fix-admin-dashboard

## Change Summary

Restored correctness and observability to the admin dashboard backend. The `query_logs_all` and `count_logs` functions in `log_store.py` had an identical `WHERE synced = 0` filter as the legacy `query_logs()` path, causing the admin log view to silently hide any record that had been synced to MySQL. The fix removes that filter from the "all" variants. Alongside this, synced-record retention was extended from 1 h to 24 h so usage-KPI history stays continuous across sync cycles. A TRUNCATE guard was added to `SyncWorker._run_login_session_migration()` to prevent live session data from being wiped on redeploy. The `/admin/api/logs` pagination was corrected so total is derived from independent `COUNT` queries rather than the length of a windowed fetch. The `/admin/api/performance-detail` endpoint was extended additively with Redis eviction/fragmentation/slowlog telemetry and DuckDB temp-dir/memory-limit telemetry, with graceful null fallbacks when any external is unavailable.

## Final Behavior

- `/admin/api/logs` returns all log rows (synced and unsynced); total accurately reflects combined SQLite + MySQL counts regardless of page size.
- Synced log records are retained for 24 h before cleanup; `SyncWorker._cleanup_synced()` passes the explicit `older_than_hours=24` argument.
- `SyncWorker._run_login_session_migration()` only executes `TRUNCATE TABLE dashboard_login_sessions` when the target table is empty; non-empty tables are skipped with an INFO log.
- `/admin/api/performance-detail` `redis` section now includes `evicted_keys`, `expired_keys`, `mem_fragmentation_ratio`, `slowlog` (top-5, normalized). `duckdb` top-level field added with `temp_dir_bytes` and `memory_limit_state`. All new fields are null when the respective service is unavailable; response always returns 200.

## Final Contracts Updated

- `contracts/api/api-contract.md` — bumped 1.7.0 → 1.8.0; additive keys on `/admin/api/performance-detail`
- `contracts/data/data-shape-contract.md` — bumped 1.6.0 → 1.7.0; new Section 3.8 documents full performance-detail payload shape
- `contracts/api/api-inventory.md` — bumped 1.1.6 → 1.1.7; compatibility note added
- `contracts/CHANGELOG.md` — three entries added (`[data 1.7.0]`, `[api 1.8.0]`, `[api-inventory 1.1.7]`)

## Final Tests Added / Updated

| file | tests added | ACs |
|---|---|---|
| `tests/test_log_store.py` | `TestLogStoreAllRows` (3 tests) | AC-1, AC-2 |
| `tests/test_login_session_store.py` | new file, 2 tests | AC-2 |
| `tests/test_sync_worker.py` | `TestLoginSessionMigrationGuard` (3 tests); `test_cleanup_synced_calls_log_store_with_24h` | AC-3, AC-2 |
| `tests/test_admin_routes_logs.py` | `TestApiLogsSqliteIncludesSynced`, `TestMergePagination` (7 tests), `TestApiLogsNoMysql` | AC-1, AC-4, AC-7 |
| `tests/test_admin_routes_perf.py` | new file: `TestPerfDetailRedisAdditiveKeys` (5), `TestPerfDetailDuckdb` (3), `TestPerfDetailNoExternals` (1) | AC-5, AC-6, AC-7 |
| `tests/test_admin_routes.py` | `test_user_usage_kpi_no_500_mysql_unavailable` | AC-7 |

Total: 72 passed in 2.77 s (all local gates green before CI).

Pre-existing test updated: `test_sync_worker.py::TestCleanupSynced::test_cleanup_removes_old_synced_logs` — backdate changed from 2 h to 25 h to match new 24 h retention threshold.

## Final CI/CD Gates

| gate | result |
|---|---|
| ruff-lint | pass |
| mypy-type-check | skipped (not installed in env; CI covers it) |
| cdd-validate | pass |
| pytest-unit | pass |
| pytest-integration | pass |
| coverage-report | informational |
| CI (backend-tests.yml) | PASS (user-confirmed) |

## Production Reality Findings

- **Test isolation pitfall** (from backend-engineer agent-log): `rq_monitor_service` imports `get_redis_client` at module level via `from x import y`. Any performance-detail test that runs after a test with `REDIS_ENABLED=True` must also stub `mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary`. Patching `mes_dashboard.core.redis_client.get_redis_client` at function level does not intercept rq calls. Pattern: patch at the `rq_monitor_service` boundary.
- **TRUNCATE guard race**: two gunicorn workers can both pass the `COUNT(*)` check before either inserts the migration-version row. Acceptable because the version-meta `REPLACE` serializes subsequent runs. Documented in a code comment.
- Pre-existing lint removed: unused `render_template` import in `admin_routes.py` was cleaned by ruff during this change.

## Lessons Promoted to Standards

| lesson | target | location | evidence |
|---|---|---|---|
| L-1: rq_monitor_service module-level import — patch at service boundary | CLAUDE.md | `## Admin Service Test Isolation Notes` (new section) | agent-log/backend-engineer.yml notes |
| L-2: query_logs_all/count_logs must not filter by synced | contracts/business/business-rules.md | `ADMIN-06` (1.8.0 → 1.9.0) | agent-log/backend-engineer.yml; tests/test_log_store.py::TestLogStoreAllRows |
| L-3: log pagination total from independent COUNT queries | contracts/business/business-rules.md | `ADMIN-07` (1.8.0 → 1.9.0) | agent-log/backend-engineer.yml; tests/test_admin_routes_logs.py::TestMergePagination |
| L-4: SyncWorker destructive migration guard pattern | CLAUDE.md | `## Cache Architecture Notes` (appended) | agent-log/backend-engineer.yml; tests/test_sync_worker.py::TestLoginSessionMigrationGuard |

## Follow-up Work

- Frontend: admin-pages SPA does not yet render the new Redis and DuckDB telemetry fields. A separate change (`admin-dashboard-perf-detail-ui`) should add display components for `redis.evicted_keys`, `expired_keys`, `mem_fragmentation_ratio`, `slowlog`, and `duckdb.temp_dir_bytes` / `memory_limit_state`.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
