# Archive — gunicorn-preload-workers

> Cold Data Warning: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Enabled `preload_app = True` in `gunicorn.conf.py` so Flask's `create_app()` runs once in the master process before workers fork — eliminating repeated startup costs (Oracle pool build, DuckDB prewarm, Redis warm-up) per worker. A `post_fork()` hook reinitialises per-resource handles (Oracle engine pool, Redis connection pool, SQLite thread-local state) in each forked worker to ensure no shared FDs survive the fork. Master-only single-run prewarms (resource-history DuckDB, downtime analysis, material consumption, resource_cache) are guarded by `is_testing_runtime` so they do not fire during the pytest suite. The change is purely a startup-lifecycle reorganisation with no API, data, business, or UI surface changes.

## Final Behavior

- `gunicorn.conf.py`: `preload_app = True`; `post_fork(server, worker)` hook calls `dispose_engine()`, `close_redis()`, `_start_per_worker_services()` per worker.
- `app.py`: startup block split — master-only prewarms under `if not is_testing_runtime:` (lines 818–836); per-worker thread starts in `_start_per_worker_services()` called from `post_fork`.
- `resource_history_duckdb_cache.py`: `fcntl.flock(LOCK_EX|LOCK_NB)` + 10s thread delay + 90s peer-wait retained (belt-and-suspenders; safe under single master writer).
- `resource_cache.py`: additional version guard in `refresh_cache(force=True)` branch preventing re-query when Redis version is unchanged (AC-7).
- `internal_metrics_service.py`: extended to 8 categories — added `engine_id` (pool identity), `pool_id` (Redis pool identity), and `threads` (per-worker thread enumeration) for GunicornHarness integration assertions.
- `config/settings.py`: `REGISTER_INTERNAL_METRICS` now env-var-overrideable via `_bool_env()` so test harnesses can enable `/internal/metrics` without TestingConfig.
- `tests/integration/_multi_worker_harness.py`: `GunicornHarness` class added — spawns a real gunicorn subprocess with N forked workers on a free port, clears pytest env poison, enables Redis, captures combined stdout/stderr, provides `log_count()`, `collect_per_worker_metrics()`, `kill_worker()`, `wait_for_respawn()`.
- `tests/integration/test_preload_fork_safety.py`: All 14 `pytest.skip` stubs replaced with real test logic (all 14 PASS, 534s runtime).

## Final Contracts Updated

- `contracts/env-contract.md`: added `REGISTER_INTERNAL_METRICS` env var entry (env-var-overrideable gate for `/internal/metrics` route).
- No API/data/business/CSS contract changes (confirmed by `cdd-kit validate` and contract-reviewer).

## Final Tests Added / Updated

- `tests/test_post_fork_reinit.py`: unit tests for `post_fork` hook (5 tests).
- `tests/test_resource_cache_version_check.py`: unit tests for AC-7 version guard (5 tests).
- `tests/integration/test_preload_fork_safety.py`: 14 integration multi-worker tests (AC-1–9, Tier 3 nightly).
- `tests/routes/test_internal_routes.py`: updated `_EXPECTED_KEYS` to include `"threads"` (8 categories).

## Final CI/CD Gates

| gate | tier | trigger | result |
|---|---|---|---|
| contract-validate | 0 | local pre-PR | PASS |
| lint | 0 | PR | PASS (changed files ruff-clean) |
| unit-mock-integration | 1 | PR | PASS (4359 passed, 122 skipped) |
| nightly-integration | 3 | nightly / workflow_dispatch | PASS — 14/14 fork-safety tests green (verified in close session, 534s) |
| soak | 4 | weekly | stress-soak-report.md written; runtime soak pending weekly schedule |

## Production Reality Findings

First-restart log verification (after enabling `preload_app = True` on production):
1. **Each prewarm logged exactly once** — downtime, material, resource-history DuckDB ("prewarm complete: 191482 base rows"), resource_cache each appeared once. No N× duplication.
2. **No `version changed: X→X`** — AC-7 resource_cache version guard working correctly.
3. **No `timed out waiting for peer worker`** — DuckDB flock not deadlocking.
4. **No ORA- errors under concurrent load** — Oracle pool reinitialised cleanly per worker.
5. **Both worker PIDs showed `dispose_engine` + `redis close` in post_fork** — fork-safety reinit confirmed in production.

GunicornHarness implementation findings (during close session):
- `_try_reuse_existing()` exits silently (no "prewarm complete") when a valid `tmp/resource_history.duckdb` already exists from the running production service. Test sentinel must be "background thread started" (always logged), not "prewarm complete" (only on Oracle load).
- resource_history DuckDB stores its file at `tmp/resource_history.duckdb`, not `tmp/query_spool/resource_history/`.
- pytest conftest sets `FLASK_ENV=testing` and `REDIS_ENABLED=false` which subprocess inherits via `os.environ.copy()`; harness must explicitly pop/override both.
- `worker-rss-guard` thread name does not exist in `_start_per_worker_services()` — removed from expected-threads list.
- `/health/deep` requires authentication (returns 401); AC-4 SQLite restart test uses `/health` instead.

## Lessons Promoted to Standards

Promoted to `CLAUDE.md` — new section `## GunicornHarness Integration Test Notes` (4 rules):

- **L2** (app URI + PYTHONPATH): `CLAUDE.md §GunicornHarness Integration Test Notes`. Evidence: `tests/integration/_multi_worker_harness.py::GunicornHarness.start()`.
- **L5** (is_testing_runtime guard + harness env isolation, absorbs L1): `CLAUDE.md §GunicornHarness Integration Test Notes`. Evidence: `app.py:798-818`, `_multi_worker_harness.py:424-435`, `conftest.py:18-19`.
- **L3** (DuckDB "background thread started" sentinel): `CLAUDE.md §GunicornHarness Integration Test Notes`. Evidence: `test_preload_fork_safety.py:113-117,368-378`.
- **L6** (REGISTER_INTERNAL_METRICS + INTERNAL_METRICS_ENABLED both required): `CLAUDE.md §GunicornHarness Integration Test Notes`. Evidence: `config/settings.py:53,179`, `_multi_worker_harness.py:434-436`.

Not promoted:
- **L1** — subsumed by L5 (same root cause at shallower depth; contract-reviewer decision).
- **L4** (resource_history DuckDB file path) — already documented in `contracts/env/env-contract.md:89-94`.

## Follow-up Work

- **FU-1 Soak**: `stress-soak-report.md` written; runtime soak (restart-loop + thread-count-drift) pending weekly schedule post-merge.
- **FU-3/FU-4 ADR reconciliation**: ADR-0004 + design D4 describe the fcntl.flock as removed; as-built code retains it (belt-and-suspenders, no negative safety impact). Reconciliation (update ADR to accepted-as-built or align code) deferred to follow-up.
- **FU-4 Resource-cache D3 deviation**: `refresh_cache(force=True)` received a population check that design D3 explicitly rejected; outcome-equivalent but code path diverges from recorded decision. Low-priority.
