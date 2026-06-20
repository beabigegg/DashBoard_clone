# Change Classification

## Change Types
- primary: feature-add (RQ async worker implementation for WIP detail), refactor (dead-code removal of `merge_chunks`)
- secondary: api-only-change (HTTP 202 async-routing contract for WIP detail must now actually engage)

## Risk Level
- high

## Impact Radius
- cross-module

(`wip_routes.py` → `wip_service.py` / WIP SQL runtime → new `execute_wip_detail_job` + job registry registration → `global_concurrency` slot → RQ infra + deploy service unit. Crosses route/service/worker/core-concurrency boundaries.)

## Tier
- 1

(High risk + cross-module + new concurrency-critical worker with Oracle-bound slot acquisition. RQ workers wiring `acquire_heavy_query_slot` before their `*_USE_RQ` flag goes to production are Tier 1 per established convention — see docs/cdd-kit-patterns.md §flag-gated concurrency wiring.)

## Lane
- feature

(The "Unknown job type" return is a known-unimplemented stub, not a symptom of unknown root cause. Part C is a deterministic, already-diagnosed dead-code removal. Lane is `feature`, not `bug-fix`.)

## Architecture Review Required
- yes
- reason: New RQ worker introduces a Type-B async data flow and a concurrency-gate decision (where `acquire_heavy_query_slot` is acquired, sync↔async routing boundary at L3, request-time-no-Oracle-connection guarantee). This is a module-boundary + data-flow + operational-risk decision (ADR 0011 semaphore, ADR 0006 RQ-queue patterns) that must be settled in `design.md` before implementation.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current behavior (stub returns `(None, "Unknown job type")`; merge_chunks has zero callers) is fully captured in change-request and verifiable by grep/test |
| proposal.md | no | Scope is decided; no user-facing behavior decision to investigate |
| spec.md | no | No new user-facing spec; behavior is "async path engages above L3, sync below L3 unchanged" |
| design.md | yes | Architecture Review Required = yes: slot-acquisition placement, sync↔async routing boundary, Type-B progress milestones, and request-time-no-Oracle-connection guarantee are non-obvious design decisions (ADR 0011 / ADR 0006) |
| qa-report.md | no | Routine pass/fail belongs in `agent-log/qa-reviewer.yml`; promote only if blocking findings or approved-with-risk |
| regression-report.md | no | Sync-path-unchanged regression is covered by tests + agent-log |
| visual-review-report.md | no | No UI output change |
| monkey-test-report.md | no | Not a fuzz/monkey-target surface for this change |
| stress-soak-report.md | yes | Tier 1 new Oracle-bound RQ worker with concurrency slot: durable load/soak evidence required (matches Tier-1 concurrency convention in docs/cdd-kit-patterns.md) |

## Required Contracts
- API: yes — `contracts/api/api-contract.md` (WIP detail async endpoint now returns HTTP 202 + job-id polling shape above L3; regen `contracts/openapi.json` if endpoint table changes)
- CSS/UI: no
- Env: conditional — `contracts/env/env-contract.md` only if a `WIP_*_USE_RQ` / `*_USE_UNIFIED_JOB` feature flag is introduced or its default changes; if flag added, also update `contracts/env/env.schema.json` + `.env.example` (CLAUDE.md rule)
- Data shape: no — async-routed WIP detail must return identical row schema as sync path; covered by AC-7 integration/contract test rather than a separate data-shape contract entry
- Business logic: no — L3 threshold semantics and WIP detail business rules are unchanged
- CI/CD: conditional — if new integration/stress gate target added for WIP RQ path, update `contracts/ci/ci-gate-contract.md`; otherwise not-applicable

## Required Tests
- unit: yes — `execute_wip_detail_job` happy/error path; job_registry registration assertion; merge_chunks absence via `ast.parse()` / import-absence test; `enqueue_job_dynamic("wip-detail")` no longer returns `(None, "Unknown job type")`; update `tests/test_job_registry.py` count and add worker stem to `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py`
- contract: yes — WIP detail async endpoint returns HTTP 202 above L3, sync 200 below L3; response wrapper key matches route `success_response(...)`
- integration: yes — extend `tests/integration/test_wip_rowcount_rq_routing.py`: above-L3 enqueues to RQ, job completes, result retrievable; assert no Oracle connection acquired at request time
- E2E: yes (lightweight) — above-L3 WIP detail 202 → poll → results; below-L3 sync path unchanged
- visual: no
- data-boundary: no
- resilience: yes — Redis-down / worker-down fail-open to sync (mirror `test_redis_timeout_fallback.py`); COUNT pre-check fails open, never 503
- fuzz/monkey: no
- stress: yes — RQ semaphore / slot contention under load for WIP worker (mirror `tests/stress/test_rq_semaphore_stress.py`); required by stress-soak-report.md
- soak: yes (informational) — long-running WIP async job stability; soak runs nightly/weekly per test-layer governance, not pre-merge

## Required Agents
- spec-architect — writes `design.md` (slot-acquisition placement, Type-B async routing boundary, no-request-time-Oracle guarantee, dead-code-removal blast radius)
- contract-reviewer — verifies API (202 async) contract and env-flag/schema parity if flag introduced
- test-strategist — acceptance-criteria → test mapping; merge_chunks-absence + job-registry-count tests
- ci-cd-gatekeeper — confirms gate wiring and any `ci-gate-contract.md` update
- implementation-planner — turns design + contracts + tests into execution packet
- backend-engineer — implements `execute_wip_detail_job`, registers "wip-detail" job type, wires `acquire_heavy_query_slot`, removes `merge_chunks`
- e2e-resilience-engineer — Redis/worker-down fail-open and 202→poll happy path
- stress-soak-engineer — stress + soak consideration for new Oracle-bound worker; produces `stress-soak-report.md`
- qa-reviewer — release readiness; confirms sync-path-unchanged and grep-clean `merge_chunks`

## Inferred Acceptance Criteria
- AC-1: `enqueue_job_dynamic("wip-detail")` returns a valid job id (not `(None, "Unknown job type")`); the "wip-detail" job type is registered in `job_registry`
- AC-2: A WIP detail query above the L3 row-count threshold returns HTTP 202 with a pollable job reference, the background job completes, and results are retrievable by the frontend
- AC-3: A WIP detail query below the L3 threshold uses the synchronous path unchanged (same response shape and row schema as before this change)
- AC-4: No Oracle connection is acquired at request time for async-routed WIP queries; `acquire_heavy_query_slot` is acquired only inside the worker
- AC-5: When Redis/worker is unavailable, the async pre-check fails open to the sync path (never 503)
- AC-6: `merge_chunks` and its now-unused imports are fully deleted; `grep merge_chunks` returns no hits in `src/` or `tests/`
- AC-7: Async-routed WIP detail returns a row schema identical to the sync path (no column drift)
- AC-8: Under concurrent load, the WIP worker respects the global concurrency semaphore without connection-pool exhaustion or slot leaks

## Tasks Not Applicable
- not-applicable: 2.2 (no CSS/UI), 2.4 (data-shape covered by integration test), 2.5 (business logic unchanged), 3.4 (no fuzz/monkey target), 4.2 (no frontend change), 5.1 (no UI/UX), 5.2 (no visual)

## Clarifications or Assumptions
- Feature lane (not bug-fix): "Unknown job type" is a known stub, root cause already stated; no diagnosis needed
- Async-routing API contract (HTTP 202 + polling) already exists for sibling domains; this change makes WIP conform to the existing contract
- CER-001: `src/mes_dashboard/services/` directory path covers wip_service.py; exact file names to be confirmed by spec-architect before editing
- Open question: Does Part B introduce a new `WIP_DETAIL_USE_RQ` flag or reuse existing routing? spec-architect resolves this; determines env-contract scope

## Context Manifest Draft

### Affected Surfaces
- WIP detail async query path (sync↔RQ routing at L3 threshold)
- RQ worker registration + global concurrency slot (Oracle-bound)
- Dead-code removal: `merge_chunks` in WIP service

### Allowed Paths
- specs/changes/wip-rq-worker-chunks-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/rq_worker_preload.py
- deploy/
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_redis_timeout_fallback.py
- tests/integration/test_soak_workload.py
- tests/stress/test_rq_semaphore_stress.py
- tests/test_job_registry.py
- tests/test_query_cost_policy.py
- frontend/tests/playwright/
- docs/adr/0011-global-concurrency-semaphore-rq-oracle-bound.md
- docs/adr/0006-duckdb-prewarm-via-rq-queue.md
- docs/architecture/service-patterns.md
- docs/architecture/cache-spool-patterns.md
- .github/workflows/
