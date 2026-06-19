# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- downtime-analysis backend service (JOBID bridging / Path B `pd.merge` → DuckDB JOIN)
- DuckDB chunked-job core (BaseChunkedDuckDBJob + job registry)
- downtime async worker / query-job service
- env / runtime configuration (new feature flag DOWNTIME_USE_UNIFIED_JOB)

## Allowed Paths
- specs/changes/downtime-duckdb-join-migration/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- .env.example
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md
- docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/workers/eap_alarm_worker.py
- tests/integration/test_downtime_rq_async.py
- tests/integration/test_rowcount_flag_parity.py
- tests/stress/test_downtime_analysis_stress.py
- tests/test_base_chunked_duckdb_job.py
- tests/e2e/test_downtime_analysis_e2e.py
- tests/contract/
- tests/test_env_contract.py
- tests/test_query_cost_policy.py

## Required Contracts
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/data/data-shape-contract.md (verify-only)
- contracts/business/business-rules.md (verify-only)

## Required Tests
- tests/integration/test_downtime_rq_async.py
- tests/integration/test_rowcount_flag_parity.py
- tests/stress/test_downtime_analysis_stress.py
- tests/test_base_chunked_duckdb_job.py
- tests/e2e/test_downtime_analysis_e2e.py
- tests/contract/ (env-flag contract test)

## Agent Work Packets

### spec-architect
- specs/changes/downtime-duckdb-join-migration/
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/workers/eap_alarm_worker.py
- contracts/business/business-rules.md

### implementation-planner
- specs/changes/downtime-duckdb-join-migration/
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/feature_flags.py
- contracts/env/

### backend-engineer
- specs/changes/downtime-duckdb-join-migration/
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/routes/downtime_analysis_routes.py

### test-strategist
- specs/changes/downtime-duckdb-join-migration/
- tests/integration/test_downtime_rq_async.py
- tests/integration/test_rowcount_flag_parity.py
- tests/test_base_chunked_duckdb_job.py
- tests/contract/

### contract-reviewer
- specs/changes/downtime-duckdb-join-migration/
- contracts/env/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

### e2e-resilience-engineer
- specs/changes/downtime-duckdb-join-migration/
- tests/e2e/test_downtime_analysis_e2e.py
- tests/integration/test_downtime_rq_async.py

### stress-soak-engineer
- specs/changes/downtime-duckdb-join-migration/
- tests/stress/test_downtime_analysis_stress.py

### ci-cd-gatekeeper
- specs/changes/downtime-duckdb-join-migration/
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/downtime-duckdb-join-migration/

## Approved Context Expansions

### CER-001 (approved)
- requested_paths:
  - src/mes_dashboard/workers/eap_alarm_worker.py
  - docs/adr/0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md
  - docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
- reason: spec-architect and backend-engineer need these as canonical reference implementation for BaseChunkedDuckDBJob streaming-Arrow + cross-chunk pairing pattern established by eap-alarm-unified-job-poc
- approved-by: main-claude
- scope: spec-architect, backend-engineer
