---
change-id: resource-history-migration
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Change Classification

## Change Types
- primary: refactor, business-logic-change
- secondary: env-change, ci-cd-change, performance-fix

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: Dual-query structure (detail + OEE) forces a non-obvious chunk-strategy decision. OEE Availability = (PRD+SBY+EGT)/(PRD+SBY+EGT+SDT+UDT+NST) per RESOURCEID is a ratio-of-SUMs spanning all time chunks — this constitutes cross-row reduction and is incompatible with naive row-level time-chunking (ADR-0003 precedent). spec-architect must resolve: (a) two separate jobs (False detail + True OEE) vs (b) one True job whose post_aggregate produces both views in DuckDB — and confirm spool-schema-UNCHANGED holds under either topology.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Behavior captured in change-request + design.md |
| proposal.md | no | Roadmap-driven (query-dataflow-unification.md §3 P2) |
| spec.md | no | No user-facing behavior decision; spool schema unchanged |
| design.md | yes | Architecture Review Required = yes; spec-architect resolves detail/OEE job split + requires_cross_chunk_reduction |
| qa-report.md | no | Routine; promote to yes on blocking findings only |
| regression-report.md | no | Flag defaults off; no default-path behavior change |
| visual-review-report.md | no | No frontend change |
| monkey-test-report.md | no | No interactive UI surface |
| stress-soak-report.md | no | Deferred via tier-floor-override; revisit on flag enablement |

## Required Contracts
- API: none — no new endpoints, no response-shape change (confirm-only)
- CSS/UI: none — no frontend change (explicit non-goal)
- Env: contracts/env/env-contract.md — add `RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`, Restart required); update `.env.example`
- Data shape: contracts/data/data-shape-contract.md — assert spool-schema-UNCHANGED for resource-history detail + OEE parquet outputs (§3.x)
- Business logic: contracts/business/business-rules.md — new ASYNC-09 rule for unified-job execution path + OEE cross-chunk-reduction semantics
- CI/CD: contracts/ci/ci-gate-contract.md — compat note; patch bump

## Required Tests
- unit: ResourceHistoryJob class(es), decompose_by_time_range chunk strategy, OEE post_aggregate DuckDB SQL aggregation, requires_cross_chunk_reduction behavior, base+OEE parallel model preserved, iterrows→DuckDB SQL parity
- contract: env default-value pin; ASYNC-09 presence; spool-schema-UNCHANGED; _APPROVED_CALLERS extension (test_query_cost_policy.py); job registry (test_async_query_job_service.py)
- integration: route flag dispatch (off→legacy, on→unified enqueue); spool parquet output parity for detail + OEE views
- E2E: none — flag off by default, no frontend change
- visual: none
- data-boundary: OEE ratio-of-SUMs cross-chunk correctness per RESOURCEID; chunk-boundary aggregation must equal single-pass
- resilience: degraded-path → 503 when sync-fallback is removed (AC-7)
- fuzz/monkey: none
- stress: deferred (tier-floor-override)
- soak: deferred (tier-floor-override)

## Required Agents
- change-classifier (complete)
- spec-architect (design.md — resolve detail/OEE job split + requires_cross_chunk_reduction before implementation-planner)
- test-strategist
- implementation-planner
- backend-engineer
- contract-reviewer
- qa-reviewer
- ci-cd-gatekeeper

## Inferred Acceptance Criteria
- AC-1: When `RESOURCE_HISTORY_USE_UNIFIED_JOB=off` (default), `resource_history_service.export_csv()` behavior is unchanged — the legacy path is unchanged and existing tests pass.
- AC-2: When `RESOURCE_HISTORY_USE_UNIFIED_JOB=on`, the two full-DataFrame `read_sql_df(detail_sql)` and `read_sql_df(oee_sql)` calls are replaced by chunk-to-spool execution via `decompose_by_time_range`, eliminating the OOM risk (no single full-table materialization in gunicorn process).
- AC-3: OEE Availability (ratio-of-SUMs per RESOURCEID across all time chunks) computed via chunk-to-spool equals the value computed by the legacy single-pass `read_sql_df(oee_sql)` to within 1e-6; cross-chunk reduction strategy decided by spec-architect in design.md.
- AC-4: The `iterrows` loop in `resource_dataset_cache.py` is replaced by DuckDB SQL aggregation with output parity to the prior in-memory transformation.
- AC-5: The base+OEE `ThreadPoolExecutor(max_workers=2)` parallel model is preserved in the unified-job implementation.
- AC-6: The output spool parquet schema for both detail and OEE views is unchanged; no frontend resource pages are modified (spool-schema-UNCHANGED assertion passes).
- AC-7: The sync-fallback pandas SELECT is removed from the unified execution path; degraded path (worker unavailable) returns 503, consistent with prior P2 AC-5 pattern.
- AC-8: `env-contract.md` pins `RESOURCE_HISTORY_USE_UNIFIED_JOB` default (`off`); `.env.example` updated; ASYNC-09 business rule added; `_APPROVED_CALLERS` in `test_query_cost_policy.py` extended; all contract validators pass.
- AC-9: The new resource-history job is registered in the job registry; `test_async_query_job_service.py` asserts registration with `importlib.reload()` pattern per test-discipline rule.

## Tasks Not Applicable
- not-applicable: 2.1 (API — confirm-only, no edit), 2.2 (CSS/UI — no frontend), 3.3 (E2E/Playwright — flag off, no frontend), 3.4 (monkey — no interactive UI), 3.5 (stress/soak — deferred via tier-floor-override), 4.2 (Frontend — no change), 4.4 (CI/CD workflows — no new workflow files), 5.1 (UI/UX — no UI surface), 5.2 (visual — no UI surface), 6.4 (nightly/weekly — deferred gates)

## Clarifications or Assumptions
- Assumption: detail query is row-level (requires_cross_chunk_reduction=False); OEE query is cross-chunk (requires_cross_chunk_reduction=True). Final topology (two jobs vs one True job) is a spec-architect decision.
- Assumption: tier-floor-override required in tasks.yml frontmatter (flag-gated off, no default-path caller, stress/soak deferred — same rationale as prior P2).
- Assumption: api-contract.md confirm-only; no edit required.
- Assumption: Version entries go to contracts/CHANGELOG.md only.
- Note: eap-alarm-unified-job-poc is a stated precondition; base_chunked_duckdb_job.py is already in codebase (precondition satisfied).

## Context Manifest Draft

### Affected Surfaces
- resource-history query execution engine (services + worker job)
- shared chunked-job core (base_chunked_duckdb_job, query_cost_policy, job_registry)
- env / business / data-shape / ci contracts
- async RQ worker dispatch (routing already exists; engine swapped)

### Allowed Paths
- specs/changes/resource-history-migration/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/architecture/ci-workflow.md
- docs/architecture/test-discipline.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- src/mes_dashboard/workers/
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/resource_history_job_service.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/sql/resource_history/
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/api/api-contract.md
- contracts/CHANGELOG.md
- tests/test_query_cost_policy.py
- tests/test_async_query_job_service.py
- tests/test_resource_history_service.py
- tests/test_resource_history_job_service.py
- tests/test_resource_history_unified_job.py
- tests/integration/test_resource_history_rq_async.py

### Agent Work Packets

#### spec-architect
- specs/changes/resource-history-migration/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_job_service.py
- src/mes_dashboard/sql/resource_history/

#### test-strategist
- specs/changes/resource-history-migration/
- docs/architecture/test-discipline.md
- tests/test_query_cost_policy.py
- tests/test_async_query_job_service.py
- tests/test_resource_history_service.py
- tests/test_resource_history_job_service.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py

#### implementation-planner
- specs/changes/resource-history-migration/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/resource_history_job_service.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/workers/

#### backend-engineer
- specs/changes/resource-history-migration/
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/resource_history_job_service.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/resource_history/
- tests/test_resource_history_service.py
- tests/test_resource_history_job_service.py
- tests/test_resource_history_unified_job.py
- tests/test_query_cost_policy.py
- tests/test_async_query_job_service.py
- tests/integration/test_resource_history_rq_async.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md

#### contract-reviewer
- specs/changes/resource-history-migration/
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/api/api-contract.md
- contracts/CHANGELOG.md

#### qa-reviewer
- specs/changes/resource-history-migration/
- tests/test_resource_history_service.py
- tests/test_resource_history_job_service.py
- tests/test_resource_history_unified_job.py
- tests/test_query_cost_policy.py
- tests/test_async_query_job_service.py

#### ci-cd-gatekeeper
- specs/changes/resource-history-migration/
- docs/architecture/ci-workflow.md
- contracts/ci/ci-gate-contract.md
