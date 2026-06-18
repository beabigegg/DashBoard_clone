# Change Classification

## Change Types
- primary: feature-add (backend infrastructure / core abstraction)
- secondary: env-change (new `DUCKDB_JOB_DIR` runtime config), data-shape-change (Oracle → Arrow RecordBatch → DuckDB/parquet streaming boundary)

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
- reason: This is the foundational abstraction layer (`BaseChunkedDuckDBJob` template method, `QueryCostPolicy` 4-layer classifier, `OracleArrowReader` streaming + connection-pool) that all P1–P5 domain migrations depend on. It encodes non-obvious design decisions: cross-chunk reduction path vs multi-parquet-append path, DuckDB single-writer constraint + writer_lock, Oracle connection-pool sizing/lifecycle (min=2/max=12–15, finally:close), short-circuit cost policy replacing scattered `*_ASYNC_DAY_THRESHOLD` env vars, and ChunkStrategy classification inherited from ADR-0003. A design error here propagates to every downstream migration and to OOM/operational risk. `spec-architect` must produce `design.md` before `implementation-planner` runs.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Pure new-module addition; no existing behavior to document. Current 3-path landscape is captured in `docs/architecture/query-dataflow-unification.md`. |
| proposal.md | no | Product/behavior decision already made in the architecture design doc. |
| spec.md | no | No user-facing behavior; abstraction contract belongs in `design.md`. |
| design.md | yes | Architecture Review Required = yes. Must document: template-method seams, two reduction paths, ChunkStrategy taxonomy + ADR-0003 linkage, Oracle pool lifecycle/sizing, writer_lock model, job-temp path + TTL/orphan cleanup, and 4-layer cost policy migration from env thresholds. Resolves two Open Questions (DUCKDB_JOB_DIR default; pool singleton vs per-worker per ADR-0004). |
| qa-report.md | no | Routine pass/fail evidence fits `agent-log/qa-reviewer.yml`; promote only on blocking/approved-with-risk findings. |
| regression-report.md | no | No existing behavior modified; no regression surface. |
| visual-review-report.md | no | No UI. |
| monkey-test-report.md | no | No interactive UI surface. |
| stress-soak-report.md | no | Stress/soak deferred to first P1 domain migration; no end-to-end load surface yet. |

## Required Contracts
- API: none — no HTTP endpoints exposed
- CSS/UI: none
- Env: `contracts/env/env-contract.md`, `contracts/env/.env.example.template`, `contracts/env/env.schema.json` — add `DUCKDB_JOB_DIR` with pinned default value. Deprecate (not remove) `*_ASYNC_DAY_THRESHOLD` vars per env breaking-change-policy.
- Data shape: `contracts/data/data-shape-contract.md` — document Oracle → pyarrow RecordBatch → DuckDB/parquet streaming boundary and chunk-iteration row-level invariants.
- Business logic: none — `classify_query_cost` is infrastructure routing policy, not an MES domain rule.
- CI/CD: `contracts/ci/ci-gate-contract.md` — confirm new `core/` modules and tests are covered by `backend-tests.yml`; add gate row only if a dedicated concurrency/integration test job is introduced.

## Required Tests
- unit: yes — `BaseChunkedDuckDBJob` template-method seams for all 4 ChunkStrategies and both reduction paths; `QueryCostPolicy` 4-layer short-circuit; `OracleArrowReader` chunk iteration and `finally: conn.close()` (mock Oracle)
- contract: yes — env-contract test pinning `DUCKDB_JOB_DIR` name AND default; data-shape boundary contract test for Arrow/parquet schema
- integration: yes — real Oracle pool (exhaustion+return), DuckDB writer_lock under `requires_cross_chunk_reduction=True`, job-temp lifecycle + TTL (nightly real-infra lane)
- E2E: none
- visual: none
- data-boundary: yes — null/empty chunk, schema drift, Oracle DATE/CHAR strip semantics through `OracleArrowReader`
- resilience: yes — Oracle failure mid-chunk, pool exhaustion, DuckDB write failure, partial-chunk abort all release connections and clean job-temp
- fuzz/monkey: none
- stress: deferred to first P1 domain migration
- soak: deferred to first P1 domain migration

## Required Agents
- spec-architect (write `design.md` — before planner)
- implementation-planner (convert design + contracts + tests to execution packet)
- backend-engineer (implement 3 new `core/` modules)
- test-strategist (unit/contract/integration/data-boundary/resilience plan + AC→test mapping)
- ci-cd-gatekeeper (write `ci-gates.md` confirming backend-tests.yml coverage)
- contract-reviewer (review env + data-shape contract edits)
- qa-reviewer (Tier-1 release readiness)

## Inferred Acceptance Criteria
- AC-1: `BaseChunkedDuckDBJob` exposes a template-method `run()` that orchestrates pre_query → build_chunk_sql → chunk_to_duckdb → post_aggregate → progress_report, and supports all four ChunkStrategy values (TIME, ID_LIST, ROW_COUNT, SINGLE).
- AC-2: With `requires_cross_chunk_reduction=False`, chunks are written via independent multi-parquet append (no DuckDB single-writer contention); with `=True`, chunk inserts are serialized under `writer_lock` into a single DuckDB file.
- AC-3: `OracleArrowReader` streams Oracle results as pyarrow RecordBatches, acquires one connection per chunk from a pool sized min=2/max=12–15, and always returns the connection via `finally: conn.close()` — verified by a pool-exhaustion-then-recovery test.
- AC-4: `classify_query_cost` applies the 4-layer short-circuit in order and returns the correct routing (L0 spool-hit→SYNC, L1 always-async-domain→ASYNC, L2 date-span over threshold→ASYNC, L3 rowcount COUNT(*) over threshold→ASYNC), with earlier layers short-circuiting later ones.
- AC-5: DuckDB job-temp files are created at `{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb`, deleted on job completion; mid-job failure releases the connection and cleans the temp file.
- AC-6: `DUCKDB_JOB_DIR` is added to the env contract, `.env.example.template`, and `env.schema.json` with a pinned default value; a contract test asserts both name and default.
- AC-7: No new pip dependency is introduced; no existing route, service, or frontend module is modified (diff confined to new `core/` modules + config + contracts + tests).
- AC-8: The Oracle → Arrow → DuckDB/parquet streaming boundary is documented in the data-shape contract; a data-boundary test covers null/empty-chunk and Oracle DATE/CHAR strip edge cases.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 3.3, 3.5, 4.2, 5.1, 5.2

## Clarifications or Assumptions
- Two Open Questions resolved in `design.md` by spec-architect: (1) DUCKDB_JOB_DIR default path — design should use /tmp subdir consistent with existing `QUERY_SPOOL_DIR`; (2) Oracle pool singleton vs per-worker — must account for ADR-0004 gunicorn preload/fork-safety (pool created pre-fork is not fork-safe).
- `classify_query_cost` is infrastructure routing policy (not MES domain rule) → no business-rules.md change; revisit if a threshold encodes domain semantics.
- Scattered `*_ASYNC_DAY_THRESHOLD` env vars are only deprecated (not removed) in this change; removal happens in P1–P5 per env breaking-change-policy (deprecate-2-minors).
- Stress/soak certification deferred to first P1 domain migration.
- New core module unit tests live alongside existing `tests/test_*.py` flat suite (e.g. `tests/test_base_chunked_duckdb_job.py`); real-Oracle integration tests in `tests/integration/` on nightly lane.

## Context Manifest Draft

### Affected Surfaces
- backend core infrastructure: `src/mes_dashboard/core/` (3 new modules)
- runtime config: env contract (`DUCKDB_JOB_DIR`)
- data boundary: Oracle → Arrow → DuckDB/parquet streaming

### Allowed Paths
- specs/changes/unified-query-core-infra/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/architecture/cache-spool-patterns.md
- src/mes_dashboard/core/
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/config/
- contracts/env/
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- tests/

### Agent Work Packets

#### spec-architect
- specs/changes/unified-query-core-infra/
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/architecture/cache-spool-patterns.md
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/core/query_spool_store.py

#### implementation-planner
- specs/changes/unified-query-core-infra/
- docs/architecture/query-dataflow-unification.md
- src/mes_dashboard/core/
- contracts/env/
- contracts/data/data-shape-contract.md

#### backend-engineer
- specs/changes/unified-query-core-infra/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/services/batch_query_engine.py
- contracts/env/
- contracts/data/data-shape-contract.md
- tests/

#### test-strategist
- specs/changes/unified-query-core-infra/
- src/mes_dashboard/core/
- tests/

#### ci-cd-gatekeeper
- specs/changes/unified-query-core-infra/
- contracts/ci/ci-gate-contract.md
- .github/workflows/

#### contract-reviewer
- specs/changes/unified-query-core-infra/
- contracts/env/
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md

#### qa-reviewer
- specs/changes/unified-query-core-infra/
- contracts/
