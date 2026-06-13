---
change-id: downtime-rq-async
schema-version: 0.1.0
last-changed: 2026-06-13
---

# Implementation Plan: downtime-rq-async

## Objective
Add an env-gated RQ async query path to `POST /api/downtime-analysis/query` that returns HTTP 202 `{async:true, job_id, status_url}` for date ranges ≥ `DOWNTIME_ASYNC_DAY_THRESHOLD` (when `DOWNTIME_ASYNC_ENABLED=true` and a worker is available), while keeping the existing HTTP 200 synchronous path byte/row-identical for short ranges and all fallback cases. The async job is a thin worker fn that wraps the already-shipped `query_downtime_dataset_raw()`, dispatched through the Phase-2 dynamic job registry, with documented pct milestones and DA-11 two-parquet atomicity. See design.md §Summary and AC-1..AC-7 in change-classification.md.

## Execution Scope

### In Scope
- New backend job service `downtime_query_job_service.py` (worker fn + `JobTypeConfig` registration), mirroring `production_history_job_service.py` (design.md D1/D6).
- Sync/async branch in `downtime_analysis_routes.py::api_downtime_query` (design.md component table, lines 141-211; D4 fallback conditions).
- App-startup import wiring so `register_job_type("downtime",...)` runs (design.md component table; AC-7a).
- 4 new `DOWNTIME_*` env vars in `.env.example` (env-contract §Async Worker — Downtime Query; AC-4).
- Frontend 202 → polling → `AsyncQueryProgress` branch in `frontend/src/downtime-analysis/App.vue` + composables (AC-5).
- New deploy unit `deploy/mes-dashboard-downtime-worker.service` (`--queues downtime-query`) and `rq_monitor_service._QUEUE_NAMES` registration.
- CI step `npx playwright install --with-deps chromium` in `frontend-tests.yml` before the downtime spec.
- Tests per test-plan.md AC→test mapping (unit, contract, integration, e2e/resilience, data-boundary parity).

### Out of Scope
- Modifying `query_downtime_dataset_raw()` itself — it is wrapped, not changed (design.md D1; component table "No change").
- Modifying `job_registry.py` — consumed via existing `register_job_type()`/`enqueue_job_dynamic()` (design.md component table).
- Any `BatchQueryEngine` row-count chunking in the worker (ADR-0003 / design.md D5).
- New CSS / new shared-ui component — `AsyncQueryProgress` is a Phase-1 component (test-plan Out of Scope).
- New CI gate tier or workflow command (ci-gates.md §Workflow Gates).
- Parquet namespace/schema changes — async writes the same namespaces as the sync flag-ON path (design.md §Migration).
- Stress/soak test files (test-plan Out of Scope; informational gates only).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend service | Create `downtime_query_job_service.py`: `execute_downtime_query_job(*, job_id, owner, **query_params)` wrapping `query_downtime_dataset_raw()`; emit pct 5→15→60→90→100; `complete_job(prefix, job_id, query_id=...)` only after both parquets written; `register_job_type(JobTypeConfig(job_type="downtime",...))` at module import | backend-engineer |
| IP-2 | route | Add sync/async branch in `api_downtime_query` (L141-211): compute day span, gate on `_ASYNC_ENABLED` AND span ≥ `_ASYNC_DAY_THRESHOLD` AND `is_async_available()` → `enqueue_job_dynamic(...)` → 202; else fall through to unchanged sync 200 | backend-engineer |
| IP-3 | app startup | Import `downtime_query_job_service` in `app.py` factory so registration side-effect runs | backend-engineer |
| IP-4 | env | Add 4 `DOWNTIME_*` vars to `.env.example` with pinned defaults (true/30/downtime-query/1800) | backend-engineer |
| IP-5 | frontend | Branch `App.vue`/composable on 202 (`data.async`) → drive `useAsyncJobPolling.ts` + `AsyncQueryProgress.vue`; on finish read `result.query_id` → load both spools; 200 path unchanged | frontend-engineer |
| IP-6 | deploy | Create `deploy/mes-dashboard-downtime-worker.service` (`--queues downtime-query`, timeout from `DOWNTIME_JOB_TIMEOUT_SECONDS`); export identical `DOWNTIME_*`+DuckDB env set as gunicorn (design.md §Open Risks) | ci-cd-gatekeeper |
| IP-7 | ci/monitor | Add `os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query")` to `rq_monitor_service._QUEUE_NAMES`; add `npx playwright install --with-deps chromium` step in `frontend-tests.yml` before downtime spec | ci-cd-gatekeeper |
| IP-8 | tests | Author/extend all tests per Test Execution Plan below | test-strategist, e2e-resilience-engineer |
| IP-9 | contracts | Verify api/env/data/business/ci contract entries match shipped behavior (entries already present — verify, don't re-add) | contract-reviewer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (worker fn sig), D2 (pct map), D3 (DA-11 ordering), D4 (fallback), D5 (ADR-0003), D6 (new file) | implementation constraints |
| design.md | §Affected Components table | exact files + line ranges (route 141-211; raw fn 783-987) |
| design.md | §Open Risks | worker env parity, 60s availability race, importlib.reload registration |
| test-plan.md | AC→Test Mapping table + Notes | test files, names, tiers, monkeypatch.setattr/importlib.reload rules |
| test-plan.md | Test Update Contract | extend `TestTwoParquetAtomicity` for AC-6b — do not duplicate base fixture |
| ci-gates.md | Required Gates table | verification commands |
| ci-gates.md | Merge Eligibility | gate green list + `_QUEUE_NAMES` + systemd unit presence |
| env-contract.md | §Async Worker — Downtime Query (L108-120) | 4 var names, pinned defaults (true/30/downtime-query/1800) |
| api-contract.md | §7 Type B (L233-237); endpoints table L214; §10 note L375 | 202/200 response shapes |
| `production_history_job_service.py` | full file | mirror template for IP-1 (worker fn + JobTypeConfig) |
| `async_query_job_service.py` | `enqueue_job_dynamic` L341-378; `is_async_available` L57-103; `complete_job`/`update_job_progress` | dispatch + progress/complete protocol |
| `job_registry.py` | `register_job_type` L59-65; `JobTypeConfig`, `enqueue_job_dynamic` | registration interface (consume only) |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/downtime_query_job_service.py` | create | IP-1; mirror `production_history_job_service.py` |
| `src/mes_dashboard/routes/downtime_analysis_routes.py` | modify | IP-2; branch in `api_downtime_query` (L141-211); read `_ASYNC_ENABLED`/`_ASYNC_DAY_THRESHOLD`/`_ASYNC_WORKER_QUEUE`/`_JOB_TIMEOUT` module-level constants |
| `src/mes_dashboard/app.py` | modify | IP-3; import the new job service in factory |
| `.env.example` | modify | IP-4; 4 `DOWNTIME_*` vars |
| `frontend/src/downtime-analysis/App.vue` | modify | IP-5; 202/polling branch |
| `frontend/src/downtime-analysis/composables/` | modify | IP-5; wire query-dispatch composable to `useAsyncJobPolling.ts` (CER-001 approved) |
| `deploy/mes-dashboard-downtime-worker.service` | create | IP-6 (CER-002 approved) |
| `src/mes_dashboard/services/rq_monitor_service.py` | modify | IP-7; `_QUEUE_NAMES` += downtime queue |
| `.github/workflows/frontend-tests.yml` | modify | IP-7; playwright install step + optional concurrency block (ci-gates.md) |
| `tests/test_downtime_analysis_routes.py` | modify | add `TestDowntimeAsyncQuery`, `TestDowntimeJobDispatch` |
| `tests/test_downtime_analysis_service.py` | modify | add `TestDowntimeAsyncWorker`, `TestDowntimeAsyncEnvVars`; extend `TestTwoParquetAtomicity` (AC-6b) |
| `tests/integration/test_downtime_rq_async.py` | create | `pytestmark = pytest.mark.integration_real` |
| `tests/e2e/test_downtime_analysis_e2e.py` | modify | add `TestDowntimeAsyncResilience` |
| `frontend/tests/playwright/downtime-analysis.spec.js` | modify | long/short-range UX cases |

## Contract Updates

- API: `contracts/api/api-contract.md` — 202/200 shapes already recorded (L214, §7 L233-237, §10 note L375). Verify, do not re-add.
- CSS/UI: none.
- Env: `contracts/env/env-contract.md` §Async Worker — Downtime Query (L108-120) lists the 4 vars with pinned defaults. Verify `.env.example` matches.
- Data shape: `contracts/data/data-shape-contract.md` §3.14 — async job response shape + parquet parity (referenced by ci-gates contract-validate); verify present.
- Business logic: `contracts/business/business-rules.md` — async threshold gate rule cross-referencing DA-11 + ADR-0003; verify present.
- CI/CD: `contracts/ci/ci-gate-contract.md` §downtime-rq-async Gate Compatibility Note; schema-version 1.3.21 (ci-gates Merge Eligibility — already recorded).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 long-range → 202 | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_long_range_returns_202` | 202 + `{async,job_id,status_url}` |
| AC-2a short-range → 200 | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_short_range_returns_200` | 200 sync shape |
| AC-2b flag off → 200 | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_flag_disabled_returns_200` | 200 sync |
| AC-2c worker down → 200 | `tests/test_downtime_analysis_routes.py::TestDowntimeAsyncQuery::test_worker_unavailable_returns_200` | 200 fallback |
| AC-3 parity | `tests/integration/test_downtime_rq_async.py::TestDowntimeAsyncParity::test_worker_fn_parity_vs_sync` | byte/row-identical parquets |
| AC-4a..d env defaults | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncEnvVars` | defaults true/30/downtime-query/1800 (monkeypatch.setattr) |
| AC-5a long-range UX | `frontend/tests/playwright/downtime-analysis.spec.js` "should show async progress for long range query" | progress renders → results |
| AC-5b short-range UX | `frontend/tests/playwright/downtime-analysis.spec.js` "should show sync results for short range query" | no progress bar |
| AC-6a pct sequence | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncWorker::test_pct_milestones_sequence` | 5→15→60→90→100 in order |
| AC-6b DA-11 atomicity | `tests/test_downtime_analysis_service.py::TestDowntimeAsyncWorker::test_atomicity_base_hit_bridge_miss_raises_500` | loud 500 |
| AC-7a registration | `tests/test_downtime_analysis_routes.py::TestDowntimeJobDispatch::test_job_type_registered` | job type registered (importlib.reload) |
| AC-7b dispatch | `tests/integration/test_downtime_rq_async.py::TestDowntimeAsyncDispatch::test_enqueue_to_downtime_queue` | routed to downtime-query |
| Resilience timeout | `tests/e2e/test_downtime_analysis_e2e.py::TestDowntimeAsyncResilience::test_job_timeout_status_failed` | status=failed |
| Resilience cancel | `tests/e2e/test_downtime_analysis_e2e.py::TestDowntimeAsyncResilience::test_cancel_mid_job_abandon` | abandon flow |

Required test phases (floor): `collect`, `targeted`, `changed-area`. Add `contract` (api/env/data contract changes), `quality` (lint/css/type-check), and `full` per ci-gates.md Required Gates. Nightly `integration_real`/`multi_worker` gate covers AC-3 + AC-7b + resilience (test-plan tier 3 / ci-gates Nightly Gates). Implementation agents generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. Full ladder lives in test-plan.md and references/sdd-tdd-policy.md.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- `query_downtime_dataset_raw()` (downtime_analysis_service.py L783-987) is wrapped, not modified — do not edit it.
- Worker fn must own `update_job_progress`/`complete_job` and must not introduce row-count chunking (design.md D1/D5; ADR-0003).
- `base_events` parquet is written before `job_bridge`; `complete_job()` only after both succeed (design.md D3).
- Env-var tests use `monkeypatch.setattr()` on module-level constants; registration test uses `importlib.reload()` after clearing the registry dict (test-plan Notes; design.md §Open Risks).
- New systemd unit must export the same `DOWNTIME_*` + DuckDB env set as gunicorn (design.md §Open Risks — parity precondition for AC-3).
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- AC-3 parity depends on worker-process env matching gunicorn (DuckDB-prewarm/Oracle-fallback). IP-6 must assert identical env export; otherwise parity can silently drift.
- `is_async_available()` 60 s cache: a worker that dies mid-window can still receive a 202 for up to 60 s before fallback engages; the in-flight job then times out and the frontend retries (covered by resilience tests).
- `register_job_type("downtime",...)` is a module-level side effect — `setattr` alone will not re-run it; tests must `importlib.reload()` after clearing the registry dict.
- Code map generated 2026-06-13 by cdd-kit 3.1.0 at current HEAD — treated as fresh; line ranges above sourced from it and design.md.
