# Change Classification

## Change Types
- primary: migration (backend service: pd.merge → DuckDB JOIN), performance/operational-risk-change
- secondary: env-change (new feature flag DOWNTIME_USE_UNIFIED_JOB), business-logic-change (RESOURCEID+time-overlap bridging must stay behavior-equivalent)

## Lane
- feature

## Risk Level
- high
- rationale: Replaces the system's #1 OOM risk point; touches cross-row aggregation chunking under ADR-0003; new chunk-by-RESOURCEID grouping model; feature-flagged but must produce byte/row-equivalent results to the existing pd.merge Path B.

## Impact Radius
- cross-module
- rationale: downtime_analysis_service + downtime_analysis_duckdb_cache + downtime_query_job_service + core/base_chunked_duckdb_job + job_registry + downtime worker; behavior must match the legacy path consumed by downtime routes.

## Tier
- 1

## Architecture Review Required
- yes
- reason: XL change requires an independent design.md for the RESOURCEID grouping model and the DuckDB time-overlap JOIN strategy (window-function vs. range-join), and must reconcile with ADR-0003 (cross-row aggregation, no row/time chunking). Open questions (grouping granularity, JOIN SQL strategy) must be resolved before implementation.

## Required Artifacts

Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Existing Path B behavior captured in change-request + design.md + reference_mes_downtime_job_tables.md |
| proposal.md | no | Scope fixed by query-dataflow-unification §3 P3; no user-facing behavior decision to resolve |
| spec.md | no | No new user-facing behavior; flag-gated equivalent migration |
| design.md | yes | XL migration; RESOURCEID grouping + DuckDB JOIN strategy decision required before implementation-planner runs (Architecture Review = yes) |
| qa-report.md | no | Routine pass/fail in agent-log; promote only on blocking findings |
| regression-report.md | no | Flag-parity equivalence captured via tests + agent-log |
| visual-review-report.md | no | No UI surface |
| monkey-test-report.md | no | No interactive UI surface |
| stress-soak-report.md | yes | #1 OOM risk point; durable memory-ceiling/large-cardinality stress evidence required to prove migration safety |

## Required Contracts
- API: none (response shape is verify-only; not modified)
- CSS/UI: none
- Env: yes — add `DOWNTIME_USE_UNIFIED_JOB` (default `off`) to env-contract.md, env.schema.json (boolean enum + default false), .env.example.template, .env.example
- Data shape: verify-only — assert downtime spool/output columns byte/row-equivalent between Path B legacy and DuckDB-JOIN path; document each path's columns separately (no blanket "UNCHANGED" if columns differ)
- Business logic: verify-only — RESOURCEID+time-overlap JOBID bridging must remain consistent with business-rules.md; document if any new rule applies
- CI/CD: none expected — confirm existing downtime gates wire the new flag path

## Required Tests
- unit: DuckDB JOIN builder (range/time-overlap predicate), RESOURCEID grouping/chunk planner, feature-flag dispatch (flag off → legacy Path B, flag on → DuckDB JOIN)
- contract: env-contract test pinning `DOWNTIME_USE_UNIFIED_JOB` name + default; data-shape response equivalence test
- integration: downtime RQ async job parity; flag-on vs flag-off result equivalence on real-shaped fixtures; RESOURCEID grouping with chunk_strategy=SINGLE per group
- E2E: downtime-analysis flow unaffected (flag default off) — confirm no regression via existing test_downtime_analysis_e2e.py
- visual: none
- data-boundary: large/empty/skewed RESOURCEID groups, NULL/overlapping time windows, single-RESOURCEID vs multi-RESOURCEID cardinality at JOIN boundary
- resilience: DuckDB spill-to-disk under constrained memory; partial-failure/abort mid-JOIN; worker restart during grouped job
- fuzz/monkey: not applicable (no interactive UI)
- stress: high-cardinality RESOURCEID × time-overlap JOIN under memory ceiling proving no heap OOM; extend tests/stress/test_downtime_analysis_stress.py
- soak: weekly cadence (not pre-merge); extend tests/integration/test_soak_workload.py

## Required Agents
1. spec-architect (writes design.md: RESOURCEID grouping model + DuckDB time-overlap JOIN strategy; reconcile ADR-0003)
2. implementation-planner (turns design + contracts + tests into execution packet)
3. backend-engineer (replace Path B pd.merge with streaming Arrow → DuckDB JOIN; flag dispatch; grouping)
4. test-strategist (AC → test mapping; flag-parity, data-boundary, stress coverage)
5. contract-reviewer (env contract + data-shape/business equivalence verification)
6. e2e-resilience-engineer (spill/abort/worker-restart resilience)
7. stress-soak-engineer (OOM-ceiling stress evidence; stress-soak-report.md)
8. ci-cd-gatekeeper (confirm gates wire the flag path; gate-readiness)
9. qa-reviewer (release readiness)

## Tasks Not Applicable
- 2.2 (CSS/UI contract — no UI surface)
- 3.4 (fuzz/monkey — no interactive UI)
- 4.2 (Frontend — no frontend changes)
- 5.1 (UI/UX review — no UI surface)
- 5.2 (Visual review — no UI surface)

## Inferred Acceptance Criteria
- AC-1: When `DOWNTIME_USE_UNIFIED_JOB=off` (default), downtime analysis output (rows, columns, values, spool schema) is byte/row-identical to current production behavior.
- AC-2: When `DOWNTIME_USE_UNIFIED_JOB=on`, `_bridge_jobid` Path B contains no `pd.merge`; events and jobs are streamed as Arrow into two DuckDB tables and joined inside DuckDB.
- AC-3: Flag-on and flag-off produce equivalent results for the same inputs across representative fixtures (single-RESOURCEID, multi-RESOURCEID, overlapping/NULL time windows).
- AC-4: Chunking uses RESOURCEID grouping with `requires_cross_chunk_reduction=True` and `chunk_strategy=SINGLE` per group; TIME and ROW_COUNT chunking are never used (ADR-0003 preserved).
- AC-5: Under a constrained-memory stress run with high-cardinality RESOURCEID × time-overlap data, the DuckDB-JOIN path completes via on-disk spill without Python heap OOM, whereas the legacy path is the documented OOM baseline.
- AC-6: `DOWNTIME_USE_UNIFIED_JOB` is registered in env-contract.md, env.schema.json (boolean enum + default false), and .env.example, with a contract test pinning name and default.
- AC-7: RESOURCEID + time-overlap JOBID bridging remains consistent with reference_mes_downtime_job_tables.md and business-rules.md (bridge semantics unchanged).
- AC-8: Existing downtime routes/E2E/spool consumers see no behavior or schema change (non-goals upheld).
