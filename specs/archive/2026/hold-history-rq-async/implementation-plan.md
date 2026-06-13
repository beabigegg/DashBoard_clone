---
change-id: hold-history-rq-async
schema-version: 0.1.0
last-changed: 2026-06-13
---

# Implementation Plan: hold-history-rq-async

## Objective

Add a threshold-gated async (RQ) execution path to `POST /api/hold-history/query`, mirroring the shipped Phase 3-A `downtime-rq-async` pattern. Long-range queries return HTTP 202 + job handle and stream per-chunk progress to the existing `AsyncQueryProgress` UI; short-range queries (and any flag-off / Redis-down case) keep the existing synchronous 200 path byte-for-byte. The async worker wraps the unmodified `execute_primary_query()`; result parity with the sync path is mandatory.

This is Phase 3-B of `docs/dynamic-rq-migration-plan.md`. Architecture is pre-decided; no `design.md` (classification: Architecture Review Required = no). The single bounded deviation from 3-A — row-count chunking with per-chunk pct milestones, and the confirmation that ADR-0003 does NOT apply here — is captured in this plan.

### ADR-0003 applicability (confirmed)
ADR-0003 (`docs/adr/0003-downtime-rowcount-chunking-exclusion.md`) excludes *downtime* from row-count chunking because downtime applies cross-row, whole-dataset reductions (`_merge_cross_shift_events`, `_bridge_jobid`) that would be split across chunk seams. Hold-history has NO such cross-row reductions: `hold_dataset_cache.execute_primary_query()` already uses `decompose_by_row_count()` + `execute_plan()` + `merge_chunks_to_spool()` (row-count chunking) under `_USE_ROW_COUNT_CHUNKING` today. The ADR-0003 exclusion therefore does NOT apply. (The separate single-chunk whole-range branch in `execute_primary_query` is the open-hold `RELEASETXNDATE IS NULL` escape guard, unrelated to ADR-0003.) No ADR change required.

## Execution Scope

### In Scope
- New `src/mes_dashboard/services/hold_query_job_service.py` (worker fn + `should_use_async` gate + 4 `HOLD_*` constants + module-level `register_job_type(...)`), modeled on `downtime_query_job_service.py`.
- Async dispatch branch added to `api_hold_history_query()` in `hold_history_routes.py` (202 on async, fall-through to existing sync 200 path otherwise).
- Module-level `HOLD_*` constants in `hold_history_routes.py` (mirror `downtime_analysis_routes.py` `_ASYNC_ENABLED`/`_ASYNC_DAY_THRESHOLD` pattern).
- Job-service import in `app.py` so `register_job_type("hold-history", ...)` fires at startup.
- `rq_monitor_service._QUEUE_NAMES` gains the hold queue.
- New systemd unit `deploy/mes-dashboard-hold-history-worker.service` (clone of downtime unit, `HOLD_*` env vars).
- Frontend hold-history app: 202 branch → poll → `AsyncQueryProgress`, mirroring `frontend/src/downtime-analysis/`.
- Contract updates: `env-contract.md` + `.env.example` (4 `HOLD_*` vars), `api-contract.md` + `api-inventory.md` (202 response), `ci-gate-contract.md` (new queue + worker unit + Gate Compatibility Note).
- Tests per `test-plan.md` Acceptance Criteria → Test Mapping.

### Out of Scope
- `execute_primary_query()` internals in `hold_dataset_cache.py` — wrap only; do NOT add a `progress_callback` parameter or otherwise modify its body or signature (see Known Risks for the milestone consequence).
- `apply_view()`, `hold_history_sql_runtime.py`, `batch_query_engine.py`, SQL files — read-only references.
- `today-snapshot` route, `hold_history_service.py` trend/pareto/duration functions — unaffected.
- DA-11 two-parquet atomicity — hold-history uses a single `hold_dataset` spool namespace.
- New CSS layer / `AsyncQueryProgress.vue` rework — reuse the existing shared component.
- Stress/soak tests — reuse existing suites; not pre-merge (test-layer governance).
- Opportunistic refactor of the sync path or the engine.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend / service | Create `hold_query_job_service.py`: 4 `HOLD_*` module constants, `should_use_async(params)`, `enqueue_hold_history_query(params, owner)` (delegates to `enqueue_job_dynamic("hold-history", ...)`), `execute_hold_history_query_job(*, job_id, owner, **params)` worker wrapping `execute_primary_query()`, and module-level `register_job_type(JobTypeConfig(job_type="hold-history", queue_name=HOLD_WORKER_QUEUE, worker_fn=..., timeout_seconds=HOLD_JOB_TIMEOUT_SECONDS, ttl_seconds=HOLD_JOB_TTL_SECONDS, should_enqueue=should_use_async))`. | backend-engineer |
| IP-2 | backend / route | Add `HOLD_ASYNC_ENABLED`, `HOLD_ASYNC_DAY_THRESHOLD`, `HOLD_WORKER_QUEUE`, `HOLD_JOB_TIMEOUT_SECONDS` module constants to `hold_history_routes.py`; add async branch to `api_hold_history_query()` (after param validation, before the `execute_primary_query` try-block): if `should_use_async(params)` and `is_async_available()`, `enqueue_job_dynamic`/`enqueue_hold_history_query` → on success return `success_response({"async": True, "job_id": ..., "status_url": f"/api/job/{job_id}?prefix=hold-history"}, status_code=202)`; on enqueue failure or any precondition miss, fall through to the existing sync 200 path unchanged. | backend-engineer |
| IP-3 | backend / startup | Add `import mes_dashboard.services.hold_query_job_service  # noqa: F401` next to the existing downtime import in `app.py` (~line 893) so `register_job_type` runs before requests. | backend-engineer |
| IP-4 | backend / monitor | Add `os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")` to `rq_monitor_service._QUEUE_NAMES` (after the downtime entry, ~line 30). | backend-engineer |
| IP-5 | deploy | Create `deploy/mes-dashboard-hold-history-worker.service` by cloning `mes-dashboard-downtime-worker.service`; substitute queue/timeout env to `HOLD_WORKER_QUEUE` (default `hold-history-query`) / `HOLD_JOB_TIMEOUT_SECONDS` (default 1800); SyslogIdentifier `mes-dashboard-hold-history-worker`. | backend-engineer / ci-cd-gatekeeper |
| IP-6 | frontend | In `frontend/src/hold-history/`, mirror `frontend/src/downtime-analysis/`: handle the 202 response, drive `useAsyncJobPolling.ts` with `prefix=hold-history`, render `<AsyncQueryProgress>` with cancel support, load result on completion. Suppress LoadingOverlay while async progress is active (`v-if="... && !asyncJobProgress.active"` — css-contract Rule 4.6). | frontend-engineer |
| IP-7 | contracts | Update `env-contract.md` + `.env.example` (4 `HOLD_*` vars, pinned defaults); `api-contract.md` + `api-inventory.md` (202 async response on `POST /api/hold-history/query`); `ci-gate-contract.md` (new `hold-history-query` queue, worker unit, hold-history-e2e Gate Compatibility Note). | backend-engineer (env/api), ci-cd-gatekeeper (ci) |
| IP-8 | tests | Author/extend tests per `test-plan.md` mapping (see Test Execution Plan). | test-strategist / backend-engineer / frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | Acceptance Criteria → Test Mapping; Test Update Contract; Notes | test files/commands, env-default assertions, milestone-ordering assertions |
| ci-gates.md | Required Gates table; Workflow Gates; Rollback Policy | verification commands, e2e job placement, soft/hard rollback |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8; Clarifications 1-4 | AC scope; parity/data-shape assumption |
| docs/dynamic-rq-migration-plan.md §階段三-B / §關鍵檔案索引 | 3B-1..3B-4; HOLD_* defaults | canonical pattern, env defaults, file list |
| docs/adr/0003-downtime-rowcount-chunking-exclusion.md | Decision / Context | confirms exclusion does NOT apply to hold-history |
| src/mes_dashboard/services/downtime_query_job_service.py | full file (template) | worker fn + register_job_type structure |
| src/mes_dashboard/services/production_history_job_service.py | `enqueue_*` delegation (lines 62-86) | enqueue helper pattern |
| src/mes_dashboard/routes/downtime_analysis_routes.py:160-229 | async branch + module constants | route 202 dispatch + fall-through template |
| src/mes_dashboard/services/hold_dataset_cache.py:141-313 | `execute_primary_query` signature + BQE call site | wrap target; milestone-placement constraint |
| contracts/env/env-contract.md:112-120 | DOWNTIME_* rows | row format to mirror for HOLD_* |
| deploy/mes-dashboard-downtime-worker.service | full file | systemd unit template |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/hold_query_job_service.py` | create | IP-1. Constants: `HOLD_ASYNC_ENABLED` (default true), `HOLD_ASYNC_DAY_THRESHOLD` (default 90), `HOLD_WORKER_QUEUE` (default `hold-history-query`), `HOLD_JOB_TIMEOUT_SECONDS` (default 1800), `HOLD_JOB_TTL_SECONDS` (default 3600). `_JOB_PREFIX = "hold-history"`. Worker wraps `execute_primary_query(start_date, end_date, hold_type, record_type)`; coarse pct milestones 5→15→90→100 bracketing the call (see Known Risks for per-chunk option). `register_job_type(...)` at module end. |
| `src/mes_dashboard/routes/hold_history_routes.py` | modify | IP-2. Add 4 `HOLD_*` module constants (read env at import). Insert async branch in `api_hold_history_query()` between validation and the `execute_primary_query` try-block; build a `params` dict identical to the sync call kwargs (`start_date`, `end_date`, `hold_type`, `record_type`). Use `get_owner_token()` for owner. Do not alter the sync branch. |
| `src/mes_dashboard/app.py` | modify | IP-3. Add hold job-service import beside downtime import (~line 893). |
| `src/mes_dashboard/services/rq_monitor_service.py` | modify | IP-4. Append `os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")` to `_QUEUE_NAMES` (~line 30). |
| `deploy/mes-dashboard-hold-history-worker.service` | create | IP-5. Clone downtime unit; `HOLD_WORKER_QUEUE` / `HOLD_JOB_TIMEOUT_SECONDS`; new SyslogIdentifier. |
| `frontend/src/hold-history/` (App + composable usage) | modify | IP-6. 202 branch + polling + `AsyncQueryProgress` + LoadingOverlay suppression (css-contract Rule 4.6). Template: `frontend/src/downtime-analysis/`. |
| `contracts/env/env-contract.md` | modify | IP-7. Add 4 `HOLD_*` rows mirroring DOWNTIME_* (lines 112-120) with pinned defaults + per-var prose; note module-level constant ⇒ restart required. |
| `.env.example` | modify | IP-7. Add `HOLD_ASYNC_ENABLED=true`, `HOLD_ASYNC_DAY_THRESHOLD=90`, `HOLD_WORKER_QUEUE=hold-history-query`, `HOLD_JOB_TIMEOUT_SECONDS=1800` near the DOWNTIME_* block (~line 204). |
| `contracts/api/api-contract.md`, `contracts/api/api-inventory.md` | modify | IP-7. Document the 202 async response on `POST /api/hold-history/query` (`{async, job_id, status_url}`); note sync 200 shape unchanged. |
| `contracts/ci/ci-gate-contract.md` | modify | IP-7. Register `hold-history-query` RQ queue + worker unit; add `§hold-history-rq-async` Gate Compatibility Note (e2e job + `playwright install --with-deps chromium`). |
| `tests/test_hold_history_routes.py` | modify | IP-8. Add 202/200 branch + env-default + per-kwarg forwarding + redis-down fallback tests; extend `test_query_success`. |
| `tests/integration/test_hold_history_rq_async.py` | create | IP-8. Mirror `tests/integration/test_downtime_rq_async.py`; `pytestmark = pytest.mark.integration_real`; parity, per-chunk milestone ordering, dispatch, resilience. |
| `tests/e2e/test_hold_history_e2e.py` | modify | IP-8. Add long-range 202+job_id test; extend short-range sync test. |
| `frontend/tests/playwright/hold-history-flat-table.spec.js` | modify | IP-8. Long-range → progress bar → result; short-range → 200 unchanged. |
| `tests/test_rq_monitor_service.py` | modify | IP-8. Parametrize/assert the hold queue is enumerated. |

## Contract Updates

- API: `contracts/api/api-contract.md` + `contracts/api/api-inventory.md` — add 202 async response `{async: true, job_id, status_url: "/api/job/{id}?prefix=hold-history"}` for `POST /api/hold-history/query`; sync 200 payload unchanged (Clarification 1: async envelope identical to sync — if it ever diverges, escalate data-shape contract to required).
- CSS/UI: none new. Reuse `AsyncQueryProgress.vue`; enforce css-contract Rule 4.6 LoadingOverlay suppression.
- Env: `contracts/env/env-contract.md` + `.env.example` — 4 `HOLD_*` vars, pinned defaults `true / 90 / hold-history-query / 1800`. Mark module-level (restart required).
- Data shape: `contracts/data/data-shape-contract.md` — no change expected (parity assumption); touch only if envelope diverges.
- Business logic: none — threshold gating is operational config, not a domain rule.
- CI/CD: `contracts/ci/ci-gate-contract.md` — new `hold-history-query` queue + `mes-dashboard-hold-history-worker.service`; `§hold-history-rq-async` Gate Compatibility Note for the e2e job.

## Test Execution Plan

Required test phases for this change: `collect`, `targeted`, `changed-area` (always), plus `contract` (env/api/ci contracts touched) and `quality` (lint/css/type). Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. Gate commands live in `ci-gates.md` — do not restate them here.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_long_range_returns_202` | range ≥ threshold + enabled ⇒ HTTP 202 |
| AC-1 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_202_response_has_job_id` | 202 body has `job_id` + `status_url` |
| AC-2 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_short_range_returns_200_sync` | range < threshold ⇒ HTTP 200 sync payload |
| AC-2 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_async_flag_false_returns_200_sync` | flag off ⇒ HTTP 200 sync |
| AC-3 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_worker_fn_parity_vs_sync` | worker result row/field parity vs sync |
| AC-3 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_passes_params` | per-kwarg forwarding (use `call_args.kwargs[...]`) |
| AC-4 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_per_chunk_pct_milestones_fire_in_order` | pct sequence non-decreasing, first ≤ 5, last == 100 |
| AC-4 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_pct_envelope_never_decreases` | pct monotonic non-decreasing |
| AC-5 | `frontend/tests/playwright/hold-history-flat-table.spec.js` | long-range → AsyncQueryProgress renders → correct result; short-range → 200 sync |
| AC-5 | `tests/e2e/test_hold_history_e2e.py::TestHoldHistoryQuery::test_long_range_returns_202_and_job_id` | long-range HTTP 202 + job_id end-to-end |
| AC-6 | `tests/test_hold_history_routes.py::TestHoldHistoryConfigRoute::test_config_has_hold_async_keys` | config exposes hold async keys |
| AC-6 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_hold_async_enabled_default_is_true` | default True (monkeypatch.setattr) |
| AC-6 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_hold_async_day_threshold_default_is_90` | default 90 |
| AC-6 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_hold_worker_queue_default_is_hold_history_query` | queue default `hold-history-query` |
| AC-6 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_hold_job_timeout_default_is_1800` | timeout default 1800 |
| AC-7 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_enqueue_to_hold_history_queue` | dispatch routes to hold queue |
| AC-7 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_enqueue_payload_contains_owner_and_params` | enqueue payload has owner + params |
| AC-7 | `tests/test_rq_monitor_service.py` | hold queue enumerated in `_QUEUE_NAMES` |
| AC-8 | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_worker_fn_failure_does_not_call_complete_job` | worker exception → `complete_job(error=...)` + reraise, no false success |
| AC-8 | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_redis_down_falls_back_to_sync` | `is_async_available()` False ⇒ sync 200 |
| AC-8 | `cdd-kit validate` | all contracts pass |

(`cdd-kit test select` falls back to this table when test-plan.md has no mapping. Required floor: collect, targeted, changed-area; full ladder in test-plan.md / references/sdd-tdd-policy.md.)

Test mechanics (from test-plan.md Notes — do not re-derive):
- Patch module-level constants with `monkeypatch.setattr('mes_dashboard.services.hold_query_job_service.HOLD_ASYNC_ENABLED', ...)` (and route-module constants for route tests); `os.environ` patching has no effect post-import.
- `register_job_type()` is a module-level side effect: to re-test registration after clearing the registry, use `importlib.reload()` on the job-service module — `setattr` alone does not re-run it.
- `tests/integration/` `pytestmark` must be `pytest.mark.integration_real` — verify before adding mock tests there.
- Route forwarding: assert per-kwarg via `call_args.kwargs[key]` with non-default values, not `assert_called_once_with()`.

## Handoff Constraints

- Do NOT modify `execute_primary_query()` (or `apply_view`, `hold_history_sql_runtime`, `batch_query_engine`, SQL files) — wrap only. No new `progress_callback` parameter.
- Worker fn MUST call `register_job_type(JobTypeConfig(job_type="hold-history", queue_name=HOLD_WORKER_QUEUE, worker_fn=execute_hold_history_query_job, ...))` at module level; `app.py` imports the module at startup (IP-3) so registration fires before any request.
- Module-level constants `HOLD_ASYNC_ENABLED`, `HOLD_ASYNC_DAY_THRESHOLD`, `HOLD_WORKER_QUEUE`, `HOLD_JOB_TIMEOUT_SECONDS` live in `hold_history_routes.py` (route gate) AND in `hold_query_job_service.py` (the `should_use_async` gate + registry config). Mirror the `downtime_analysis_routes.py` constant pattern.
- `rq_monitor_service._QUEUE_NAMES` MUST include `os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")`.
- Async dispatch MUST be gated by `is_async_available()` and MUST fall through to the unchanged sync 200 path on any enqueue failure / precondition miss (no error surfaced to the user for a degradable async failure).
- Frontend: use `frontend/src/downtime-analysis/` as the 202-branch template; suppress LoadingOverlay while `asyncJobProgress.active` (css-contract Rule 4.6).
- Env defaults are exact and contract-pinned: `true / 90 / hold-history-query / 1800`.
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- **Per-chunk milestone wiring (AC-4) is the one non-obvious point.** `execute_primary_query()` computes `engine_hash` internally and does NOT return it, and per the constraint it must not be modified to accept a `progress_callback`. The engine writes live per-chunk progress to Redis under `("hold", engine_hash)` via `_update_progress`/`get_batch_progress` (`batch_query_engine.py:255,295`), but the worker cannot read it without `engine_hash`. Two acceptable implementations for the worker — backend-engineer chooses and documents in the worker docstring:
  1. **Coarse bracket (lowest risk, recommended):** emit `pct=5` (started) → `pct=15` (querying, before the call) → `pct=90` (after `execute_primary_query` returns) → `pct=100` (complete). Use the incremental fallback formula from the task brief if intermediate steps are desired: start at 15, cap at 90 until done. AC-4 asserts ordering (non-decreasing, first ≤ 5, last == 100), which this satisfies; the integration test fixture must simulate chunk progression at the milestone-emission boundary.
  2. **Hash-mirroring poll (true per-chunk):** the worker recomputes the engine hash by mirroring `compute_query_hash({"start_date", "end_date", "mode": "row_count", "total_rows": ...})` (`hold_dataset_cache.py:186-189`) and polls `get_batch_progress("hold", engine_hash)` from a background thread, mapping `completed/total` onto `pct = 5 + (completed/total)*85`. This is brittle: the hash recipe is coupled to `execute_primary_query` internals and would silently desync if that recipe changes. Only choose this if AC-4 reviewers require genuine per-chunk granularity; pin the hash recipe with a membership/equality test if so.
- Parity (AC-3): the async worker must produce a result identical to the sync path. The single-chunk open-hold escape branch (`RELEASETXNDATE IS NULL`) means the integration fixture must include open-hold rows; assert row-count + field parity (test-plan.md AC-3).
- `tests/integration/test_hold_history_rq_async.py` runs only in the nightly `integration_real` gate (ci-gates.md Nightly Gates) — AC-3/AC-4/AC-7 integration coverage is NOT enforced pre-merge; the PR-tier unit + e2e gates carry merge eligibility. Triage nightly failures within 1 business day.
- `.cdd/code-map.yml` placed `execute_primary_query` in `hold_dataset_cache.py` (not `hold_history_service.py` as the kickoff brief implied); the brief's import path was corrected here after reading the source. Map otherwise current.
- The `src/mes_dashboard/workers/` directory referenced in the context manifest contains no per-queue entry files; worker registration is via systemd unit (`deploy/`) + `app.py` import + `rq_worker_preload`. No new file is needed under `workers/`.
