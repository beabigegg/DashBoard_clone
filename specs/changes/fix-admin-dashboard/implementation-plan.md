---
change-id: fix-admin-dashboard
schema-version: 0.1.0
last-changed: 2026-05-19
---

# Implementation Plan: fix-admin-dashboard

## Objective
Restore correctness and observability to the admin dashboard backend by (a) removing the `synced=0` log filter that hid history-merged rows, (b) extending synced-record retention from 1h to 24h so user-usage-kpi history stays continuous, (c) guarding the startup `TRUNCATE dashboard_login_sessions` migration so it cannot wipe live data on redeploy, (d) fixing `/admin/api/logs` pagination so offset/limit slice happens after merge-sort with an authoritative combined total, and (e) extending `/admin/api/performance-detail` additively with Redis eviction/fragmentation/slowlog telemetry and DuckDB temp-dir/memory-limit telemetry. All changes must degrade gracefully when MySQL / Redis / DuckDB temp dir are unavailable.

## Execution Scope

### In Scope
- `src/mes_dashboard/core/log_store.py` — drop `WHERE synced = 0` from `query_logs_all` and `count_logs`; raise `cleanup_synced` default from 1h to 24h.
- `src/mes_dashboard/core/login_session_store.py` — verify `cleanup_synced` default = 24h (source confirms); add boundary unit tests; no code change unless tests reveal a regression.
- `src/mes_dashboard/core/sync_worker.py` — add row-count guard to `_run_login_session_migration()` so `TRUNCATE TABLE dashboard_login_sessions` only fires when the target table is empty; update `_cleanup_synced` to pass an explicit 24h argument to `_log_store.cleanup_synced`.
- `src/mes_dashboard/routes/admin_routes.py` — fix `/admin/api/logs` MySQL-merge pagination (authoritative combined total + post-merge slice); extend `/admin/api/performance-detail` `redis` section with `evicted_keys`, `expired_keys`, `mem_fragmentation_ratio`, `slowlog`; add `duckdb` field with `temp_dir_bytes` and `memory_limit_state`.
- `src/mes_dashboard/core/duckdb_runtime.py` — add `get_duckdb_telemetry()` helper returning temp-dir bytes and memory-limit state with graceful null fallbacks.
- `src/mes_dashboard/core/redis_client.py` — optional thin helper if it simplifies `admin_routes`; otherwise inline reads at the existing `get_redis_client()` boundary.
- New / extended tests as enumerated in `test-plan.md §Acceptance Criteria → Test Mapping`; TDD — write tests alongside each fix.
- Contract updates: `contracts/api/api-contract.md` and `contracts/data/data-shape-contract.md` — additive keys only.

### Out of Scope
- Any frontend / admin-pages SPA changes (no UI rendering for the new performance-detail keys in this change).
- Real-MySQL or real-Redis integration tests (deferred per `test-plan.md §Out of Scope`).
- DuckDB temp-dir alerting thresholds, dashboards, or operational runbooks.
- Renaming or removing any existing JSON keys on `/admin/api/logs`, `/admin/api/user-usage-kpi`, or `/admin/api/performance-detail` (additive only).
- Changes to `metrics_history` store, `metrics_history.cleanup_synced`, or the metrics sync path.
- New env vars in this change; if a future tunable is exposed, document in `contracts/env/env-contract.md`.
- Refactoring `SyncWorker` beyond the TRUNCATE guard (no module reorg).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `core/log_store.py::query_logs_all` | Remove `WHERE synced = 0` (and the leading `WHERE` becomes `WHERE 1=1` or be reshaped to keep filters intact). Keep all other filters, ORDER, LIMIT, OFFSET. | backend-engineer |
| IP-2 | `core/log_store.py::count_logs` | Remove `WHERE synced = 0`; keep all filters. | backend-engineer |
| IP-3 | `core/log_store.py::cleanup_synced` | Change default `older_than_hours=1` → `older_than_hours=24`. | backend-engineer |
| IP-4 | `core/sync_worker.py::_cleanup_synced` | Update the call to `_log_store.cleanup_synced(...)` to explicitly pass `older_than_hours=24` (do not rely on default). | backend-engineer |
| IP-5 | `core/login_session_store.py::cleanup_synced` | Verify default is 24h (current source confirms); add unit tests for boundary. No code change unless tests reveal a defect. | backend-engineer |
| IP-6 | `core/sync_worker.py::_run_login_session_migration` | Before `TRUNCATE TABLE dashboard_login_sessions`, run `SELECT COUNT(*) FROM dashboard_login_sessions LIMIT 1`; skip TRUNCATE when count > 0; still REPLACE the migration version meta row so the guard does not re-evaluate every restart; log at INFO when skipped because table was non-empty. | backend-engineer |
| IP-7 | `routes/admin_routes.py::api_logs` (MySQL branch) | Replace `total = len(all_rows)` (which truncates to per-source `limit`) with authoritative counts: compute `total = log_store.count_logs(...) + _count_mysql_logs(...)`. Fetch enough rows per source to cover `offset + limit` (pass `limit=offset + limit` to both source queries), then merge-sort by parsed timestamp DESC, then slice `[offset : offset + limit]`. Add a `_count_mysql_logs(level, q, since)` helper mirroring `_query_mysql_logs`, wrapped in try/except returning 0 on failure. | backend-engineer |
| IP-8 | `routes/admin_routes.py::api_logs` (SQLite-only branch) | Already returns correct `total` via `count_logs`; behavior remains correct after IP-2. No additional change. | backend-engineer |
| IP-9 | `routes/admin_routes.py::api_performance_detail` (redis) | Extend the existing `redis_detail` dict with `evicted_keys` (from `stats_info`), `expired_keys` (from `stats_info`), `mem_fragmentation_ratio` (from `info(section="memory")`), and `slowlog` (call `client.slowlog_get(5)` and normalize each entry to `{id, start_time, duration_us, command}`). Each addition wrapped so a failure leaves the key as `null`. Preserve existing keys. | backend-engineer |
| IP-10 | `routes/admin_routes.py::api_performance_detail` (duckdb section) | Add a new top-level `duckdb` field in the success payload by calling `get_duckdb_telemetry()`; on exception fill `{"error": str(exc)}` and return 200. | backend-engineer |
| IP-11 | `core/duckdb_runtime.py` | Add `get_duckdb_telemetry() -> dict` returning `{"temp_dir_bytes": <int|None>, "memory_limit_state": {"memory_limit": DUCKDB_MEMORY_LIMIT, "threads": DUCKDB_THREADS, "temp_dir": DUCKDB_TEMP_DIR or None, "connection_ok": <bool>}}`. Use non-recursive `os.scandir` on the temp dir when configured + exists; return `None` for `temp_dir_bytes` otherwise. The connection probe must open and close a heavy-query connection inside try/except, setting `connection_ok=False` on failure. Never raise. | backend-engineer |
| IP-12 | tests | Write/extend the test files listed in `test-plan.md` (per-AC); add fixtures for MySQL-mocked merge mode and Redis-mocked SLOWLOG; mock only at `get_mysql_connection` / `get_redis_client` boundaries. | backend-engineer |
| IP-13 | contracts | Add additive keys to `contracts/api/api-contract.md` and `contracts/data/data-shape-contract.md` for `/admin/api/performance-detail`. No removals/renames. | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | scope and AC-to-fix mapping |
| change-classification.md | Required Contracts (additive only) | constraint that all new keys must be additive |
| change-classification.md | Clarifications / Assumptions | SQLite log retention 1h→24h; TRUNCATE guard uses `SELECT COUNT(*) LIMIT 1` |
| test-plan.md | Acceptance Criteria → Test Mapping | exact test file names + test names per fix |
| test-plan.md | Data-Boundary Pagination Matrix (AC-4) | offset/limit edge cases the merge fix must satisfy |
| test-plan.md | Notes (mock boundaries) | mock at `get_mysql_connection` / `get_redis_client` only |
| test-plan.md | Out of Scope | excludes real MySQL/Redis, frontend, E2E, soak, stress |
| ci-gates.md | Required Gates for This Change | exact pytest invocations gating the PR |
| ci-gates.md | Promotion Policy / Rollback Policy | no parquet cleanup; revert-commit is sufficient |
| contracts/api/api-contract.md | existing `/admin/api/performance-detail` schema | location for additive keys |
| contracts/data/data-shape-contract.md | existing performance-detail data shape | location for additive shape |

## File-Level Plan
| path | action | notes |
|---|---|---|
| src/mes_dashboard/core/log_store.py | edit | IP-1, IP-2, IP-3 only. Do not touch `query_logs` (legacy unsynced-only path retained intentionally). Do not touch `cleanup_old_logs` (separate retention-days policy). |
| src/mes_dashboard/core/login_session_store.py | verify | IP-5: confirm `cleanup_synced(older_than_hours=24)` default; no code change unless tests reveal a defect. |
| src/mes_dashboard/core/sync_worker.py | edit | IP-4 (explicit 24h arg in `_cleanup_synced`), IP-6 (TRUNCATE guard). Do not refactor the migration-meta table SQL beyond adding the guard. |
| src/mes_dashboard/core/duckdb_runtime.py | edit | IP-11: add `get_duckdb_telemetry()` near the bottom of the module; reuse existing `DUCKDB_TEMP_DIR`, `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS` constants and `create_heavy_query_connection()` for the probe. |
| src/mes_dashboard/core/redis_client.py | edit (optional) | Only add a small helper if it simplifies `admin_routes`; inline reads via existing client are acceptable. |
| src/mes_dashboard/routes/admin_routes.py | edit | IP-7 (logs pagination + `_count_mysql_logs` helper), IP-9 (redis extra keys + slowlog), IP-10 (new `duckdb` field). |
| contracts/api/api-contract.md | edit | Document the four new redis keys and two new duckdb keys on `/admin/api/performance-detail`. |
| contracts/data/data-shape-contract.md | edit | Document additive data shape for the new keys. |
| tests/test_log_store.py | new/extend | AC-1 (synced+unsynced returned), AC-2 (cleanup_synced default 24h). |
| tests/test_login_session_store.py | new/extend | AC-2 (24h retention boundary). |
| tests/test_sync_worker.py | new/extend | AC-3 (TRUNCATE guard skip/fire/version-current). |
| tests/test_admin_routes_logs.py | extend | AC-1 integration, AC-4 data-boundary matrix, AC-7 no-500 with MySQL absent. |
| tests/test_admin_routes_perf.py | new | AC-5 (redis additive keys + SLOWLOG top-5 + null when unavailable), AC-6 (duckdb keys + null when unavailable), AC-7 (no-500 when all externals off). |
| tests/test_admin_routes.py | extend | AC-7 user-usage-kpi no-500 with MySQL unavailable. |

## Contract Updates
- API: `contracts/api/api-contract.md` — additive only on `/admin/api/performance-detail`: document `redis.evicted_keys` (int|null), `redis.expired_keys` (int|null), `redis.mem_fragmentation_ratio` (float|null), `redis.slowlog` (array of `{id, start_time, duration_us, command}` | null), `duckdb.temp_dir_bytes` (int|null), `duckdb.memory_limit_state` (object). No changes to `/admin/api/logs` or `/admin/api/user-usage-kpi` schemas.
- CSS/UI: none.
- Env: no new vars in this change; if a future tunable is exposed (e.g., `LOG_SQLITE_SYNCED_RETENTION_HOURS`), document in `contracts/env/env-contract.md`.
- Data shape: `contracts/data/data-shape-contract.md` mirrors the API additions above.
- Business logic: none.
- CI/CD: none — existing workflows cover all new test files under `tests/` per `ci-gates.md §CI/CD Workflow`.

## Test Execution Plan
Gates and exact pytest invocations are defined in `ci-gates.md §Required Gates for This Change`. Acceptance-criterion-to-test rows are fully enumerated in `test-plan.md §Acceptance Criteria → Test Mapping`. The table below summarizes by AC and points at the gate command.

| acceptance criterion | test files | gate command (from ci-gates.md) | expected signal |
|---|---|---|---|
| AC-1 | tests/test_log_store.py, tests/test_admin_routes_logs.py | pytest-unit, pytest-integration | green |
| AC-2 | tests/test_login_session_store.py, tests/test_log_store.py | pytest-unit | green |
| AC-3 | tests/test_sync_worker.py | pytest-unit | green |
| AC-4 | tests/test_admin_routes_logs.py (matrix in test-plan.md) | pytest-integration | green for all 8 matrix rows |
| AC-5 | tests/test_admin_routes_perf.py | pytest-integration | redis keys present when client mocked, null when client absent |
| AC-6 | tests/test_admin_routes_perf.py | pytest-integration | duckdb keys present when temp_dir configured, null otherwise |
| AC-7 | tests/test_admin_routes_logs.py, tests/test_admin_routes_perf.py, tests/test_admin_routes.py | pytest-integration | all endpoints return 200 envelope when MySQL/Redis/DuckDB unavailable |
| (lint/type) | n/a | ruff-lint, mypy-type-check, vue-tsc-type-check, cdd-validate | green |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- All new performance-detail keys must be **additive**; do not rename or remove any existing key on `/admin/api/performance-detail`, `/admin/api/logs`, or `/admin/api/user-usage-kpi`.
- All external-dependency failures (MySQL down, Redis SLOWLOG unavailable, DuckDB temp dir missing) must return null/empty fields with a 200 envelope — never 500.
- The TRUNCATE guard must remain a `SELECT COUNT(*) ... LIMIT 1` check (per classification §Clarifications); do not replace with row-by-row inspection.
- Do not mock SQLite internals in tests — only mock at `get_mysql_connection` and `get_redis_client` boundaries (per `test-plan.md §Notes`).
- Frontend rendering for the new performance-detail fields is intentionally out of scope; do not edit `frontend/`.
- Preserve `query_logs` (the unsynced-only legacy path) and `cleanup_old_logs` (retention-days policy) untouched in `log_store.py`.

## Known Risks
- **Merge-mode total accuracy** (IP-7): if `total` is computed as `len(all_rows)` after fetching only `limit` rows per source, total is silently under-reported whenever either source exceeds `limit`. Mitigation: implement `_count_mysql_logs()` and call `log_store.count_logs()` to derive authoritative `total` independent of the windowed fetch.
- **TRUNCATE guard race** (IP-6): two gunicorn workers may both pass the `COUNT(*)` check before either inserts. Acceptable because the migration runs only at SyncWorker startup and the version-meta REPLACE serializes subsequent runs; document the race in a code comment.
- **Redis SLOWLOG client compatibility** (IP-9): `redis-py` exposes `slowlog_get`; older clients may not. Wrap in try/except and fall back to `null`.
- **DuckDB temp dir scan cost** (IP-11): scanning a temp dir with many transient files could be slow. Mitigation: non-recursive `os.scandir` only, single level, short-circuit on `OSError` with `temp_dir_bytes=None`.
- **Retention extension blast radius** (IP-3, IP-4): raising synced-log retention from 1h to 24h grows SQLite size up to 24× in worst case. Operationally bounded by the existing `LOG_SQLITE_MAX_ROWS=100000` cap enforced by `cleanup_old_logs`.

