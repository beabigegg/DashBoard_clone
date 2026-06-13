# Archive: unify-duckdb-prewarm-rq

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).

## Change Summary

Moved two DuckDB prewarm operations (resource_history and downtime_analysis) from master-process daemon threads in `app.py` to RQ jobs in `spool_warmup_scheduler._WARMUP_JOBS`. Each prewarm service gained a `run_prewarm_job()` entry point called by the RQ worker. In the same change, the per-service spool TTL was corrected from the global `CACHE_TTL_DATASET` (7200s/2h) to a dedicated env-var default of 72000s (20h), ensuring prewarm files survive across shifts without constant Oracle re-queries.

## Final Behavior

- At gunicorn startup, `spool_warmup_scheduler` enqueues `_warmup_resource_history_duckdb_job` and `_warmup_downtime_analysis_duckdb_job` into the RQ default queue. No daemon threads are spawned from `app.py` for these two prewarms.
- `resource_history_duckdb_cache.run_prewarm_job()` and `downtime_analysis_duckdb_cache.run_prewarm_job()` are the canonical RQ entry points; `start_duckdb_prewarm()` is retained as a thin no-thread backward-compat shim.
- Spool TTL for both services defaults to 72000s (20h), overrideable via `RESOURCE_HISTORY_SPOOL_TTL` and `DOWNTIME_SPOOL_TTL` env vars. `CACHE_TTL_DATASET` (7200s) is no longer involved.

## Final Contracts Updated

| Contract | Version | Nature |
|---|---|---|
| `business-rules.md` | RH-07/RH-08 added | resource_history DuckDB prewarm via RQ |
| `business-rules.md` | DA-07/DA-08 added | downtime_analysis DuckDB prewarm via RQ |
| `env-contract.md` | new rows | `RESOURCE_HISTORY_SPOOL_TTL`, `DOWNTIME_SPOOL_TTL` (default 72000) |
| `contracts/CHANGELOG.md` | entries added | business + env version bumps |
| `ci-gate-contract.md` | assertion updated | daemon-thread removal CI note |

## Final Tests Added / Updated

| File | Tests | Covers |
|---|---|---|
| `tests/test_app_startup.py::TestDaemonPrewarmRemovedFromApp` | 4 AST-based absence tests | AC-1: daemon threads removed |
| `tests/test_spool_warmup_scheduler.py` | 3 new tests | AC-3: both services in `_WARMUP_JOBS` |
| `tests/test_resource_history_duckdb_cache.py::TestResourceSpoolTtlDefault, TestRunPrewarmJobGate` | added | AC-2, AC-4 |
| `tests/test_downtime_analysis_duckdb_cache.py::TestDowntimeSpoolTtlDefault, TestDowntimeRunPrewarmJobGate` | added | AC-2, AC-4 |
| `tests/test_env_contract.py::TestDuckdbPrewarmTtlDefaults` | 5 tests | AC-4 env pin |
| `tests/test_rq_warmup_resilience.py` | 11 tests (3 classes) | AC-7: RQ worker error isolation |
| `tests/integration/test_preload_fork_safety.py` | updated 6 + added 3 | AC-1/AC-6: GunicornHarness RQ enqueue assertions |

## Final CI/CD Gates

Tier 1 required: `lint`, `type-check`, `unit-mock-integration`, `contract-validate`, `resilience`, `css-governance`.
Tier 3 required (nightly): `nightly-integration` (GunicornHarness RQ enqueue + daemon-thread-absent sentinels).

## Production Reality Findings

- 2 pre-existing Oracle thick-mode failures in `TestDowntimeMigration::test_uses_batch_query_engine_not_direct_oracle` exist on the base branch before this change — no regression introduced.
- `CACHE_TTL_DATASET` (7200s) constant in `config/constants.py` was intentionally left unchanged; only the per-service imports and defaults were updated. The global constant remains correct for other dataset caches.
- `start_duckdb_prewarm()` retained as a thin shim (no thread, calls `run_prewarm_job()` directly) to preserve compatibility with `TestStartDowntimePrewarmDelegates` without requiring that test to be rewritten.

## Lessons Promoted to Standards

**A — DuckDB prewarm spool TTL must use per-service env var, not `CACHE_TTL_DATASET`** → `CLAUDE.md §Cache Architecture Notes`
Promoted after "Multi-parquet spool atomicity" bullet. Evidence: `resource_dataset_cache.py:35`, `downtime_analysis_cache.py:37`; `contracts/env/env-contract.md §Cache Tuning — Resource History`; `contracts/business/business-rules.md §RH-07, DA-07`.

**B — AST-based absence tests for removed startup side-effects** → `CLAUDE.md §Test Coverage Discipline`
Promoted after the `pytestmark` bullet. Evidence: `tests/test_app_startup.py::TestDaemonPrewarmRemovedFromApp` (4 AST absence tests).

**C — Backward-compat shim pattern** → *not promoted* (one-off transitional detail; existing test-update discipline in CLAUDE.md is the correct rule; no other service in codebase would benefit today).

## Follow-up Work

- Nightly Tier 3 GunicornHarness run to confirm RQ enqueue + no-daemon sentinels on first post-merge nightly.
- 24h soak observation for TTL 72000s boundary behavior (daily-refresh boundary not tested pre-merge by design — Tier 3 nightly observation).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
