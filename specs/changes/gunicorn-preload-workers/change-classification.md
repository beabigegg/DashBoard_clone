# Change Classification

## Summary

Enable `preload_app = True` in `gunicorn.conf.py` and add a fork-safe `post_fork` worker reinitialization path so that single-run startup work (Oracle prewarm, parquet spool writes, version-gated cache loads) executes once in the master process before fork, while per-worker resources (Oracle connection pool, Redis connection pool, SQLite file handles, all background threads) are correctly re-created in each forked worker. Fixes N× Oracle load on restart, duplicate/competing parquet writes, the `resource_history_duckdb_cache` file-lock deadlock, and the `resource_cache` version-identical reload bug. No user-facing API, schema, or report-behavior change.

## Change Types
- primary: `bug-fix`, `infrastructure-change` (concurrency / process-model)
- secondary: `ci-cd-change`

## Risk Level
- critical

Rationale: `post_fork` runs on every worker start. A partial or incorrect reinit does not fail loudly — it produces workers serving requests on shared/stale Oracle or Redis connections, corrupted SQLite handles inherited across fork, or dead background threads. The blast radius is the entire worker fleet and every report page.

## Impact Radius
- system-wide

## Tier
- 0

## Risk Factors

- **Fork safety — Oracle pool**: connection pools created pre-fork share sockets across workers; post_fork must dispose/recreate the SQLAlchemy engine. Shared connections cause intermittent ORA errors and response cross-talk under load.
- **Fork safety — Redis pool**: module-level `redis.Redis`/RQ client must be reset post_fork; inherited sockets multiplex two workers onto one connection.
- **Fork safety — SQLite handles**: `log_store.py`, `login_session_store.py`, `metrics_history.py` open SQLite files; inherited write handles risk WAL corruption.
- **Fork safety — background threads**: threads do NOT survive `fork()`. cache_updater, realtime_equipment_cache, scrap_reason_exclusion_cache, metrics_history, worker_memory_guard, anomaly_detection_scheduler, keep-alive, query_spool_store cleanup — each must be (re)started in post_fork.
- **Single-run vs per-worker split correctness**: prewarm work (downtime_analysis_cache, material_consumption_service, resource_history_duckdb_cache, resource_cache) must move to a pre-fork master hook and run exactly once; per-worker work must stay in post_fork. Putting prewarm in post_fork re-introduces the N× bug.
- **Production startup path, no fallback**: a post_fork exception kills the worker; gunicorn will respawn and re-crash, taking the fleet down on deploy.
- **Existing partial implementation interaction**: `resource_history_duckdb_cache` already has a file-lock that deadlocks; the fix must reconcile the new model with the existing lock.
- **`resource_cache` version-compare bug**: logs "version changed: X -> X" then re-queries — a correctness defect that must be fixed in tandem.
- **Spool-namespace coupling**: prewarm writes to namespaced parquet; moving to single-run must preserve namespace alignment or prewarm becomes a no-op.

## Architecture Review Required
- yes
- reason: Redefines the process/concurrency model (pre-fork master vs post-fork worker). Must establish a non-obvious boundary for "what runs once vs per worker" across 8+ subsystems. `spec-architect` must write `design.md` and an ADR before `implementation-planner` runs.

## Required Artifacts

Always required: `change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

| artifact | create? | reason |
|---|---|---|
| design.md | yes | Architecture Review Required = yes |
| qa-report.md | yes | Tier 0 startup change with no loud failure mode; needs durable multi-worker verification evidence |
| stress-soak-report.md | yes | Concurrency/startup change; restart-loop soak evidence required |
| current-behavior.md | no | Captured in change-request Known Context |
| proposal.md | no | No user-facing/product decision |
| spec.md | no | No new user-facing behavior |
| regression-report.md | no | Promote to yes only if a regression is found |
| visual-review-report.md | no | No UI/CSS surface |
| monkey-test-report.md | no | No UI interaction surface |

## Required Contracts
- contracts/ci/ci-gate-contract.md — update required (multi-worker single-run gate must be added)
- contracts/env/env-contract.md — conditional: only if implementation introduces a new env var; architect decides in design.md
- contracts/CHANGELOG.md — version entry for any contract that changes

## Required Tests
- unit: per-subsystem reinit helpers; `resource_cache` version-compare fix; single-run guard idempotence
- integration: multi-worker harness proving single-run, fresh-connection, thread-alive, no-deadlock, no-duplicate-parquet
- E2E smoke: app boots under `preload_app=True` and serves a representative report page
- resilience: worker crash/respawn re-runs post_fork correctly without re-triggering master prewarm
- soak: restart-loop / long-running multi-worker soak (weekly CI, not pre-merge per test-layer governance)

## Required Agents

Ordered:
1. `spec-architect` — author `design.md` + ADR: define init-phase contract, reinit strategy, existing lock reconciliation, rollback model, env-flag decision
2. `implementation-planner` — execution packet after design + contracts + tests are known
3. `bug-fix-engineer` — reproduce four defects with failing tests before fixing; root-cause the duckdb file-lock deadlock
4. `backend-engineer` — implement under TDD: `preload_app=True`, post_fork/master hooks, per-subsystem reinit, single-run guards, `resource_cache` fix
5. `test-strategist` — AC → Test Mapping; multi-worker/integration/resilience/soak matrix
6. `contract-reviewer` — confirm API/data/business/CSS untouched; confirm CI contract updated; verify CHANGELOG
7. `qa-reviewer` — Tier 0 release readiness: multi-worker evidence, fresh-connection/thread-restart proofs, deploy + rollback runbook

## Inferred Acceptance Criteria

- AC-1: With `preload_app = True` and N≥2 workers, each single-run prewarm task (downtime_analysis, material_consumption, resource_history, resource_cache) executes exactly once per restart, not once per worker.
- AC-2: After fork, each worker holds its own freshly created Oracle connection pool — no Oracle socket is shared across worker PIDs; concurrent requests produce no ORA errors or cross-talk.
- AC-3: After fork, each worker holds its own Redis connection pool / RQ client — no inherited Redis socket is multiplexed across workers.
- AC-4: After fork, SQLite-backed stores (log_store, login_session_store, metrics_history) operate on per-worker handles with no WAL corruption across a restart cycle.
- AC-5: Every background thread (cache_updater 600s, realtime_equipment 300s, scrap_reason_exclusion 86400s, metrics 30s, memory_guard 15s, anomaly scheduler, keep-alive, spool cleanup) is running in each worker after post_fork.
- AC-6: `resource_history_duckdb_cache` prewarm completes once without the dual-worker file-lock deadlock/timeout; only the elected runner performs the Oracle load.
- AC-7: `resource_cache` does not re-query Oracle when the cached version is unchanged; a unit test pins identical-version → no Oracle fetch.
- AC-8: No duplicate parquet spool files are written by competing workers for the affected datasets on a single restart.
- AC-9: A single worker crash respawns and re-runs post_fork correctly without re-triggering master pre-fork prewarm, and without leaking connections/threads.
- AC-10: No user-facing API, report behavior, data shape, or business rule changes — api/data/business/css contracts remain untouched.

## Tasks Not Applicable

Mark these as `status: skipped` in tasks.yml:
- 2.1 — API contract (read-only confirmation only; no update required)
- 2.2 — CSS/UI contract (no UI surface)
- 2.4 — Data shape contract (explicit non-goal)
- 2.5 — Business logic contract (explicit non-goal)
- 3.4 — Data-boundary/monkey tests (no interaction surface)
- 4.2 — Frontend (no UI changes)
- 5.1 — UI/UX review (no UI)
- 5.2 — Visual review (no UI)

Keep pending until design.md decision:
- 2.3 — Env contract (conditional on whether a new env var/flag is introduced)
