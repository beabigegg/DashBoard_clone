# Change Classification

## Change Types
- primary: refactor (architecture/runtime-path unification)
- primary: business-logic-change (query decomposition strategy changes how large production datasets are paged/materialized to spool)
- secondary: env-change (USE_ROW_COUNT_CHUNKING; HOLD/JOB/MSD ENGINE_PARALLEL)

## Risk Level
- high

## Impact Radius
- cross-module — one shared engine + 7 service modules + 14 SQL files + 3 env files. No frontend, no DB schema, no cross-system reach.

## Tier
- 1

## Architecture Review Required
- yes
- reason: introduces new public engine primitive (`decompose_by_row_count`) consumed by 7 services; new SQL decomposition pattern (ROW_NUMBER() CTE paging) replacing date-range chunking; parallel-execution change bounded by DB_SLOW_POOL_SIZE. Non-obvious decisions: per-service ORDER BY key stability (ties must be deterministic), count-vs-paged consistency under concurrent data change, flag/rollback semantics, and non-interference with existing spool TTL/cleanup/memory-guard.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | captured inline in design.md |
| proposal.md | no | no user-facing product decision |
| spec.md | no | design.md covers the engine/SQL contract |
| design.md | yes | new engine primitive + new SQL pattern + concurrency change (Architecture Review = yes) |
| qa-report.md | no | use agent-log pointers unless blocking/approved-with-risk |
| regression-report.md | yes | durable proof that flag=false fallback is row-identical across all 7 services |
| visual-review-report.md | no | no UI surface |
| monkey-test-report.md | no | no interactive UI surface |
| stress-soak-report.md | yes | row-count chunking changes per-chunk memory profile + adds parallel execution on largest queries |

## Required Contracts
- API: none — no endpoint shape/behavior change
- CSS/UI: none
- Env: yes — contracts/env/env-contract.md + .env.example for USE_ROW_COUNT_CHUNKING (default false), HOLD_ENGINE_PARALLEL, JOB_ENGINE_PARALLEL, MSD_ENGINE_PARALLEL; document DB_SLOW_POOL_SIZE ceiling. CHANGELOG entry to contracts/CHANGELOG.md only.
- Data shape: confirm-only — contracts/data/data-shape-contract.md re-affirmed; spool parquet column schema MUST NOT change between paths
- Business logic: yes — contracts/business/business-rules.md add chunk-decomposition correctness rule (row-count paging == date-range result set; deterministic ORDER BY key per service). CHANGELOG entry to contracts/CHANGELOG.md only.
- CI/CD: confirm-only — extend existing tests only; no new required gate

## Required Tests
- unit: yes — decompose_by_row_count edge cases; per-service count/paged SQL builders; flag gating
- contract: yes — env validation for 4 new vars; data-shape parity (paged columns == date-range columns)
- integration: yes — per service, flag=true vs flag=false, identical spool row set; both Oracle and snapshot/cache paths
- E2E: no (new) — existing per-page E2E acts as regression guard with flag default-off
- visual: no
- data-boundary: yes — chunk-seam off-by-one, duplicate/drop, ORDER BY tie-stability
- resilience: yes — count/paged under concurrent data change; partial-chunk failure; parallelism vs DB_SLOW_POOL_SIZE
- fuzz/monkey: no
- stress: yes — parallel-execution memory profile on largest queries
- soak: yes — sustained memory uniformity vs date-range; spool TTL/cleanup/memory-guard unaffected

## Required Agents
- spec-architect — writes design.md (engine primitive, SQL paging pattern, ORDER BY key stability, concurrency, flag/rollback, count-vs-paged consistency)
- implementation-planner — execution packet after design + contracts + tests are known
- backend-engineer — batch_query_engine.py decompose_by_row_count, 7 service wirings, 14 SQL files, flag gating, env wiring
- test-strategist — AC → test mapping; flag-parity, chunk-boundary, resilience, stress/soak suites
- contract-reviewer — env + business + data-shape; CHANGELOG placement
- qa-reviewer — release readiness; regression-report and stress-soak-report sign-off

## Inferred Acceptance Criteria
- AC-1: decompose_by_row_count(total_rows, rows_per_chunk) returns inclusive (start_row, end_row) ranges covering exactly 1..total_rows with no gap and no overlap, including edge cases: total_rows=0, total_rows<rows_per_chunk, total_rows exact multiple, total_rows=1.
- AC-2: With USE_ROW_COUNT_CHUNKING=false (default), all 7 services produce a row-identical spool result to the existing date-range path — no behavior change on merge.
- AC-3: With USE_ROW_COUNT_CHUNKING=true, each service's paged path produces the SAME complete row set as the date-range path for identical filters — no dropped or duplicated rows at chunk boundaries — using the per-service deterministic ORDER BY key from change-request.md.
- AC-4: downtime_analysis_service is migrated to BatchQueryEngine → execute_plan → merge_chunks_to_spool; no direct Oracle→spool path remains; spool output schema/namespace unchanged.
- AC-5: Spool parquet column schema is identical between date-range and row-count paths for every service (data-shape parity).
- AC-6: HOLD/JOB/MSD ENGINE_PARALLEL are env-configurable and never exceed DB_SLOW_POOL_SIZE (prod=3, dev=2); all 4 new env vars documented in env-contract, .env.example.
- AC-7: Existing spool TTL, cleanup, and memory-guard behavior are unchanged (no spool-lifecycle regression).
- AC-8: The 3 excluded services (yield_alert, material_trace, material_consumption) are not modified.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.6, 4.2, 5.1, 5.2

## Clarifications or Assumptions
- ASSUMPTION: spool output (column schema + namespace) must remain identical across both chunking paths; pinned by AC-5 and a data-shape parity test.
- ASSUMPTION: no new API endpoint or response-shape change; existing per-page E2E acts as regression guard only.
- ASSUMPTION: .env Phase 0 (HOLD/JOB/MSD ENGINE_PARALLEL) kept in this change as the env-contract portion.
- ASSUMPTION: extend existing test suite for chunk-boundary/resilience; no new CI required gate added.

## Context Manifest Draft

### Affected Surfaces
- backend large-query pipeline (BatchQueryEngine + spool)
- per-service SQL decomposition (7 services)
- runtime env configuration (chunking flag + ENGINE_PARALLEL)

### Allowed Paths
- specs/changes/batch-rowcount-unification/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/reject_cache_sql_runtime.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/services/hold_dataset_cache.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/job_query_service.py
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/job_query/
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/resource/
- contracts/env/env-contract.md
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- .env
- .env.development
- .env.production
- .env.example
- tests/

### Required Contracts
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md (confirm-only)
- contracts/CHANGELOG.md

### Required Tests
- tests/test_batch_query_engine.py
- tests/ (per-service SQL-runtime unit tests, integration, resilience, stress/soak)
