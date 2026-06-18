# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend core infrastructure: `src/mes_dashboard/core/` (3 new modules)
- runtime config: env contract (`DUCKDB_JOB_DIR`)
- data boundary: Oracle → Arrow → DuckDB/parquet streaming

## Allowed Paths
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
- contracts/
- tests/
- .github/workflows/

## Required Contracts
- contracts/env/env-contract.md
- contracts/env/.env.example.template
- contracts/env/env.schema.json
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/ (new unit tests: tests/test_base_chunked_duckdb_job.py, tests/test_query_cost_policy.py, tests/test_oracle_arrow_reader.py)
- tests/integration/ (Oracle pool, DuckDB writer_lock, job-temp lifecycle — nightly real-infra lane)
- tests/contract/ (env + data-shape boundary)

## Agent Work Packets

### spec-architect
- specs/changes/unified-query-core-infra/
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0004-gunicorn-preload-app-fork-safety.md
- docs/architecture/cache-spool-patterns.md
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/duckdb_runtime.py
- src/mes_dashboard/core/query_spool_store.py

### implementation-planner
- specs/changes/unified-query-core-infra/
- docs/architecture/query-dataflow-unification.md
- src/mes_dashboard/core/
- contracts/env/
- contracts/data/data-shape-contract.md

### backend-engineer
- specs/changes/unified-query-core-infra/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- src/mes_dashboard/services/batch_query_engine.py
- contracts/env/
- contracts/data/data-shape-contract.md
- tests/

### test-strategist
- specs/changes/unified-query-core-infra/
- src/mes_dashboard/core/
- tests/

### ci-cd-gatekeeper
- specs/changes/unified-query-core-infra/
- contracts/ci/ci-gate-contract.md
- .github/workflows/

### contract-reviewer
- specs/changes/unified-query-core-infra/
- contracts/env/
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/unified-query-core-infra/
- contracts/

## Context Expansion Requests
-

## Approved Expansions
- expansion-id: CER-001
  approved_paths:
    - docs/architecture/query-dataflow-unification.md
    - docs/adr/0003-downtime-rowcount-chunking-exclusion.md
    - docs/adr/0004-gunicorn-preload-app-fork-safety.md
    - src/mes_dashboard/services/batch_query_engine.py
    - src/mes_dashboard/core/global_concurrency.py
    - src/mes_dashboard/core/duckdb_runtime.py
    - src/mes_dashboard/core/query_spool_store.py
  reason: change-request.md mandates reading architecture doc §2/§4/§6 and ADR-0003 before implementation; BatchQueryEngine, global_concurrency, duckdb_runtime, and query_spool_store are named positive references for pool/parallelism/writer-lock/spool-path design needed by spec-architect and backend-engineer.
  status: approved
