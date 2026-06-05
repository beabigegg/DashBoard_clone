---
change-id: gunicorn-preload-workers
schema-version: 0.1.0
last-changed: 2026-06-05
risk: high
tier: 3
---

# Test Plan: gunicorn-preload-workers

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name(s) | tier | markers |
|---|---|---|---|---|---|
| AC-1 | integration | tests/integration/test_preload_fork_safety.py | `test_downtime_prewarm_runs_once_across_two_workers`, `test_material_consumption_warmup_runs_once_across_two_workers`, `test_resource_history_duckdb_prewarm_runs_once`, `test_resource_cache_init_runs_once` | Tier 3 | `integration_real, multi_worker` |
| AC-2 | integration | tests/integration/test_preload_fork_safety.py | `test_each_worker_has_distinct_oracle_engine_pool`, `test_concurrent_oracle_requests_no_cross_talk` | Tier 3 | `integration_real, multi_worker` |
| AC-3 | unit + integration | tests/test_post_fork_reinit.py, tests/integration/test_preload_fork_safety.py | `test_close_redis_disposes_connection_pool`, `test_each_worker_has_distinct_redis_pool` | Tier 1 + Tier 3 | `multi_worker` |
| AC-4 | unit + integration | tests/test_post_fork_reinit.py, tests/integration/test_preload_fork_safety.py | `test_sqlite_handles_reopen_per_worker`, `test_sqlite_no_wal_corruption_on_restart` | Tier 1 + Tier 3 | `multi_worker` |
| AC-5 | unit + integration | tests/test_app_factory.py (extend), tests/integration/test_preload_fork_safety.py | `test_all_background_threads_alive_post_fork`, `test_post_fork_hook_registered_in_app_factory` | Tier 1 + Tier 3 | `multi_worker` |
| AC-6 | integration | tests/integration/test_preload_fork_safety.py | `test_duckdb_prewarm_no_timeout_two_workers`, `test_duckdb_prewarm_completes_once` | Tier 3 | `integration_real, multi_worker` |
| AC-7 | unit | tests/test_resource_cache_version_check.py | `test_identical_version_skips_oracle_fetch`, `test_changed_version_triggers_oracle_fetch` | Tier 1 | none |
| AC-8 | integration | tests/integration/test_preload_fork_safety.py | `test_no_duplicate_parquet_files_on_two_worker_start` | Tier 3 | `integration_real, multi_worker` |
| AC-9 | integration | tests/integration/test_preload_fork_safety.py | `test_worker_crash_respawn_no_master_prewarm_retrigger`, `test_worker_crash_respawn_fresh_connections` | Tier 3 | `integration_real, multi_worker` |
| AC-10 | contract | tests/test_app_factory.py (extend) | `test_api_contracts_unchanged_after_preload` | Tier 1 | none |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 1 | `dispose_engine()`, `close_redis()`, SQLite handle reopen, version-check logic — mock-only, no marker, runs in default `pytest` |
| integration | Tier 3 | Multi-worker process harness; requires real Oracle + Redis; gate via `pytest -m multi_worker` in `backend-tests.yml` nightly job |
| resilience | Tier 3 | Worker crash + respawn cycle (AC-9); uses `_multi_worker_harness.py` `kill_worker()` helper |
| contract | Tier 1 | Pins that no API shape, business rule, or CSS contract changed; extends `tests/test_app_factory.py` |
| soak | Tier 4 | Extend `tests/integration/test_soak_workload.py`: sustained 4-worker load for 30 min; assert no ORA errors, no thread-count drift |

## Test Files

| path | purpose | tier | markers | new vs existing |
|---|---|---|---|---|
| `tests/test_post_fork_reinit.py` | Unit-tests each post_fork primitive: `dispose_engine()`, `close_redis()`, per-store SQLite handle close+reopen, thread restart stubs | Tier 1 | none | **new** |
| `tests/test_resource_cache_version_check.py` | Pins AC-7: identical-version → zero Oracle calls; changed-version → exactly one Oracle call | Tier 1 | none | **new** |
| `tests/integration/test_preload_fork_safety.py` | Primary evidence layer — AC-1 through AC-9 using `_multi_worker_harness.py`; per-test/class-level markers only (no module-level `pytestmark`) | Tier 3 | `integration_real, multi_worker` per-test | **new** |
| `tests/test_app_factory.py` | Extend: add `test_post_fork_hook_registered_in_app_factory`, `test_api_contracts_unchanged_after_preload` | Tier 1 | none | **extend** |
| `tests/test_cache_updater.py` | Extend: verify `force=True` path no longer bypasses Redis version check (regression for AC-7 init_cache change) | Tier 1 | none | **extend** |
| `tests/integration/test_soak_workload.py` | Extend: 4-worker 30-min soak; assert stable thread count and zero ORA errors per worker | Tier 4 | `soak` | **extend** |

## Critical Test Names (contract for backend-engineer)

**AC-1** `test_downtime_prewarm_runs_once_across_two_workers` — spawn 2 workers via harness, count Oracle queries for downtime_analysis, assert count == 1  
**AC-1** `test_material_consumption_warmup_runs_once_across_two_workers`  
**AC-1** `test_resource_history_duckdb_prewarm_runs_once` — no timeout log lines, single parquet file  
**AC-1** `test_resource_cache_init_runs_once` — Oracle fetch count == 1 across 2 workers  
**AC-2** `test_each_worker_has_distinct_oracle_engine_pool` — compare engine pool identity across worker PIDs  
**AC-2** `test_concurrent_oracle_requests_no_cross_talk` — 2 workers issue concurrent queries, assert no ORA-3135 or response data cross-contamination  
**AC-3** `test_close_redis_disposes_connection_pool` (unit) — mock Redis client; assert `connection_pool.disconnect()` called  
**AC-3** `test_each_worker_has_distinct_redis_pool` (integration)  
**AC-4** `test_sqlite_handles_reopen_per_worker` (unit) — inherited handle vs child handle are distinct objects  
**AC-4** `test_sqlite_no_wal_corruption_on_restart` (integration) — write in worker A, restart, read in new worker B  
**AC-5** `test_all_background_threads_alive_post_fork` — after post_fork hook runs, assert each expected thread name present in `threading.enumerate()`  
**AC-5** `test_post_fork_hook_registered_in_app_factory` — assert gunicorn server hooks dict contains `post_fork` key  
**AC-6** `test_duckdb_prewarm_no_timeout_two_workers` — no "timed out waiting for peer" in captured logs  
**AC-6** `test_duckdb_prewarm_completes_once` — parquet file present, correct row count, written by master before fork  
**AC-7** `test_identical_version_skips_oracle_fetch` (unit, monkeypatch.setattr on module constant)  
**AC-7** `test_changed_version_triggers_oracle_fetch` (unit)  
**AC-8** `test_no_duplicate_parquet_files_on_two_worker_start` — assert `len(glob(spool_dir/*)) == expected` after 2-worker start  
**AC-9** `test_worker_crash_respawn_no_master_prewarm_retrigger` — kill worker, respawn, assert Oracle prewarm call count stays == 1  
**AC-9** `test_worker_crash_respawn_fresh_connections` — respawned worker's pool id differs from killed worker's pool id

## Out of Scope

- Frontend/UI regression tests (no user-facing behavior change per AC-10)
- New env-var contract tests (design.md confirms no new env vars)
- Oracle XE fault injection (covered by existing `test_real_oracle_fault_injection.py`)
- Redis chaos scenarios already in `test_redis_chaos.py` — extend only if post_fork creates new Redis failure modes
- CSS/contract-file validation (cdd-kit validate covers this separately)
- Stress-tier load tests (`tests/stress/`) — no new endpoints or throughput targets introduced

## Notes

- `tests/integration/test_preload_fork_safety.py` must use **per-test** `@pytest.mark.integration_real` and `@pytest.mark.multi_worker` decorators, not a module-level `pytestmark`. This allows `pytest -m "not integration_real"` to collect and skip gracefully, and keeps Tier 1 imports in the same file safe.
- All module-level constants in target services (e.g., `_USE_ROW_COUNT_CHUNKING`) must be patched via `monkeypatch.setattr()` on the attribute, not `monkeypatch.setenv()`.
- AC-7 unit tests belong in `tests/test_resource_cache_version_check.py`, not `tests/integration/test_oracle_error_path.py` (which carries `pytestmark = pytest.mark.integration_real` — mock tests there are silently skipped).
- The soak extension (Tier 4) runs in `backend-tests.yml` nightly lane only; it is not a PR gate.
