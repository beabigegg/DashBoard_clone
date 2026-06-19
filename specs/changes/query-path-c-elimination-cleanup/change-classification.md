# Change Classification

## Change Types
- primary: refactoring
- secondary: cleanup, contract, config

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: Changes synchronous gunicorn-blocking Path (C) to RQ async dispatch for `query_tool_routes` and `wip_routes`; redefines `global_concurrency` semaphore semantics from "protect sync path" to "limit RQ Oracle concurrency". These are concurrency, data-flow, and operational-risk decisions that must be settled in `design.md` before implementation. Confirmed 4 ASYNC_DAY_THRESHOLD vars (not 7 as estimated in change-request); env removal integration with deprecate-2-minors policy needs design guidance. `enqueue_query_job` is in `async_query_job_service.py` (no rq_utils.py).

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Path (C) sync-blocking behavior and the 4 confirmed ASYNC_DAY_THRESHOLD vars need precise pre-change inventory to anchor regression scope. |
| proposal.md | no | |
| spec.md | no | |
| design.md | yes | Architecture Review Required = yes; concurrency, semaphore semantics, RQ job-type reuse, env-removal rollback. |
| qa-report.md | no | |
| regression-report.md | yes | Sync→async dispatch + semaphore repurpose + env removal is high-regression-risk; durable parity evidence required. |
| visual-review-report.md | no | |
| monkey-test-report.md | no | |
| stress-soak-report.md | yes | RQ Oracle-concurrency semaphore repurpose under load requires stress evidence (no gunicorn worker starvation; bounded Oracle concurrency). |

## Required Contracts
- API: contracts/api/api-contract.md (202+job_id async-dispatch shape for query_tool under QUERY_TOOL_USE_RQ=on; rowcount pre-check for oversized wip; flag-gated behavior)
- CSS/UI: none
- Env: contracts/env/env-contract.md (remove 4 deprecated ASYNC_DAY_THRESHOLD vars; add QUERY_TOOL_USE_RQ flag; update global_concurrency semantics note), contracts/env/env.schema.json, contracts/env/.env.example.template, .env.example
- Data shape: none
- Business logic: contracts/business/business-rules.md (cost-threshold routing rule; global_concurrency semaphore semantics; merge_chunks deprecation / no-new-callers rule)
- CI/CD: contracts/ci/ci-gate-contract.md (CI env-var removal sync)

## Required Tests
- unit: tests/test_batch_query_engine.py (DeprecationWarning emitted, backward compat), query_tool_routes dispatch threshold unit test, wip_routes rowcount pre-check unit test, query_cost_policy L3 threshold wiring
- contract: tests/contract/ env-pin tests for removed vars (absence) and QUERY_TOOL_USE_RQ (default off)
- integration: tests/integration/ RQ async dispatch integration test for query_tool (flag on/off parity); worker-blocking-elimination check
- E2E: tests/e2e/test_query_tool_e2e.py, tests/e2e/test_wip_hold_pages_e2e.py (small query stays inline; flag-off behavior unchanged)
- visual: none
- data-boundary: none
- resilience: tests/integration/ flag-off no-regression; Oracle-concurrency bound validation
- fuzz/monkey: none
- stress: tests/stress/ RQ Oracle-concurrency bound, no sync worker starvation under load
- soak: none

## Required Agents
- spec-architect (design.md)
- implementation-planner
- backend-engineer
- contract-reviewer
- test-strategist
- stress-soak-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: When `QUERY_TOOL_USE_RQ=on` and query cost > classify_query_cost threshold, query_tool_routes returns 202 + job_id and enqueues RQ job instead of blocking gunicorn worker up to 300s.
- AC-2: When `QUERY_TOOL_USE_RQ=off` (default), query_tool_routes behaves exactly as before — verified by parity test.
- AC-3: wip_routes performs rowcount pre-check; queries at or above L3 (200,000 rows) route to RQ; sub-L3 WIP queries return inline.
- AC-4: batch_query_engine.merge_chunks is marked @deprecated, emits DeprecationWarning, carries "no new callers" docstring; existing callers remain backward compatible.
- AC-5: All 4 confirmed ASYNC_DAY_THRESHOLD vars (DOWNTIME_, HOLD_, RESOURCE_, REJECT_) are removed from routes, services, .env.example, env-contract.md, env.schema.json; routes read from classify_query_cost / CostPolicy uniformly.
- AC-6: global_concurrency semaphore contract updated to "limit RQ Oracle concurrency" (not "protect sync path"); runtime behavior matches new semantics.
- AC-7: Contract tests pin absence of removed vars and presence + default (off) of QUERY_TOOL_USE_RQ.
- AC-8: Under stress load, no gunicorn worker is blocked beyond cost threshold on oversized queries; RQ Oracle concurrency stays within semaphore bound.

## Tasks Not Applicable
- not-applicable: 2.2, 3.4, 5.1, 5.2

## Clarifications or Assumptions
- CER-001 RESOLVED: no `rq_utils.py`; enqueue_query_job is in `async_query_job_service.py` (already in allowed paths).
- CER-002 RESOLVED: confirmed 4 vars (not 7) — DOWNTIME_, HOLD_, RESOURCE_, REJECT_ASYNC_DAY_THRESHOLD; in routes/downtime_analysis_routes, hold_history_routes, resource_history_routes and services/hold_query_job_service, reject_query_job_service, resource_query_job_service. query_tool and wip routes have no ASYNC_DAY_THRESHOLD vars.
- All 4 removed vars are already marked "Deprecated (removal P5)" in env-contract.md by unified-query-core-infra; this change completes the removal.
- current-behavior.md to be authored by spec-architect as part of design.md preamble or standalone.
- Open question for design.md: whether query_tool_routes reuses an existing generic heavy RQ job type or needs a new job type (affects test_job_registry.py count).

## Context Manifest Draft

### Affected Surfaces
- routes: query_tool_routes.py, wip_routes.py
- routes (ASYNC_DAY_THRESHOLD removal): downtime_analysis_routes.py, hold_history_routes.py, resource_history_routes.py
- services (ASYNC_DAY_THRESHOLD removal): hold_query_job_service.py, reject_query_job_service.py, resource_query_job_service.py
- core: global_concurrency.py, query_cost_policy.py
- service: batch_query_engine.py (deprecation), async_query_job_service.py (RQ dispatch)
- architecture blueprint: docs/architecture/query-dataflow-unification.md

### Allowed Paths
- specs/changes/query-path-c-elimination-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/adr/
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/feature_flags.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- .env.example
- tests/test_batch_query_engine.py
- tests/contract/
- tests/integration/
- tests/e2e/test_query_tool_e2e.py
- tests/e2e/test_wip_hold_pages_e2e.py
- tests/stress/
- tests/test_job_registry.py
- tests/test_query_cost_policy.py
- .github/workflows/backend-tests.yml
- .github/workflows/contract-driven-gates.yml
