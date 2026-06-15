---
change-id: resource-history-rq-async
schema-version: 0.1.0
last-changed: 2026-06-15
---

# Implementation Plan: resource-history-rq-async

## Objective
Add a threshold-gated async (RQ) execution path to `POST /api/resource/history/query` (note the real url_prefix is `/api/resource/history`, not `/api/resource-history`). Day-span ≥ threshold returns HTTP 202 `{async:true, job_id, status_url}`; a dedicated `resource-history-query` RQ worker runs the unmodified `resource_dataset_cache.execute_primary_query()` (Oracle → Parquet spool); the frontend polls via `useAsyncJobPolling.ts`, reads top-level `query_id`, sets `queryId`, calls `refreshView()`. Short-span / flag-off / Redis-down keep the existing sync 200 path byte-for-byte. Architecture is decided in `design.md`; mirror the shipped `hold-history-rq-async` exactly.

## Execution Scope

### In Scope
- New `src/mes_dashboard/services/resource_query_job_service.py` (mirror `hold_query_job_service.py`).
- Async dispatch branch + 4 `RESOURCE_*` module constants in `resource_history_routes.py::api_resource_history_query`.
- Startup import in `app.py`; `RESOURCE_WORKER_QUEUE` appended to `rq_monitor_service._QUEUE_NAMES`.
- Worker registration in `scripts/start_server.sh` AND `supervisord.conf` AND `deploy/` systemd unit.
- Frontend 202 polling in `frontend/src/resource-history/App.vue` (reuse `useAsyncJobPolling.ts`).
- Contracts: api-contract, api-inventory, env-contract, business-rules, CHANGELOG, `.env.example`.
- Tests per `test-plan.md`; e2e spec; stress extension; CI Playwright install step.

### Out of Scope
- `execute_primary_query()` / `apply_view()` internals in `resource_dataset_cache.py` — wrap only; NO `progress_callback`, NO signature/body change.
- New spool namespace — `resource_dataset` already serves both paths and is already in `spool_routes._ALLOWED_NAMESPACES` (design Key Decision 2).
- `data-shape-contract.md` — spool schema identical to sync (parity assumption holds).
- ADR-0003 re-classification — design.md confirms it does NOT apply; no ADR change.
- `AsyncQueryProgress.vue` rework, sync-path refactor, the existing batch `/query/progress` polling path.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend / service | Create `resource_query_job_service.py`: 5 `RESOURCE_*` constants, `should_use_async(params)`, `enqueue_resource_history_query(params, owner)` → `enqueue_job_dynamic("resource-history", owner=owner, params=params)`, `execute_resource_history_query_job(*, job_id, owner, **query_params)` wrapping `execute_primary_query` with coarse milestones 5→15→90→100, module-level `register_job_type(...)`. | backend-engineer |
| IP-2 | backend / route | Add 4 `RESOURCE_*` module constants + 202 dispatch branch in `api_resource_history_query` (before the canonical/Oracle try-block at line 198); `owner` inside `_params`; fall through to sync on any miss/failure. | backend-engineer |
| IP-3 | backend / startup | Add `import mes_dashboard.services.resource_query_job_service  # noqa: F401` beside the existing job-service imports in `app.py`. | backend-engineer |
| IP-4 | backend / monitor | Append `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")` to `rq_monitor_service._QUEUE_NAMES`. | backend-engineer |
| IP-5 | worker registration | Add resource worker to `scripts/start_server.sh` (config + pid/log vars + start/stop/status fns + lifecycle hookup) AND `supervisord.conf` (`[program:worker-resource-history]`) AND clone `deploy/` systemd unit. | backend-engineer / ci-cd-gatekeeper |
| IP-6 | frontend | In `App.vue::executePrimaryQuery`, detect `responseData.async === true` → drive `useAsyncJobPolling.ts` (`prefix=resource-history`) → on completion read top-level `finalStatus.query_id`, set `queryId`, call `refreshView()`. No duplicated polling. | frontend-engineer |
| IP-7 | contracts | Update api-contract + api-inventory (202 + job type), env-contract + `.env.example` (4 vars), business-rules (threshold rule), CHANGELOG. | backend-engineer (env/api/business/changelog), ci-cd-gatekeeper (ci) |
| IP-8 | tests | Author/extend per `test-plan.md` mapping (see Test Execution Plan). | test-strategist / backend-engineer / frontend-engineer |
| IP-9 | e2e | Create `frontend/tests/playwright/resource-history-async.spec.ts`. | e2e-resilience-engineer |
| IP-10 | stress | Extend `tests/stress/test_resource_history_stress.py` (concurrent async-job load, nightly lane). | stress-soak-engineer |
| IP-11 | CI | Add `npx playwright install --with-deps chromium` before the resource-history-async spec in `frontend-tests.yml` `e2e-critical`. | ci-cd-gatekeeper / backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | Key Decision 1 & 2; New Worker Module; Owner-in-params; Worker Process Registration; Migration/Rollback | architecture constraints, signatures, env defaults |
| test-plan.md | Acceptance Criteria → Test Mapping; Test Update Contract; Notes | test files/commands, monkeypatch/milestone mechanics |
| ci-gates.md | Required Gates; Workflow; Rollback Policy; Manual Gates | verification commands, e2e job, worker-registration verify |
| change-classification.md | AC-1..AC-9; Required Contracts | AC scope; contract surface |
| specs/archive/2026/hold-history-rq-async/implementation-plan.md | full file | exact pattern being mirrored |
| src/mes_dashboard/services/hold_query_job_service.py | full file (174 lines) | worker fn + register_job_type template |
| src/mes_dashboard/routes/hold_history_routes.py:216-263 | async branch + fall-through | route 202 dispatch template |
| src/mes_dashboard/routes/resource_history_routes.py:35-41,168-230 | constants + `api_resource_history_query` | insertion site (before try-block @198) |
| src/mes_dashboard/services/resource_dataset_cache.py:178-186,40 | `execute_primary_query` signature + `_REDIS_NAMESPACE="resource_dataset"` | wrap target, namespace confirm |
| frontend/src/hold-history/App.vue:420-466 | 202 branch + `pollJobUntilComplete` + top-level `query_id` + `refreshView()` | frontend template |
| frontend/src/resource-history/App.vue:489-580 | `executePrimaryQuery`, line 528-529 `responseData` | 202-branch insertion site |
| scripts/start_server.sh:52-54,116-117,632-634,1323-1420,1622,1686,1742 | hold-hist worker blocks | clone target lines |
| supervisord.conf:97-110 | `[program:worker-hold-history]` | clone target block |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/resource_query_job_service.py` | create | IP-1. Constants: `RESOURCE_ASYNC_ENABLED` (true), `RESOURCE_ASYNC_DAY_THRESHOLD` (90), `RESOURCE_WORKER_QUEUE` (`resource-history-query`), `RESOURCE_JOB_TIMEOUT_SECONDS` (1800), `RESOURCE_JOB_TTL_SECONDS` (3600). `_JOB_PREFIX="resource-history"`. Import `execute_primary_query` INSIDE the worker fn. Worker call: `execute_primary_query(start_date=query_params["start_date"], end_date=query_params["end_date"], granularity=query_params.get("granularity","day"), **{filter kwargs})` — pass through `workcenter_groups/families/resource_ids/is_production/is_key/is_monitor/package_groups`. Do NOT forward `owner` into `execute_primary_query`. `complete_job(_JOB_PREFIX, job_id, query_id=result["query_id"])`; on exception `complete_job(..., error=str(exc))` then re-raise. |
| `src/mes_dashboard/routes/resource_history_routes.py` | modify | IP-2. Add 4 `RESOURCE_*` module constants (mirror hold lines 63+) and `is_async_available`/`enqueue_job_dynamic`/`get_owner_token` imports. Insert async branch in `api_resource_history_query` after `filters = _parse_resource_filters(body)` (line 196) and before the `try:` at 198. Build `_params = dict(owner=_owner, start_date=..., end_date=..., granularity=..., **filters)`; return `success_response({"async":True,"job_id":job_id,"status_url":f"/api/job/{job_id}?prefix=resource-history"}, status_code=202)`. Do not alter sync branch. |
| `src/mes_dashboard/app.py` | modify | IP-3. Add resource job-service import beside existing job-service imports. |
| `src/mes_dashboard/services/rq_monitor_service.py` | modify | IP-4. Append `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")` to `_QUEUE_NAMES`. |
| `scripts/start_server.sh` | modify | IP-5. Clone every `RQ_HOLD_HIST_WORKER_*` block → `RQ_RESOURCE_WORKER_*` (config 52-54 with `RQ_RESOURCE_WORKER_QUEUE="${RESOURCE_WORKER_QUEUE:-resource-history-query}"`; pid/log 116-117; rotation 632-634/652; `start/stop/status` fns 1323-1420 with `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`; lifecycle calls at 1622/1686/1742). |
| `supervisord.conf` | modify | IP-5. Add `[program:worker-resource-history]` cloning lines 97-110; `command=rq worker %(ENV_RESOURCE_WORKER_QUEUE)s --url %(ENV_REDIS_URL)s`. |
| `deploy/` systemd unit | create | IP-5. Clone the hold-history worker unit → resource unit; `RESOURCE_WORKER_QUEUE` / `RESOURCE_JOB_TIMEOUT_SECONDS`; new SyslogIdentifier `mes-dashboard-resource-history-worker`. |
| `frontend/src/resource-history/App.vue` | modify | IP-6. In `executePrimaryQuery`, after `responseData` (line 529) branch on `responseData.async === true`: poll via `pollJobUntilComplete(statusUrl, ...)`, on success set `queryId.value = String(finalStatus.query_id)`, then `await refreshView()` (do NOT parse spool/DuckDB eligibility from job metadata — `refreshView` handles it). Reuse existing progress/loading state pattern from hold-history App.vue:420-466. |
| `contracts/api/api-contract.md`, `contracts/api/api-inventory.md` | modify | IP-7. 202 async response `{async, job_id, status_url:"/api/job/{id}?prefix=resource-history"}` on `POST /api/resource/history/query`; register `resource-history` job type / `resource-history-query` queue; sync 200 unchanged. |
| `contracts/env/env-contract.md`, `.env.example` | modify | IP-7. 4 `RESOURCE_*` rows + values `true/90/resource-history-query/1800`; mark module-level (restart required). |
| `contracts/business/business-rules.md` | modify | IP-7. Async-threshold day-span rule for resource-history (per classification Required Contracts). |
| `contracts/CHANGELOG.md` | modify | IP-7. Version entry (changelog only — `validate --versions` checks here). |
| `tests/test_resource_history_routes.py` | modify | IP-8. 202/200 branch, env-default (monkeypatch.setattr), redis-down fallback; extend `test_successful_query`. |
| `tests/unit/test_resource_query_job_service.py` | create | IP-8. `should_use_async` boundary; worker failure re-raises + sets error. |
| `tests/integration/test_resource_history_rq_async.py` | create | IP-8. `pytestmark = pytest.mark.integration_real`; parity, milestone ordering, dispatch, owner-in-params, queue/timeout defaults, timeout terminal status. Mirror `test_hold_history_rq_async.py`. |
| `tests/test_env_contract.py` | modify | IP-8. `test_resource_async_env_vars_pinned_defaults`. |
| `tests/test_api_contract.py` | modify | IP-8. `TestResourceHistoryAsyncContract` 202 shape. |
| `tests/test_spool_routes.py` | modify | IP-8. `test_resource_dataset_stays_in_allowed_namespaces` (regression; no new entry). |
| `frontend/tests/playwright/resource-history-async.spec.ts` | create | IP-9. long-span → progress → result; short-span → 200 sync. |
| `tests/stress/test_resource_history_stress.py` | modify | IP-10. concurrent async-job load (nightly). |
| `.github/workflows/frontend-tests.yml` | modify | IP-11. `npx playwright install --with-deps chromium` before resource-history-async spec. |

## Contract Updates
- API: api-contract.md + api-inventory.md — 202 async response on `POST /api/resource/history/query`; register `resource-history` job type + `resource-history-query` queue; sync 200 unchanged.
- CSS/UI: none — reuse `AsyncQueryProgress.vue`.
- Env: env-contract.md + `.env.example` — `RESOURCE_ASYNC_ENABLED=true`, `RESOURCE_ASYNC_DAY_THRESHOLD=90`, `RESOURCE_WORKER_QUEUE=resource-history-query`, `RESOURCE_JOB_TIMEOUT_SECONDS=1800` (module-level ⇒ restart required).
- Data shape: no change (parity assumption — touch only if spool envelope diverges).
- Business logic: business-rules.md — resource-history async-threshold day-span rule.
- CI/CD: ci-gate-contract.md (if touched) — new queue + worker unit + Playwright install step note.

## Test Execution Plan
Required test phases: `collect`, `targeted`, `changed-area` (always), plus `contract` (env/api/business contracts touched) and `quality` (lint/css/type). Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. Gate commands live in `ci-gates.md` — do not restate.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_long_span_returns_202` | span ≥ threshold + enabled ⇒ 202 |
| AC-1 | `tests/test_api_contract.py::TestResourceHistoryAsyncContract::test_202_response_shape_has_job_id_and_status_url` | 202 body has job_id + status_url |
| AC-2 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_short_span_returns_200_sync` | span < threshold ⇒ 200 sync |
| AC-2 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_async_flag_false_returns_200_sync` | flag off ⇒ 200 sync |
| AC-3 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_worker_fn_parity_vs_sync` | worker result row/field parity vs sync |
| AC-3 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_coarse_milestones_fire_in_order` | non-decreasing, first ≤ 5, last == 100 |
| AC-3 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_pct_envelope_never_decreases` | pct monotonic |
| AC-4 | `frontend/tests/playwright/resource-history-async.spec.ts` | long-span → progress → result; short-span → 200 |
| AC-5 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_resource_async_enabled_default_is_true` | default True |
| AC-5 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_resource_async_day_threshold_default_is_90` | default 90 |
| AC-5 | `tests/test_env_contract.py::test_resource_async_env_vars_pinned_defaults` | 4 vars exact defaults |
| AC-5 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_resource_worker_queue_default_is_resource_history_query` | queue default `resource-history-query` |
| AC-5 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_resource_job_timeout_default_is_1800` | timeout default 1800 |
| AC-6 | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_redis_unavailable_falls_back_to_sync` | `is_async_available()` False ⇒ 200 sync |
| AC-6 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_worker_exception_calls_complete_job_with_error` | exception ⇒ `complete_job(error=...)` + reraise |
| AC-7 | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_should_use_async_above_threshold` | True above threshold |
| AC-7 | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_should_use_async_below_threshold_is_false` | False below threshold |
| AC-7 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_enqueue_to_resource_history_queue` | dispatch routes to resource queue |
| AC-7 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_enqueue_payload_owner_inside_params_dict` | `call_args.kwargs["params"]["owner"]` set |
| AC-8 | `tests/test_spool_routes.py::test_resource_dataset_stays_in_allowed_namespaces` | `resource_dataset` still in allowlist |
| AC-9 | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_job_timeout_produces_terminal_error_status` | timeout ⇒ terminal error status |
| AC-9 | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_worker_fn_failure_reraises_and_sets_error` | failure re-raises + sets error |

Test mechanics (from test-plan.md Notes — do not re-derive):
- Patch module-level constants via `monkeypatch.setattr('mes_dashboard.services.resource_query_job_service.RESOURCE_ASYNC_ENABLED', ...)` (and route-module constants for route tests); `os.environ` patching has no effect post-import.
- `register_job_type()` is a module-level side effect: re-test registration with `importlib.reload()` after clearing the registry — `setattr` alone does not re-run it.
- `tests/integration/` `pytestmark` MUST be `pytest.mark.integration_real` — verify before adding mock-only tests there.
- Route forwarding: assert per-kwarg via `call_args.kwargs[key]` with non-default values.
- Milestone test: sequence non-decreasing, first ≤ 5, last == 100.

## Handoff Constraints
- Do NOT modify `execute_primary_query()` / `apply_view()` / SQL — wrap only; no `progress_callback`.
- `owner` MUST be inside the `_params` dict passed to `enqueue_job_dynamic` (not only the separate `owner=` kwarg) — `enqueue_job` forwards only `kwargs` to the worker; the worker signature requires `owner=`. Pin with `call_args.kwargs["params"]["owner"]` (AC-7).
- Worker MUST be registered in BOTH `scripts/start_server.sh` AND `supervisord.conf` (AND the `deploy/` systemd unit) — missing registration caused the hold-history >120s timeout bug.
- Frontend MUST read `finalStatus.query_id` at top level (NOT `finalStatus.result?.query_id`), then call `refreshView()` — do not parse spool/DuckDB eligibility from job metadata.
- Async dispatch gated by `is_async_available()`; fall through to unchanged sync 200 on any enqueue failure / precondition miss (no user-facing error for a degradable async miss).
- `rq_monitor_service._QUEUE_NAMES` MUST include `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")` (manual gate `worker-registration-verify`).
- Env defaults are exact and contract-pinned: `true / 90 / resource-history-query / 1800`.
- Real url_prefix is `/api/resource/history` — all route/spec/contract paths must use it.
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI, or contract prose; follow the pointers above.
- If this plan omits a required file/behavior/contract/test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks
- Worker DB pool sizing: resource queries fan out base+OEE in `ThreadPoolExecutor(max_workers=2)` while start_server worker blocks pin `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1` — confirm the worker pool tolerates the fan-out (stress-soak evidence required, design Open Risks).
- `RESOURCE_JOB_TIMEOUT_SECONDS` must be < spool TTL so `/view` finds the spool after long-range jobs complete near TTL (design Open Risks).
- Integration tests (`test_resource_history_rq_async.py`) run only in the nightly `integration_real` gate — AC-3/AC-5/AC-6/AC-7/AC-9 integration coverage is NOT enforced pre-merge; merge eligibility rests on PR-tier unit + e2e gates. Triage nightly failures within 1 business day.
- The existing batch `/query/progress` polling path in `App.vue` (line 135, 533-544) is separate from the new RQ 202 path; the 202 branch must short-circuit before the `isBatch` heuristic so the two polling mechanisms do not collide.
