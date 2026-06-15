# Change Classification

## Change Types
- primary: feature-add (backend async query path)
- secondary: api-contract-change, env-change, business-logic-change (threshold rule), ci-cd-change (worker process registration / deployment config), frontend-integration

## Lane
- feature

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: A design decision is required on whether the async worker preserves `BatchQueryEngine` row-count chunking or switches to single-pass Oracle + Parquet spool. ADR 0003 (`docs/adr/0003-downtime-rowcount-chunking-exclusion.md`) explicitly flags that `ROW_NUMBER()` chunking is incompatible with cross-row reductions and must be classified at design time. This also introduces a new long-running worker process (operational/rollback risk), a new env-var contract surface, and a canonical-spool key decision. These are module-boundary, data-flow, and operational-risk decisions that require `spec-architect` to produce `design.md` before `implementation-planner` runs.

## Required Artifacts

The following 7 artifacts are always required for implementation changes:
`change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing sync path behavior fits inside design.md / implementation-plan.md; no separate product investigation needed |
| proposal.md | no | Pattern already decided (mirror hold-history-rq-async); no user-facing product decision to litigate |
| spec.md | no | No new user-facing behavior spec beyond the async-threshold rule, which lives in business-rules contract |
| design.md | yes | Architecture Review Required = yes (chunking vs single-pass, worker process, canonical-spool key, rollback) — spec-architect must decide before planning |
| qa-report.md | no | Routine pass/fail evidence goes to agent-log/qa-reviewer.yml unless blocking/approved-with-risk findings arise |
| regression-report.md | no | Sync short-span path is unchanged-by-design; regression evidence captured via tests + agent-log unless a regression is found |
| visual-review-report.md | no | No UI redesign; only an async progress/polling state reusing existing shared components |
| monkey-test-report.md | no | Not a fuzz-target change |
| stress-soak-report.md | yes | New long-running RQ worker + Oracle async path is exactly the high-load / long-running-job class that requires durable stress/soak evidence (matches hold-history/downtime async precedent) |

## Required Contracts
- API: `contracts/api/api-contract.md` — add 202 async response shape for the resource-history POST query endpoint and job-status/view contract; `contracts/api/api-inventory.md` — register resource-history async worker job type
- CSS/UI: none (reuse existing shared async-progress components)
- Env: `contracts/env/env-contract.md` — add `RESOURCE_ASYNC_ENABLED`, `RESOURCE_ASYNC_DAY_THRESHOLD`, `RESOURCE_WORKER_QUEUE` (default `"resource-history-query"`), `RESOURCE_JOB_TIMEOUT_SECONDS`; sync `.env.example` and `env.schema.json`
- Data shape: conditional — only if async Parquet spool schema diverges from sync response; `contracts/data/data-shape-contract.md`
- Business logic: `contracts/business/business-rules.md` — async-threshold day-span rule for resource-history
- CI/CD: `contracts/ci/ci-gate-contract.md` — only if a new worker test gate / Playwright spec install step is added

## Required Tests
- unit: route async/sync branch selection at threshold boundary; `resource_query_job_service` worker function (Oracle query + Parquet spool) with mocked Oracle; module-level constant overrides via `monkeypatch.setattr`; env-var defaults pinned (not just presence)
- contract: `tests/test_api_contract.py` — 202 async response shape and status/view contract; env-contract test asserting the four new vars + default values
- integration: `tests/integration/test_resource_history_rq_async.py` (new, mirroring `test_hold_history_rq_async.py`) — enqueue → poll → view round trip; `owner` carried inside `_params` dict; multi-worker behavior
- E2E: Playwright spec for long-span async query; extend resource-history e2e for the 202 polling path
- visual: none
- data-boundary: Parquet spool malformed/empty-result boundary for the async path
- resilience: worker crash / job timeout / Redis unavailable → fallback or clear error; `RESOURCE_JOB_TIMEOUT_SECONDS` enforcement
- fuzz/monkey: none
- stress: extend `tests/stress/test_resource_history_stress.py` for concurrent async-job load
- soak: long-running worker soak (nightly/weekly lane, not pre-merge)

## Required Agents
1. spec-architect — decide chunking vs single-pass, canonical-spool key reuse, worker-process topology, rollback runbook; author `design.md`
2. test-strategist — map acceptance criteria to tests; ensure boundary/resilience/contract coverage
3. ci-cd-gatekeeper — verify worker registration, any new Playwright install step, and gate readiness; author `ci-gates.md`
4. contract-reviewer — verify api/env/api-inventory/business contract edits, changelog version bump, `.env.example` sync
5. implementation-planner — turn design + contracts + test plan into execution packet; author `implementation-plan.md`
6. backend-engineer — implement route async branch, `resource_query_job_service` worker, env constants, worker registration in `scripts/start_server.sh` AND `supervisord.conf`
7. frontend-engineer — wire 202 polling path in `frontend/src/resource-history/` reusing `useAsyncJobPolling.ts`
8. e2e-resilience-engineer — async-path E2E plus worker-crash / timeout / Redis-fault resilience tests
9. stress-soak-engineer — concurrent async-job stress + long-running worker soak evidence; author `stress-soak-report.md`
10. qa-reviewer — release-readiness sign-off and regression scope for the unchanged sync path

## Inferred Acceptance Criteria
- AC-1: A POST resource-history query whose day span is ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` returns HTTP 202 with `{async: true, job_id, status_url}` when `is_async_available()` is true.
- AC-2: A POST resource-history query whose day span is below the threshold continues to return the existing synchronous 200 response with unchanged payload shape.
- AC-3: The async worker (`resource_query_job_service`) executes the Oracle query and writes a Parquet spool, and the resulting `/view` call returns the same row data the sync path would have produced for the same parameters.
- AC-4: Frontend, on receiving 202, polls job status via the shared `useAsyncJobPolling` composable, reads `query_id` from the top-level final status, sets `queryId`, and renders results via `refreshView()` without a duplicated polling implementation.
- AC-5: The four new env vars (`RESOURCE_ASYNC_ENABLED`, `RESOURCE_ASYNC_DAY_THRESHOLD`, `RESOURCE_WORKER_QUEUE` default `"resource-history-query"`, `RESOURCE_JOB_TIMEOUT_SECONDS`) are defined in the env contract, present in `.env.example`, validated by schema, and their default values are pinned by tests.
- AC-6: When `RESOURCE_ASYNC_ENABLED` is false (or `is_async_available()` is false), all queries fall back to the synchronous path regardless of span.
- AC-7: The `owner` value is included inside the `_params` dict passed to `enqueue_job_dynamic` (not only as a kwarg), so job ownership/authorization is preserved.
- AC-8: The new RQ worker queue is registered in both `scripts/start_server.sh` and `supervisord.conf` (and the deploy systemd unit if applicable), so the worker starts in every deployment topology.
- AC-9: Job timeout (`RESOURCE_JOB_TIMEOUT_SECONDS`) and worker/Redis failure produce a clear terminal job status / error response, not an indefinite poll.

## Tasks Not Applicable
- not-applicable: (none — design review is required, so task 1.3 applies)

## Clarifications or Assumptions
- Assumption: This change mirrors the completed `hold-history-rq-async` architecture exactly (202 enqueue → poll → /view), so no new product behavior decision is needed beyond the chunking-vs-single-pass design choice.
- Assumption: The Parquet spool reuses the existing resource-history result schema, so `data-shape-contract.md` is conditional. If design (spec-architect) finds the spool schema diverges, promote the data contract to required.
- Open design question for spec-architect: preserve `BatchQueryEngine` `ROW_NUMBER()` chunking in the worker, or switch to single-pass — ADR 0003 flags chunking incompatible with cross-row reductions; this must be resolved before planning.
- Open design question: confirm canonical-spool key reuse vs new namespace against the `spool_routes._ALLOWED_NAMESPACES` discipline (add namespace AND parametrize test in the same PR).
- Path uncertainty: exact route module (`resource_history_routes.py` vs `resource_routes.py`) and async service module name are unconfirmed — see CER-001 and CER-002 in context-manifest.md.

## Context Manifest Draft
(Copied verbatim to context-manifest.md — see that file.)
