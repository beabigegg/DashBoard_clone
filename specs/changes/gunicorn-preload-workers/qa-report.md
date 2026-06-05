# QA Report — gunicorn-preload-workers

- change-id: gunicorn-preload-workers
- tier: 0
- risk: critical
- reviewer: qa-reviewer
- date: 2026-06-05
- decision: **approved-with-risk**
- sign-off: requires second reviewer (spec-architect) per high/critical two-reviewer rule

## Decision Summary

The architecture (`preload_app = True`, `post_fork` reinit hook, master-only prewarm
split, `worker_exit` retained) is implemented and the unit-level building blocks are
proven by passing tests. All merge-blocking gates are green. However this Tier 0
critical change ships with **zero executed multi-worker / fork evidence** (the entire
integration layer is `pytest.skip` stubs), a **missing required `stress-soak-report.md`
artifact with no soak run**, and **two documentation-integrity deviations** where the
accepted ADR-0004 / design.md describe behavior the as-built code does not match.

None of the *executed* evidence is failing and rollback is a one-line revert, so the
change is shippable **with documented conditions and a mandatory first-restart
verification** — not `blocked`. It is not `approved`, because the classifier-required
soak artifact is absent and the design's own named risk-mitigation gate
("multi-worker integration gate") does not yet execute.

## Gate Results

| gate | tier | command | result | evidence |
|---|---:|---|---|---|
| contract-validate | 0 | `cdd-kit validate` | PASS | all validators incl. contract-versions, ci-gates, spec-traceability |
| lint (changed files) | 0 | `ruff check <this change's files>` | PASS | "All checks passed!" on gunicorn.conf.py, app.py, resource_cache.py, resource_history_duckdb_cache.py + test files |
| lint (repo-wide) | 0 | `ruff check .` | 7 errors, all pre-existing & out-of-scope | see Pre-existing Failures table |
| unit-mock-integration (Tier 1 PR gate) | 1 | exact ci-gates.md command | PASS | **4359 passed, 122 skipped, 0 failed** (149s) |
| new/changed unit tests | 1 | targeted pytest | PASS | 31 passed (version-check 5, lock-behavior 8, post_fork_reinit 5, app_factory 13) |
| integration multi-worker (Tier 3) | 3 | `pytest tests/integration/test_preload_fork_safety.py` | **NOT EXECUTED** | 14 collected, **14 skipped** — all `pytest.skip` stubs |
| soak (Tier 4) | 4 | soak-tests.yml | **NOT RUN** | test stub exists (`@pytest.mark.soak`), requires live gunicorn+Oracle harness; no run, no report |
| type-check | 0 | `mypy src/` | informational | non-blocking per ci-gates.md |

Note on count discrepancy: task brief claimed "4399 passed / 201 skipped"; the
authoritative ci-gates.md PR-gate command yields 4359/122. The delta is collection
scope, not failures — 0 failed either way.

## AC Coverage

| criterion | evidence | strength | status |
|---|---|---|---|
| AC-1 prewarm runs once per restart (4 tasks) | Architecture wires all 3 prewarm calls + resource_cache into `create_app()` master-only block (app.py:818-836); integration proof `test_*_prewarm_runs_once*` is **stubbed/skipped** | code-present, **no cross-PID proof** | **partial — stub only** |
| AC-2 per-worker Oracle pool, no cross-talk | `post_fork` calls `dispose_engine()`; integration `test_each_worker_has_distinct_oracle_engine_pool` / `test_concurrent_oracle_requests_no_cross_talk` **skipped** | primitive-present, **no cross-PID proof** | **partial — stub only** |
| AC-3 per-worker Redis pool | UNIT PASS: `test_close_redis_disposes_connection_pool`, `test_close_redis_handles_control_client_separately` (asserts singleton nulled + `.close()` called). Integration half skipped | strong unit, no live | **PASS (unit) / stub (live)** |
| AC-4 per-worker SQLite handles, no WAL corruption | UNIT PASS: `test_sqlite_handles_reopen_per_worker` (thread-local conn cleared for all 3 stores). Restart/WAL integration `test_sqlite_no_wal_corruption_on_restart` **skipped** | strong unit, **no WAL-across-restart proof** | **PASS (unit) / stub (live)** |
| AC-5 all background threads alive post_fork | UNIT PASS: hook registered + callable (`test_post_fork_hook_registered_in_gunicorn_conf`), FLASK_TESTING guard (`test_start_per_worker_services_returns_early_in_test_mode`). `_start_per_worker_services` enumerates all ~11 threads. Live `test_all_background_threads_alive_post_fork` **skipped** | registration proven, **thread-liveness-per-worker not proven** | **partial — stub for liveness** |
| AC-6 DuckDB prewarm no deadlock, one runner | UNIT PASS: `test_cache_updater_lock_behavior.py` (+4 flock tests). Live `test_duckdb_prewarm_no_timeout_two_workers` **skipped**. NOTE: implementation kept `_try_lock()` + 90s peer-wait loop + 10s threaded delay (deviation, see Findings) | flock primitive proven, **no-deadlock-across-workers not proven** | **PASS (unit) / stub (live)** |
| AC-7 resource_cache no re-query on identical version | UNIT PASS: `test_resource_cache_version_check.py` (5 tests) — identical-version → 0 Oracle calls; changed → 1 call | strong unit | **PASS** |
| AC-8 no duplicate parquet on 2-worker start | Integration `test_no_duplicate_parquet_files_on_two_worker_start` **skipped** | **no proof** | **stub only** |
| AC-9 crash respawn re-runs post_fork, no master re-prewarm | Integration `test_worker_crash_respawn_*` **skipped** | **no proof** | **stub only** |
| AC-10 no API/data/business/CSS change | `cdd-kit validate` API conformance PASS; contract-reviewer confirmed; no api/data/business/css contract files in diff; `test_api_contracts_unchanged_after_preload` present | strong | **PASS** |

Net: AC-3, AC-4(unit), AC-5(registration), AC-7, AC-10 have passing executed
evidence. AC-1, AC-2, AC-6(live), AC-8, AC-9 rest entirely on skipped stubs.

## Findings

### F1 — Required `stress-soak-report.md` artifact missing (classifier-mandated)
change-classification.md marks `stress-soak-report.md` as `create? = yes`
("Concurrency/startup change; restart-loop soak evidence required"). The file does
not exist and no soak has been executed. tasks.yml 3.5 is marked `done` ("planned by
test-strategist"); a *planned* Tier 4 test is not soak *evidence*. This is the single
biggest gap for a change whose risk thesis is silent post_fork failure under sustained
multi-worker load.

### F2 — All 14 multi-worker integration tests are skip stubs; this is the design's own named mitigation gate
design.md Open Risks: "any pool/handle the master opens during prewarm that is not
dropped in post_fork becomes a shared, corrupt FD ... **covered by a multi-worker
integration gate**." ci-gates.md: "the multi-worker test is the **authoritative
pre-deploy signal** for this change." That gate executes nothing today. The
fork-correctness contract (distinct pools across PIDs, single prewarm across workers,
no deadlock, crash-respawn) is unverified end-to-end.

### F3 — As-built code contradicts accepted ADR-0004 / design.md D4 (DuckDB lock)
ADR-0004 (status: accepted) and design D4 state the cross-worker DuckDB lock is
**removed from the prewarm path** (single master is the only writer) and explicitly
**reject `fcntl.flock` as "dead code."** Commit 624d24b instead implemented the
rejected `fcntl.flock(LOCK_EX|LOCK_NB)`, and `start_duckdb_prewarm()` still spawns a
background thread with a 10s delay and the 18×5s (90s) peer-wait loop
(`resource_history_duckdb_cache.py:320-359`). The inline comment at app.py:825 even
says prewarm is "guarded by fcntl.flock so concurrent pre-fork calls are safe" —
which presumes concurrency the design says cannot exist under a single master writer.
Safety impact: **none negative** (flock auto-releases; strictly safer than the old
O_EXCL). Integrity impact: an `accepted` ADR no longer describes the shipped code, on
a change whose entire deliverable is "a documented fork-lifecycle contract."

### F4 — As-built resource_cache fix is the alternative D3 rejected
design D3 specifies driving the initial load through `init_cache()`'s
population-checked path and **rejects** "re-add a population check inside
`refresh_cache(force=True)`." Commit 624d24b added exactly that population check inside
the `force=True` branch (`resource_cache.py:824-833`). `init_cache()` already exists
and is the contract-described path; both achieve "no re-query on identical version"
(observable AC-7 outcome holds), but the code path diverges from the recorded
decision. Belt-and-suspenders, not a regression.

### F5 — tasks.yml overstates verification state
6.4 marked `done` with note "verified on CI schedule post-merge" — nightly/soak have
not run (this is pre-merge). 3.5 `done` though no soak ran. These should read
`pending`/scheduled, not `done`, to avoid implying evidence that does not exist.

## Risk Residuals (must be confirmed on first production restart)

Because no live fork evidence exists, the following MUST be checked in `error.log` on
the first preload deploy, before declaring the change verified:
1. Each prewarm logs **exactly once** (no N× duplication): downtime, material,
   resource-history DuckDB, resource_cache.
2. **No** `version changed: X -> X` line (AC-7 in production).
3. **No** `timed out waiting for peer worker` line from resource-history DuckDB (AC-6).
4. No `ORA-` errors / response cross-talk under first concurrent load (AC-2).
5. Background-thread set present in **every** worker PID, not just one (AC-5) — the
   master-only-thread orphan risk named in design Open Risks.
6. Graceful reload (SIGHUP) does not double-prewarm or strand a `.tmp` (design Open Risk).

Owner for first-restart verification: deploy operator + backend-engineer.
If any of 1–6 fails: rollback per below and route to backend-engineer + spec-architect.

## Deploy Runbook Checklist

Before deploy:
- [ ] Confirm `GUNICORN_WORKERS >= 2` in target env (preload split is a no-op at 1).
- [ ] Confirm `gunicorn.pid` / `--pid` is configured if the soak restart-loop will run.

Deploy:
- [ ] Ship `preload_app = True` + `post_fork` (already in working tree).
- [ ] NO parquet cleanup required (design D6 — no spool/DuckDB schema change). Confirmed:
      diff touches no `.sql` and no spool column schema.
- [ ] NO database migration.
- [ ] NO `.env` change (design D5 — no new env var).

After deploy (first restart — REQUIRED, see Risk Residuals 1–6):
- [ ] Tail `error.log`, verify items 1–6 above.

Rollback (one-line, per ci-gates.md / design D6):
- [ ] Set `preload_app = False` (or remove it) in `gunicorn.conf.py`; redeploy. Workers
      resume per-worker startup; pools/threads re-create lazily. No parquet/DuckDB/env
      cleanup, no migration rollback.

Rollback policy completeness: **adequate.** Covers preload revert, no-parquet-cleanup
(correctly justified), no-migration, no-env. Matches the actual diff.

## Pre-existing Failures Excluded From This Gate

| failure/test | baseline evidence | why outside scope | owner/follow-up |
|---|---|---|---|
| ruff F841 `core/duckdb_runtime.py:153` | last touched by `93a1850` (admin-perf-detail), not in this diff | file not modified by this change | backend-engineer / cleanup ticket |
| ruff F401 `services/downtime_analysis_service.py:618` | last touched by `50bad47` (downtime-analysis) | not in this diff | backend-engineer / cleanup ticket |
| ruff F401 ×1 `services/production_history_service.py:44` | unrelated prior commit | not in this diff | backend-engineer / cleanup ticket |
| ruff F401 ×2 `services/resource_history_service.py:20` | unrelated prior commit | not in this diff | backend-engineer / cleanup ticket |
| ruff F821 `tests/stress/test_chunk_boundary.py:361` | last touched by `e89c54f` (batch-rowcount) | not in this diff; stress tier not a PR gate | test-strategist / cleanup ticket |
| ruff E401 `tests/test_admin_routes_logs.py:62` | last touched by `5fc671f` (admin-dashboard) | not in this diff | backend-engineer / cleanup ticket |

This change's own files are ruff-clean. The 7 repo-wide errors are pre-existing and
do not gate this merge.

## Fixback Routing

- F1 (missing soak artifact) -> test-strategist + qa-reviewer (produce stress-soak-report.md from a real or harnessed run, or formally downscope with spec-architect approval)
- F2 (stubbed integration gate) -> test-strategist (implement gunicorn subprocess harness) + backend-engineer
- F3 (ADR/design vs code, DuckDB lock) -> spec-drift-auditor + spec-architect + contract-reviewer (reconcile ADR-0004/D4 to as-built, or align code to remove the lock)
- F4 (resource_cache D3 deviation) -> spec-architect (update D3 to record belt-and-suspenders as-built) — low priority, outcome-equivalent
- F5 (tasks.yml overstated status) -> change owner (correct 3.5 / 6.4 to pending/scheduled)

## Follow-up Items (non-blocking, owner + date)

| id | item | owner | due |
|---|---|---|---|
| FU-1 | Run/produce `stress-soak-report.md` (restart-loop + thread-count-drift soak) | test-strategist | before first nightly post-merge |
| FU-2 | Implement gunicorn subprocess harness; un-stub the 14 `test_preload_fork_safety.py` tests; they must pass on nightly BEFORE production deploy | test-strategist + backend-engineer | before production deploy |
| FU-3 | Reconcile ADR-0004 + design D4 with as-built `fcntl.flock`/threaded prewarm (update ADR to accepted-as-built, or remove the lock) | spec-architect + spec-drift-auditor | before merge to main |
| FU-4 | Run `spec-drift-auditor` (pre-merge cadence + late-discovered drift trigger F3/F4) | spec-drift-auditor | before merge to main |
| FU-5 | Correct tasks.yml 3.5 / 6.4 status overstatement | change owner | before close |

## Decision

**approved-with-risk** — conditional on:
1. First-restart verification (Risk Residuals 1–6) executed and clean, AND
2. FU-2 multi-worker integration tests un-stubbed and green on nightly BEFORE production deploy
   (ci-gates.md already names this the authoritative pre-deploy signal), AND
3. Second reviewer sign-off (spec-architect) per high/critical two-reviewer rule, AND
4. FU-3 ADR/design reconciliation before merge to main.

Mergeable to a non-main integration branch now (Tier 1 green, reversible). NOT cleared
for production deploy until conditions 1–2 are met. The missing soak artifact (F1) and
stubbed gate (F2) are why this is not a plain `approved`.
