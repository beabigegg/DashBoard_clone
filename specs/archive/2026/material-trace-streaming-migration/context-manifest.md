# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- material-trace query execution (backend service + RQ worker)
- core cross-worker concurrency (`global_concurrency` — semantics only)
- core chunked DuckDB job base + spool pipeline
- env/runtime config (new feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB`)

## Allowed Paths
- specs/changes/material-trace-streaming-migration/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/material_trace_duckdb_runtime.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/routes/material_trace_routes.py
- src/mes_dashboard/routes/trace_routes.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- tests/test_base_chunked_duckdb_job.py
- tests/integration/test_rowcount_flag_parity.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/stress/test_material_trace_stress.py
- tests/stress/test_chunk_boundary.py
- tests/e2e/test_material_trace_e2e.py

## Required Contracts
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

## Required Tests
- tests/integration/test_eap_alarm_rq_async.py (RQ-async + 503 pattern reference)
- tests/integration/test_rowcount_flag_parity.py (parity pattern reference)
- tests/test_base_chunked_duckdb_job.py
- tests/stress/test_material_trace_stress.py
- tests/stress/test_chunk_boundary.py
- tests/e2e/test_material_trace_e2e.py

## Agent Work Packets

### spec-architect
- specs/changes/material-trace-streaming-migration/
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py

### implementation-planner
- specs/changes/material-trace-streaming-migration/
- docs/architecture/query-dataflow-unification.md
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py

### backend-engineer
- specs/changes/material-trace-streaming-migration/
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/material_trace_duckdb_runtime.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/routes/material_trace_routes.py
- src/mes_dashboard/routes/trace_routes.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template

### test-strategist
- specs/changes/material-trace-streaming-migration/
- tests/integration/test_rowcount_flag_parity.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/test_base_chunked_duckdb_job.py
- tests/e2e/test_material_trace_e2e.py

### contract-reviewer
- specs/changes/material-trace-streaming-migration/
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md

### e2e-resilience-engineer
- specs/changes/material-trace-streaming-migration/
- tests/integration/test_eap_alarm_rq_async.py
- tests/e2e/test_material_trace_e2e.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/global_concurrency.py

### stress-soak-engineer
- specs/changes/material-trace-streaming-migration/
- tests/stress/test_material_trace_stress.py
- tests/stress/test_chunk_boundary.py

### ci-cd-gatekeeper
- specs/changes/material-trace-streaming-migration/
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/material-trace-streaming-migration/

## Context Expansion Requests
-

## Approved Expansions
- CER-001 (approved): spec-architect needs `material_trace_service.py`, `global_concurrency.py`, `base_chunked_duckdb_job.py`, `query-dataflow-unification.md` to resolve the cross-chunk-reduction open question and write design.md. All four paths are in Allowed Paths above.
