---
change-id: job-registry-central
schema-version: 0.1.0
last-changed: 2026-06-13
---

# Implementation Plan: job-registry-central

## Objective
Add a central async-job registry so all RQ job types are declared in one place
and dispatchable by `job_type` string. Deliver: (1) a new `job_registry.py`
module, (2) an additive `enqueue_job_dynamic()` dispatcher in
`async_query_job_service.py`, and (3) exactly one declarative `register_job_type()`
call appended to each of the 8 existing job services. No route, worker,
frontend, contract, or CI change. Full backward compatibility: every existing
`enqueue_xxx()` path stays intact (AC-5).

Scope is fixed by `docs/dynamic-rq-migration-plan.md` §階段二 (sections 2-A,
2-B, 2-C). Reference that document for canonical signatures and the
`job_type` / `queue_name` table — do not re-derive them.

## Execution Scope

### In Scope
- New module `src/mes_dashboard/services/job_registry.py` (AC-1, AC-2): the
  `JobTypeConfig` dataclass, private `_REGISTRY` dict, and `register_job_type`,
  `get_job_type_config`, `list_registered_job_types` functions per migration
  plan §2-A.
- `enqueue_job_dynamic()` added to `async_query_job_service.py` (AC-3) per
  migration plan §2-B; import `job_registry` at top of module.
- One `register_job_type()` call appended at module end of each of the 8 job
  services (AC-4) per migration plan §2-C table.
- New test file `tests/test_job_registry.py` (AC-6) — author per `test-plan.md`
  Acceptance-Criteria→Test mapping (8 test nodes).

### Out of Scope (Non-goals)
- Do not modify any route in `src/mes_dashboard/routes/` — route dispatch stays
  on pre-existing `enqueue_xxx()` calls (AC-5).
- Do not modify `src/mes_dashboard/workers/`.
- Do not modify any existing function in `async_query_job_service.py`
  (`enqueue_job`, `get_job_status`, `update_job_progress`, `complete_job`,
  `is_async_available`, etc.) — only add `enqueue_job_dynamic()` and the import.
- Do not change existing `enqueue_xxx()` / `execute_xxx_job()` logic in any of
  the 8 job services — only append one registration call after all existing
  definitions.
- No new contract files; no edits under `contracts/`.
- No env var, Redis key/schema, or payload changes.
- No frontend or `.github/workflows/` changes.
- Do not opportunistically refactor, rename, or re-order existing code.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend-services | Create `job_registry.py` (JobTypeConfig, _REGISTRY, register/get/list) per migration plan §2-A | backend-engineer |
| IP-2 | backend-services | Add `enqueue_job_dynamic()` + `job_registry` import to `async_query_job_service.py` per §2-B; leave all existing functions untouched | backend-engineer |
| IP-3 | backend-services | Append exactly one `register_job_type()` call to each of the 8 job services per §2-C table | backend-engineer |
| IP-4 | tests | Author `tests/test_job_registry.py` (8 nodes) per test-plan.md; reset `_REGISTRY` per test | backend-engineer |
| IP-5 | verification | Run test ladder + gates; confirm zero regression in `tests/test_async_query_job_service.py` | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| docs/dynamic-rq-migration-plan.md | §階段二 2-A | `job_registry.py` shape (dataclass fields, registry funcs) |
| docs/dynamic-rq-migration-plan.md | §階段二 2-B | `enqueue_job_dynamic()` signature + body |
| docs/dynamic-rq-migration-plan.md | §階段二 2-C table | job_type / queue_name for each of the 8 services |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8 | acceptance scope |
| test-plan.md | Acceptance Criteria → Test Mapping | test node names to author |
| test-plan.md | Test Execution Ladder | required test phases/commands |
| test-plan.md | Notes (registry isolation) | reset `_REGISTRY` per test |
| ci-gates.md | Required Gates table | verification gate commands |
| async_query_job_service.py | `enqueue_job` lines 123-202 | dispatcher delegates here (param names) |
| async_query_job_service.py | constants `ASYNC_JOB_DEFAULT_TTL_SECONDS` (l.31), `ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS` (l.32) | default timeout/ttl precedent |

## File-Level Plan

| path | action | notes |
|---|---|---|
| src/mes_dashboard/services/job_registry.py | create | `JobTypeConfig` dataclass (`job_type`, `queue_name`, `worker_fn`, `timeout_seconds=1800`, `ttl_seconds=3600`, `should_enqueue=None`); private `_REGISTRY` dict; `register_job_type`, `get_job_type_config` (None for unknown), `list_registered_job_types`. Per §2-A. |
| src/mes_dashboard/services/async_query_job_service.py | edit | Add import `from mes_dashboard.services.job_registry import get_job_type_config` (top); add `enqueue_job_dynamic(job_type, owner, params, job_id=None)` returning `(None, "Unknown job type: …")` for unregistered type, honoring `should_enqueue`, else delegating to existing `enqueue_job(...)`. Per §2-B. No other change. |
| src/mes_dashboard/services/reject_query_job_service.py | edit | Append one `register_job_type(...)` at module end: job_type `"reject"`, queue `"reject-query"`. |
| src/mes_dashboard/services/yield_alert_job_service.py | edit | Append one `register_job_type(...)`: job_type `"yield_alert"`, queue `"yield-alert-query"`. |
| src/mes_dashboard/services/production_history_job_service.py | edit | Append one `register_job_type(...)`: job_type `"production_history"`, queue `"production-history-query"`. |
| src/mes_dashboard/services/trace_lineage_job_service.py | edit | Append one `register_job_type(...)`: job_type `"trace-lineage"`, queue `"trace-events"`. |
| src/mes_dashboard/services/msd_seed_job_service.py | edit | Append one `register_job_type(...)`: job_type `"msd-seed"`, queue `"msd-analysis"`. |
| src/mes_dashboard/services/msd_lineage_job_service.py | edit | Append one `register_job_type(...)`: job_type `"msd-lineage"`, queue `"msd-analysis"`. |
| src/mes_dashboard/services/material_consumption_service.py | edit | Append one `register_job_type(...)`: job_type `"material-consumption"`, queue `"material-consumption-detail"`. |
| src/mes_dashboard/services/material_trace_service.py | edit | Append one `register_job_type(...)`: job_type `"material-trace"`, queue `"trace-events"`. |
| tests/test_job_registry.py | create | 8 test nodes per test-plan.md mapping (module exports, register-returns-config, get-unknown-None, list-all, dynamic-dispatch, unregistered-error-tuple, should_enqueue-False, each-service-registers-one). Reset `_REGISTRY` per test. |
| tests/test_async_query_job_service.py | run only | No edits. No-regression run (AC-5/AC-7). |

## Contract Updates

- API: none (routes/dispatch unchanged).
- CSS/UI: none.
- Env: none (no new env var; reuse existing default-timeout/ttl precedent).
- Data shape: none (no Redis/DB schema or payload change).
- Business logic: none (job semantics unchanged; dispatcher is additive lookup).
- CI/CD: none (no workflow file change; `cdd-kit validate` is a gate, not a contract edit).

## Constraints and Ordering Rules

1. Implement IP-1 (`job_registry.py`) first — IP-2 and IP-3 import from it.
2. Implement IP-2 (`enqueue_job_dynamic`) before IP-4 dispatch tests.
3. `worker_fn` in each `register_job_type()` call must reference the service's
   own existing `execute_xxx_job` function (defined above the registration
   line) — append the registration after all existing definitions so the symbol
   is bound. Do not re-import or duplicate the worker function.
4. `job_type` and `queue_name` strings must match the §2-C table exactly
   (note `"yield_alert"` and `"production_history"` use underscores; the rest
   use hyphens; `trace-lineage` and `material-trace` both map to queue
   `"trace-events"`; `msd-seed` and `msd-lineage` both map to `"msd-analysis"`).
5. `register_job_type()` is a module-level side-effect executed on import — tests
   must reset/isolate `_REGISTRY` (test-plan.md Notes) to avoid order-dependence.
6. `get_job_type_config()` returns `None` (not raise) for unknown job_type;
   `enqueue_job_dynamic` returns the `(None, "Unknown job type: …")` tuple in
   that case (AC-3).
7. `should_enqueue=False` path returns `(None, …)` without invoking the queue —
   assert the queue mock is not called (test-plan.md Notes).
8. AC-4 registration test must import all 8 service modules and assert
   `list_registered_job_types()` count == 8 (test-plan.md Notes).
9. Do not modify any existing function body or signature in
   `async_query_job_service.py` (code-map functions at lines 45-333).

## Test Execution Plan

See `test-plan.md` for the authoritative Acceptance-Criteria→Test mapping and
the full Test Execution Ladder. Required floor for this change: `collect`,
`targeted`, `changed-area`; plus `contract` (`cdd-kit validate`). Generate
evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_job_registry.py | module exports + register/get/list pass |
| AC-2 | tests/test_job_registry.py | register-returns-config, get-unknown-None, list-all pass |
| AC-3 | tests/test_job_registry.py | dynamic dispatch, unregistered-error-tuple, should_enqueue=False pass |
| AC-4 | tests/test_job_registry.py | all 8 services register; count == 8 |
| AC-5 | tests/test_async_query_job_service.py | zero regressions |
| AC-6 | tests/test_job_registry.py | all 8 nodes green |
| AC-7 | tests/test_async_query_job_service.py | zero regressions |
| AC-8 | cdd-kit validate | passes |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above (especially migration plan §階段二 for code shape).
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- Misordered registration: appending `register_job_type()` before the
  `execute_xxx_job` definition would raise `NameError` at import. Mitigation:
  constraint 3 (append at module end).
- Shared queue names (`trace-events`, `msd-analysis`) are intentional per §2-C;
  do not "deduplicate" — two distinct job_types may share a queue.
- Underscore vs hyphen mismatch in `job_type` strings is the most likely
  silent error; constraint 4 pins exact values.
- Test order-dependence if `_REGISTRY` is not reset between tests; constraint 5
  / test-plan.md Notes require isolation.
- `.cdd/code-map.yml` lists `enqueue_job` at lines 123-202 but not its full
  inline signature; the dispatcher's delegation arg names (`queue_name`,
  `worker_fn`, `owner`, `job_id`, `kwargs`, `prefix`, `job_timeout`,
  `result_ttl`) are taken from migration plan §2-B. Backend-engineer should
  confirm against `async_query_job_service.py` lines 123-202 before wiring.
