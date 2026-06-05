---
change-id: gunicorn-preload-workers
schema-version: 0.1.0
last-changed: 2026-06-05
---

# Implementation Plan: gunicorn-preload-workers

## Objective

Enable `preload_app = True` in `gunicorn.conf.py` and add a fork-safe
`post_fork(server, worker)` reinitialization path so that:

1. The four single-run prewarm tasks (downtime_analysis, material_consumption,
   resource_history DuckDB, resource_cache initial load) execute **once** in the
   gunicorn master pre-fork — not once per worker.
2. Every fork-unsafe per-worker resource (Oracle SQLAlchemy pools, Redis/RQ
   client pools, SQLite file handles) is dropped and re-created in each forked
   worker.
3. Every background thread is (re)started in each worker post-fork (threads do
   not survive `fork()`).
4. The two existing correctness defects that the current ad-hoc per-worker
   dedupe relies on are fixed: the `resource_cache` identical-version Oracle
   re-fetch (AC-7) and the `resource_history_duckdb_cache` `O_EXCL` lock
   deadlock (AC-6).

No user-facing API, data shape, business rule, or UI change (AC-10). Delivery is
defined as: all 21 tests in `test-plan.md` pass, the Tier 0/1 gates in
`ci-gates.md` pass locally, and `error.log` on a 2-worker boot shows each prewarm
logging exactly once with no `version changed: X -> X` and no
`timed out waiting for peer worker` lines.

## Execution Scope

### In Scope
- `gunicorn.conf.py`: `preload_app = True` + new `post_fork(server, worker)` hook.
- `src/mes_dashboard/app.py`: split the `create_app()` startup block (lines
  640-667) into a single-run (pre-fork, stays in `create_app`) segment and a
  per-worker segment extracted to a new `_start_per_worker_services(app)` helper
  invoked from `post_fork`.
- AC-7 fix: `resource_cache.py` + `cache_updater.py` (bug-fix-engineer).
- AC-6 fix: `resource_history_duckdb_cache.py` (bug-fix-engineer).
- New + extended tests per `test-plan.md` (5 files).
- `contracts/ci/ci-gate-contract.md` + `contracts/CHANGELOG.md` (CI gate addition
  per `ci-gates.md`; owned downstream by contract-reviewer, but backend-engineer
  adds the gate text if not already present at implementation time — confirm with
  contract-reviewer scope, do not edit other contracts).

### Out of Scope
- No API, data shape, business logic, or UI/CSS contract change (AC-10;
  `change-classification.md` §Tasks Not Applicable 2.1/2.2/2.4/2.5).
- No new env var (`design.md` D5). Do not add a `PRELOAD_APP` toggle.
- Do not document `GUNICORN_WORKERS` in `env-contract.md` (`design.md` D5 note —
  deferred to a separate housekeeping change).
- No change to `worker_exit` logic (already correct per-worker cleanup;
  `gunicorn.conf.py:55`).
- No change to `container_filter_cache` / `reason_filter_cache` (already use
  Redis L2 correctly; `change-request.md` Non-goals).
- No engine-creation or Redis-client-creation code change in `core/database.py`
  or `core/redis_client.py` — only call the existing `dispose_engine()` /
  `close_redis()` primitives (`design.md` Affected Components rows 3-4).
- No re-architecture of the prewarm services themselves; only move their
  invocation point and fix the two named defects.
- No swap of `O_EXCL` for `fcntl.flock` in the prewarm path (it becomes dead
  code once the master is the sole writer; `design.md` D4).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | resource_cache version-guard (AC-7) | Write failing test first, then fix `refresh_cache()` so `force=True` no longer issues an Oracle fetch when `redis_version == oracle_version`; drive initial load through `init_cache()`. See File-Level Plan rows for `resource_cache.py` + `cache_updater.py`. | bug-fix-engineer |
| IP-2 | DuckDB prewarm lock deadlock (AC-6) | Write failing test first, then remove `_try_lock`/`_release_lock` `O_EXCL` cross-worker lock from the master prewarm path; retain `.tmp`→final atomic rename. See File-Level Plan row for `resource_history_duckdb_cache.py`. | bug-fix-engineer |
| IP-3 | gunicorn process model | Set `preload_app = True`; add `post_fork(server, worker)` hook that calls `dispose_engine()`, `close_redis()`, SQLite handle reopen, then `_start_per_worker_services(app)`. Each step wrapped in try/except. | backend-engineer |
| IP-4 | app factory init-phase split | Extract per-worker thread starts from `create_app()` (lines 642-667 subset) into `_start_per_worker_services(app)`; keep single-run prewarm (lines 648-653 subset) in `create_app()` body so it runs once in master under preload. | backend-engineer |
| IP-5 | SQLite handle reinit | Provide a per-worker handle reopen for `log_store`, `login_session_store`, `metrics_history`; invoke from `post_fork`. Inherited sqlite3 connections are not fork-safe (`design.md` Affected Components row 5). | backend-engineer |
| IP-6 | tests (single-run + fork-safety) | Author `tests/test_post_fork_reinit.py`, `tests/integration/test_preload_fork_safety.py`; extend `tests/test_app_factory.py`, `tests/integration/test_soak_workload.py` per `test-plan.md` §Test Files. | backend-engineer |
| IP-7 | tests (version-guard regression) | Author `tests/test_resource_cache_version_check.py`; extend `tests/test_cache_updater.py` per `test-plan.md` §Test Files. | bug-fix-engineer |
| IP-8 | CI gate contract | Add the multi-worker "prewarm-runs-once / fork-safety" assertion gate to `contracts/ci/ci-gate-contract.md` and a version entry to `contracts/CHANGELOG.md` (`design.md` Affected Components row 9; `change-classification.md` §Required Contracts). Coordinate ownership with contract-reviewer before editing. | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (init-phase contract) | which work is single-run vs per-worker |
| design.md | D2 (`preload_app=True` + `post_fork`) | hook placement; why not `on_starting`/`when_ready` |
| design.md | D3 (resource_cache version fix) | AC-7 fix strategy (`init_cache()` path, keep periodic `force=False`) |
| design.md | D4 (DuckDB lock fix) | AC-6 fix strategy (remove `O_EXCL` from prewarm path, keep `.tmp` rename) |
| design.md | D5 (no new env var) | do not add a flag / do not touch env-contract.md |
| design.md | D6 + §Migration/Rollback | one-line revert; no parquet/DuckDB cleanup on rollback |
| design.md | §Affected Components table | per-file nature of change + existing primitive line refs |
| design.md | §Open Risks | dispose completeness, orphan master threads, master boot time, SIGTERM reload |
| change-classification.md | AC-1..AC-10 + §Risk Factors | acceptance scope + fork-safety hazards |
| change-classification.md | §Tasks Not Applicable | which tasks.yml items are skipped |
| test-plan.md | §Critical Test Names | exact test names backend-engineer/bug-fix-engineer must produce |
| test-plan.md | §Notes | marker discipline + `monkeypatch.setattr` + AC-7 file placement |
| ci-gates.md | §Required Gates table | verification commands (Tier 0/1 local, Tier 3 nightly, Tier 4 weekly) |
| ci-gates.md | §Rollback Policy | revert procedure; no spool cleanup |
| context-manifest.md | §Allowed Paths | read boundary; CER-001/002/003 approved expansions |

## File-Level Plan

Line numbers below are anchors confirmed during pre-flight reads; treat them as
"find the symbol near here," not literal targets — match the symbol, not the line.

| path | action | agent | precise target + notes |
|---|---|---|---|
| `src/mes_dashboard/services/resource_cache.py` | modify | bug-fix-engineer | `refresh_cache(force=False)` (def `:793`). The guard `if not force and redis_version == oracle_version:` (`:820`) is bypassed when `force=True`, causing the identical-version Oracle re-fetch. Fix per `design.md` D3: make the short-circuit fire even when `force=True` when `redis_version == oracle_version`, OR (preferred) leave `refresh_cache` semantics intact and route the initial load through `init_cache()` (`:844`, which already checks population at `:861` before calling `refresh_cache(force=True)` `:863`). Pick the D3-aligned approach: drive initial load via `init_cache()`; do NOT overload `force`. The misleading log at `:824` (`Resource cache version changed: X -> Y`) must not fire when versions are equal. |
| `src/mes_dashboard/core/cache_updater.py` | modify | bug-fix-engineer | `_worker()` (def `:110`) calls `self._check_resource_update(force=True)` at `:117` for the startup load. `_check_resource_update` (def `:308`) imports `refresh_cache as refresh_resource_cache` (`:319-320`). Per `design.md` D3: the startup resource-cache load moves to the master pre-fork path and should go through `init_cache()` (not `refresh_cache(force=True)`); the periodic worker loop keeps `force=False`. Confirm the periodic loop body still calls the version-checked path. After the split (IP-4), `_check_resource_update(force=True)` must no longer issue an Oracle fetch when Redis already holds the target version — pin with the `tests/test_cache_updater.py` regression (IP-7). |
| `src/mes_dashboard/services/resource_history_duckdb_cache.py` | modify | bug-fix-engineer | Remove the cross-worker file lock from the prewarm path: `_LOCK_PATH` (`:44`), `_try_lock()` (def `:47`, `os.O_CREAT \| os.O_EXCL` at `:51`), `_release_lock()` (def `:60`), and the 90s peer-wait loop in `start_duckdb_prewarm()` (def `:293`; loop `for _ in range(18)` at `:318` emitting `timed out waiting for peer worker` at `:322`). Per `design.md` D4: with a single master writer there is no concurrent writer, so the lock and the wait loop are removed entirely from this path. RETAIN the `.tmp`→final atomic rename (`tmp_path` `:242`, rename `:281`) for crash-safety. Confirm `_run_prewarm` (the body around `:240-290`) has a hard timeout and no infinite wait when called synchronously in master (see Known Risks). Do NOT introduce `fcntl.flock` here (dead code per D4; reserved for a future per-request re-warm path, recorded in the ADR). |
| `gunicorn.conf.py` | modify | backend-engineer | Add module-level `preload_app = True` (currently unset → defaults False; `workers` at `:7`). Add a new `def post_fork(server, worker):` hook (gunicorn auto-detects this name, like `on_starting` `:27` / `worker_exit` `:55`). The hook must, each step in its own try/except with a logged warning on failure (post_fork exceptions are fatal — see Known Risks): (1) `from mes_dashboard.core.database import dispose_engine; dispose_engine()` (drops inherited Oracle pools; workers re-create lazily — `core/database.py` `dispose_engine` at `:497` per design); (2) `from mes_dashboard.core.redis_client import close_redis; close_redis()` (drops inherited `_REDIS_CLIENT`/`_REDIS_CONTROL_CLIENT` — `core/redis_client.py` `close_redis` at `:179` per design); (3) reopen SQLite handles (call the IP-5 helper or per-store reopen functions); (4) call `_start_per_worker_services(app)` (IP-4). Do NOT modify `on_starting` or `worker_exit`. |
| `src/mes_dashboard/app.py` | modify | backend-engineer | Startup block lives under `if not is_testing_runtime:` (`:640`). Classify each call: SINGLE-RUN (stays in `create_app()` body, runs once in master under preload): `start_duckdb_prewarm()` (`:649`), `start_downtime_prewarm()` (`:651`), `start_parts_cache_warmup` material_consumption warmup (imported `:652`, the prewarm invocation), and the resource_cache initial load (now via `init_cache()` per D3). PER-WORKER (move into new `def _start_per_worker_services(app):` invoked from `post_fork`): `get_engine()` (`:641`), `start_keepalive()` (`:642`), `start_cache_updater()` (`:643`), `init_realtime_equipment_cache(app)` (`:644`), `init_scrap_reason_exclusion_cache(app)` (`:645`), `init_query_spool_cleanup(app)` (`:646`), `init_anomaly_detection_scheduler(app)` (`:647`), `start_metrics_history(app)` (`:655`), `start_worker_memory_guard()` (`:657`), `get_login_session_store()` init (`:659`), `start_sync_worker()` (conditional, `:666-667`). The background route-contract check `threading.Thread(target=check_shared_volume...)` (`:630`, daemon) is a one-shot diagnostic — keep it single-run in master OR move to per-worker; choose per-worker is unnecessary, keep in master (it is daemon, will not block fork — confirm). Add a master-context guard around `init_cache()`: if Redis is unavailable at master init, log a warning and let the per-worker path handle it in degraded mode (see Known Risks). Do NOT change `_shutdown_runtime_resources` / `worker_exit` cleanup. |
| `tests/test_post_fork_reinit.py` | new | backend-engineer | Tier 1, no marker. Unit-test each post_fork primitive per `test-plan.md` §Test Files row 1: `test_close_redis_disposes_connection_pool` (mock Redis client; assert `connection_pool.disconnect()` called), `test_sqlite_handles_reopen_per_worker` (inherited vs child handle are distinct objects). Mock-only; runs in default `pytest`. |
| `tests/test_resource_cache_version_check.py` | new | bug-fix-engineer | Tier 1, no marker. AC-7 per `test-plan.md` §Critical Test Names: `test_identical_version_skips_oracle_fetch` (assert zero Oracle calls when versions equal — use `monkeypatch.setattr()` on the module constant, NOT `setenv`), `test_changed_version_triggers_oracle_fetch` (assert exactly one Oracle call). MUST live in this file, NOT in `tests/integration/test_oracle_error_path.py` (that file has module-level `pytestmark = pytest.mark.integration_real`, which silently skips mock tests — `test-plan.md` §Notes). |
| `tests/integration/test_preload_fork_safety.py` | new | backend-engineer | Tier 3. Primary evidence layer for AC-1..AC-9 using `_multi_worker_harness.py`. Apply `@pytest.mark.integration_real` AND `@pytest.mark.multi_worker` PER-TEST or per-class — NEVER a module-level `pytestmark` (`test-plan.md` §Notes; lets `pytest -m "not integration_real"` collect-and-skip gracefully). Test names are fixed by `test-plan.md` §Critical Test Names (e.g., `test_downtime_prewarm_runs_once_across_two_workers`, `test_each_worker_has_distinct_oracle_engine_pool`, `test_duckdb_prewarm_no_timeout_two_workers`, `test_no_duplicate_parquet_files_on_two_worker_start`, `test_worker_crash_respawn_no_master_prewarm_retrigger`, …). If `_multi_worker_harness.py` / `kill_worker()` helper does not yet exist, create it under `tests/integration/`. |
| `tests/test_app_factory.py` | extend | backend-engineer | Add `test_post_fork_hook_registered_in_app_factory` (assert gunicorn server hooks expose a `post_fork` callable; AC-5) and `test_api_contracts_unchanged_after_preload` (pins AC-10 — no API shape change). Tier 1, no marker. |
| `tests/test_cache_updater.py` | extend | bug-fix-engineer | Add regression: `force=True` path no longer bypasses the Redis version check after the D3 change (AC-7 init_cache change). Tier 1, no marker. Use `monkeypatch.setattr()` for module-level constants. |
| `tests/integration/test_soak_workload.py` | extend | backend-engineer | Add 4-worker 30-min soak assertions per `test-plan.md` §Soak: stable thread count (no drift) and zero ORA errors per worker across a restart-loop. Tier 4, `soak` marker. Weekly lane only — not a PR gate. |
| `contracts/ci/ci-gate-contract.md` | modify | backend-engineer (coordinate w/ contract-reviewer) | Add the multi-worker "prewarm-runs-once / fork-safety" assertion gate (`design.md` Affected Components row 9; `ci-gates.md` §Required Gates `nightly-integration`). |
| `contracts/CHANGELOG.md` | modify | backend-engineer (coordinate w/ contract-reviewer) | Add a `## [ci <version>]` entry for the ci-gate-contract change. This is the ONLY location `cdd-kit validate --versions` checks — do NOT put the entry inside `ci-gate-contract.md` (CLAUDE.md CDD note). |

## Contract Updates

- API: none (AC-10; `change-classification.md` 2.1 read-only confirmation).
- CSS/UI: none (no UI surface; `change-classification.md` 2.2).
- Env: none — `preload_app` is a Python value, no new env var (`design.md` D5;
  `change-classification.md` 2.3 resolved to no-change by design). Do NOT touch
  `contracts/env/env-contract.md`.
- Data shape: none (`change-classification.md` 2.4).
- Business logic: none (`change-classification.md` 2.5).
- CI/CD: `contracts/ci/ci-gate-contract.md` — add the multi-worker
  prewarm-runs-once / fork-safety gate (`ci-gates.md` §Required Gates;
  `design.md` Affected Components row 9). Add the version entry to
  `contracts/CHANGELOG.md` only.

## Test Execution Plan

Authoritative AC→test mapping lives in `test-plan.md` §Acceptance Criteria → Test
Mapping and §Critical Test Names — follow it for exact test names. The table below
gives the run command + expected signal per criterion.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (prewarm runs once) | `tests/integration/test_preload_fork_safety.py` via `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | Oracle query count == 1 per prewarm across 2 workers; single parquet/DuckDB file; no timeout log |
| AC-2 (distinct Oracle pools) | same integration file/command | distinct engine pool identity per worker PID; no ORA-3135 / no cross-talk under concurrent load |
| AC-3 (distinct Redis pools) | `tests/test_post_fork_reinit.py::test_close_redis_disposes_connection_pool` (Tier 1) + integration `test_each_worker_has_distinct_redis_pool` | `connection_pool.disconnect()` called; distinct pool per worker |
| AC-4 (SQLite per-worker handles) | `tests/test_post_fork_reinit.py::test_sqlite_handles_reopen_per_worker` (Tier 1) + integration `test_sqlite_no_wal_corruption_on_restart` | inherited vs child handle distinct; write-then-restart-then-read succeeds, no WAL corruption |
| AC-5 (threads alive post_fork) | `tests/test_app_factory.py::test_post_fork_hook_registered_in_app_factory` + integration `test_all_background_threads_alive_post_fork` | `post_fork` callable registered; each expected thread name present in `threading.enumerate()` |
| AC-6 (no DuckDB lock deadlock) | integration `test_duckdb_prewarm_no_timeout_two_workers`, `test_duckdb_prewarm_completes_once` | no `timed out waiting for peer worker` in captured logs; parquet present, correct row count |
| AC-7 (identical version no fetch) | `tests/test_resource_cache_version_check.py` + `tests/test_cache_updater.py` regression via `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | zero Oracle calls when versions equal; exactly one when changed |
| AC-8 (no duplicate parquet) | integration `test_no_duplicate_parquet_files_on_two_worker_start` | `len(glob(spool_dir/*)) == expected` after 2-worker start |
| AC-9 (crash respawn) | integration `test_worker_crash_respawn_no_master_prewarm_retrigger`, `test_worker_crash_respawn_fresh_connections` | master prewarm count stays == 1 after respawn; respawned pool id differs from killed worker's |
| AC-10 (no contract drift) | `tests/test_app_factory.py::test_api_contracts_unchanged_after_preload` + `cdd-kit validate` | api/data/business/css contracts unchanged; validate passes |
| Tier-1 full gate | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | green (PR merge gate; `ci-gates.md`) |
| Tier-0 gates | `cdd-kit validate` ; `ruff check .` | pass (local pre-PR; `ci-gates.md`) |
| Soak (Tier 4, weekly) | `tests/integration/test_soak_workload.py` (`soak` marker) via soak-tests.yml | stable thread count, zero ORA errors over 4-worker 30-min run |

## Order of Operations (TDD sequence)

1. **bug-fix-engineer first.** Write failing tests for AC-7
   (`tests/test_resource_cache_version_check.py` + `tests/test_cache_updater.py`
   regression) and AC-6 (the duckdb prewarm no-deadlock unit/behavior test, and
   any addition to `tests/test_cache_updater_lock_behavior.py`) — confirm they
   fail BEFORE any fix (TDD). Then root-cause and fix IP-1 (resource_cache /
   cache_updater) and IP-2 (resource_history_duckdb_cache). Tests turn green.
   These two defects are independent of the preload split and must land first so
   backend-engineer builds on a correct dedupe baseline.
2. **backend-engineer second.** Read this plan + `design.md` + `test-plan.md`.
   Write the remaining test stubs (IP-6) — the multi-worker fork-safety tests and
   the app-factory extensions — confirm they fail. Then implement IP-3
   (`gunicorn.conf.py` `preload_app` + `post_fork`), IP-4 (`app.py`
   single-run/per-worker split), and IP-5 (SQLite handle reinit). Tests turn
   green. Finally IP-8 (CI gate contract + CHANGELOG), coordinating ownership
   with contract-reviewer.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into
  this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and
  report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion
  Request is approved (`context-manifest.md` §Allowed Paths; CER-001/002/003
  already approved).
- TDD is mandatory: every fix and every new behavior must have a test that fails
  before the change and passes after (`change-classification.md` §Required Agents
  steps 3-4).
- Marker discipline (`test-plan.md` §Notes): multi-worker integration tests use
  PER-TEST `@pytest.mark.integration_real` + `@pytest.mark.multi_worker`, never a
  module-level `pytestmark`. Never add mock-based tests to
  `tests/integration/test_oracle_error_path.py` (module-level
  `pytestmark = pytest.mark.integration_real` silently skips them).
- Module-level constants are patched with `monkeypatch.setattr()` on the
  attribute, not `monkeypatch.setenv()` (frozen at import; CLAUDE.md Test Coverage
  Discipline).
- CHANGELOG entries go ONLY in `contracts/CHANGELOG.md`, never inside individual
  contract files (CLAUDE.md CDD note — `cdd-kit validate --versions` only scans
  `contracts/CHANGELOG.md`).
- Before resolving section-6 tasks for `cdd-kit gate --strict`: mark 6.2/6.3 done
  only when local Tier-1 gate passes (CI runs the identical command); mark 6.4
  per the soak/nightly lanes defined in `ci-gates.md` (CLAUDE.md CDD note).

## Known Risks

- **`post_fork` exceptions are fatal.** A raised exception kills the worker;
  gunicorn respawns and re-crashes, taking the fleet down on deploy
  (`change-classification.md` §Risk Factors "Production startup path"). Wrap each
  reinit step (`dispose_engine`, `close_redis`, SQLite reopen,
  `_start_per_worker_services`) in its own try/except + logged warning; never let
  one failure cascade.
- **Orphan threads in the master.** If any `start_*`/`init_*` thread launch is
  accidentally left in the single-run (master) path, that thread runs only in the
  master and never in workers (silently degraded sync). Audit: after the IP-4
  split, no per-worker background thread launch may remain in the `create_app()`
  body. Assert "no sync/cache-updater thread alive in master" (`design.md`
  §Open Risks).
- **Daemon-thread audit before fork.** Any thread that DOES legitimately run in
  the master (e.g., the `spool-volume-check` diagnostic at `app.py:630`,
  `daemon=True`) must be a daemon thread — a live non-daemon thread in the master
  after `create_app()` blocks gunicorn from forking. Confirm `daemon=True` on
  every thread that can be alive in the master at fork time.
- **DuckDB prewarm runs synchronously in master under preload.** With
  `preload_app=True`, `create_app()` (and thus the prewarm calls) run inline in
  the master. Confirm `_run_prewarm` / `start_duckdb_prewarm` has a hard timeout
  and NO infinite wait loop once the `O_EXCL` peer-wait is removed (IP-2);
  otherwise a stuck Oracle query blocks the master from ever forking
  (`design.md` §Open Risks "Master prewarm lengthens boot"). Master boot now
  blocks on ~25s DuckDB + ~8s material load before fork — acceptable vs today's
  duplicated load.
- **Redis availability at master init.** `init_cache()` and any
  Redis-snapshot-dependent prewarm run in the master before fork; Redis must be
  reachable then. Add a guard: if Redis is unavailable at master init, log a
  warning and DEFER to the per-worker post_fork path (degraded mode — acceptable;
  do not crash the master).
- **Incomplete dispose leaks shared FDs into workers.** Any pool/handle the master
  opens during prewarm that `post_fork` does not drop becomes a shared, corrupt
  FD across workers (intermittent ORA errors, response cross-talk). Mitigation is
  the IP-3 hook calling all three of `dispose_engine()` (all 3 engines),
  `close_redis()`, and SQLite reopen; verified by the AC-2/AC-3/AC-4 multi-worker
  gates (`design.md` §Open Risks).
- **SIGTERM / graceful reload double-prewarm.** Under `preload_app`, a gunicorn
  reload re-runs master `create_app()`. Confirm a reload does not double-prewarm
  or strand a stale DuckDB `.tmp` file (`design.md` §Open Risks). Covered by the
  soak/restart-loop extension (IP-6, `tests/integration/test_soak_workload.py`).
- **Existing partial lock interaction.** The fix must reconcile the new
  single-master model with the already-present `O_EXCL` lock — removing it
  (IP-2), not layering a second mechanism on top (`change-classification.md`
  §Risk Factors "Existing partial implementation").
