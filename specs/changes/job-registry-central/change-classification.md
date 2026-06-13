# Change Classification

## Change Types
- primary: feature-add (internal infrastructure / async-job registry)
- secondary: refactor (declarative registration added to 8 existing job services, no behavior change)

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 3

## Architecture Review Required
- no
- reason: Additive pattern; no new module boundary, data-flow, or concurrency decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | No existing behavior changes; routes/dispatch untouched and backward-compatible. |
| proposal.md | no | Scope fixed by docs/dynamic-rq-migration-plan.md Phase 2. |
| spec.md | no | No user-facing behavior decision; internal registry only. |
| design.md | no | No architecture review required. |
| qa-report.md | no | Routine pass/fail captured in agent-log. |
| regression-report.md | no | Backward-compat asserted by no-regression suite; log pointer suffices. |
| visual-review-report.md | no | No UI surface. |
| monkey-test-report.md | no | No interactive surface. |
| stress-soak-report.md | no | No new load path; dispatcher is a thin lookup. |

## Required Contracts
- API: none (no new endpoints; routes/dispatch unchanged)
- CSS/UI: none
- Env: none (no new env var; no Redis schema change)
- Data shape: none (no Redis/DB schema or payload change)
- Business logic: none (job semantics unchanged)
- CI/CD: none (cdd-kit validate is a gate, not a contract change)

## Required Tests
- unit: `tests/test_job_registry.py` — 5 new tests (register/get/list, unknown-job-type, enqueue_job_dynamic dispatch, should_enqueue gate, list_registered_job_types)
- contract: `cdd-kit validate` (no new contract files; gate only)
- integration: `tests/test_async_query_job_service.py` — no-regression run (existing suite must stay green)
- E2E: n/a
- visual: n/a
- data-boundary: n/a
- resilience: n/a
- fuzz/monkey: n/a
- stress: n/a
- soak: n/a

## Required Agents
- contract-reviewer (confirm no contract is affected)
- test-strategist (write test-plan.md; author test_job_registry.py plan; pin async-query-job no-regression)
- ci-cd-gatekeeper (write ci-gates.md)
- implementation-planner (write implementation-plan.md)
- backend-engineer (implement job_registry.py, enqueue_job_dynamic(), 8 register_job_type() calls, and tests)
- qa-reviewer (release readiness)

## Inferred Acceptance Criteria
- AC-1: A new module `src/mes_dashboard/services/job_registry.py` exposes `JobTypeConfig` dataclass, private `_REGISTRY` dict, and `register_job_type` / `get_job_type_config` / `list_registered_job_types` functions.
- AC-2: `register_job_type()` registers a config into `_REGISTRY`; `get_job_type_config()` returns the `JobTypeConfig` for a known job_type and `None` for unknown; `list_registered_job_types()` returns all registered type strings.
- AC-3: `async_query_job_service.py` gains `enqueue_job_dynamic()` that dispatches by `job_type` string via the registry; returns `(None, "Unknown job type: …")` for unregistered type; respects `should_enqueue` when set.
- AC-4: Each of the 8 existing job services (`reject_query_job_service`, `yield_alert_job_service`, `production_history_job_service`, `trace_lineage_job_service`, `msd_seed_job_service`, `msd_lineage_job_service`, `material_consumption_service`, `material_trace_service`) adds exactly one `register_job_type()` call at module end, with no change to existing enqueue/execute logic.
- AC-5: Route dispatch logic is unchanged; all 8 job types remain enqueueable through pre-existing `enqueue_xxx()` paths (full backward compatibility).
- AC-6: `tests/test_job_registry.py` — all 5 tests pass.
- AC-7: `tests/test_async_query_job_service.py` — zero regressions.
- AC-8: `cdd-kit validate` passes.

## Tasks Not Applicable
- not-applicable: 1.3 (no design.md / architecture review)

## Clarifications or Assumptions
- CER-001 RESOLVED: full job-service listing confirmed. The 8 services in AC-4 are the targets. `material_consumption_service.py` and `material_trace_service.py` lack `_job_` in their names but are confirmed as the async-job services per migration plan §2-C.
- `trace_job_service.py` is distinct from `trace_lineage_job_service.py`; only `trace_lineage_job_service.py` is in the migration plan §2-C table.
- `job_query_service.py` and `async_query_job_service.py` are infrastructure modules — not job services to register.
- Tier 3 (not lower) because async-job dispatch is a risk-sensitive surface even though this change is fully additive.

## Context Manifest Draft

### Affected Surfaces
- backend-services (new job_registry.py; async_query_job_service.py dispatcher; 8 job service registrations)

### Allowed Paths
- specs/changes/job-registry-central/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/yield_alert_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/trace_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_trace_service.py
- tests/test_async_query_job_service.py
- tests/test_job_registry.py
- contracts/
- .github/workflows/

### Required Contracts
- none (no contract changes; contract-reviewer confirms no-change)

### Required Tests
- tests/test_async_query_job_service.py (no-regression)
- tests/test_job_registry.py (new, 5 tests)

### Agent Work Packets

#### contract-reviewer
- specs/changes/job-registry-central/
- contracts/
- src/mes_dashboard/services/async_query_job_service.py

#### test-strategist
- specs/changes/job-registry-central/
- tests/test_async_query_job_service.py

#### ci-cd-gatekeeper
- specs/changes/job-registry-central/
- .github/workflows/

#### implementation-planner
- specs/changes/job-registry-central/
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py

#### backend-engineer
- specs/changes/job-registry-central/
- docs/dynamic-rq-migration-plan.md
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/yield_alert_job_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/trace_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_trace_service.py
- tests/test_async_query_job_service.py
- tests/test_job_registry.py

#### qa-reviewer
- specs/changes/job-registry-central/

### Context Expansion Requests
- none (CER-001 resolved by ls src/mes_dashboard/services/*job*.py)
