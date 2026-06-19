# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- async job execution plane (eap_alarm domain)
- shared job enqueue registry (`job_registry`, `async_query_job_service`)
- shared chunked-job base (`core/base_chunked_duckdb_job.py`, `core/oracle_arrow_reader.py`)
- runtime config (feature flag `EAP_ALARM_USE_UNIFIED_JOB`)

## Allowed Paths
- specs/changes/eap-alarm-unified-job-poc/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/services/eap_alarm_service.py
- src/mes_dashboard/services/eap_alarm_cache.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/eap_alarm_routes.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/config/settings.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/api/error-format.md
- contracts/CHANGELOG.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- .env.example
- tests/test_eap_alarm_service.py
- tests/test_base_chunked_duckdb_job.py
- tests/test_async_query_job_service.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- tests/integration/test_oracle_arrow_pool_lifecycle.py
- tests/integration/test_rowcount_flag_parity.py
- tests/integration/test_soak_workload.py
- tests/e2e/test_eap_alarm_e2e.py
- tests/stress/test_async_job_stress.py
- tests/stress/test_chunk_boundary.py
- tests/contract/

## Required Contracts
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/api/error-format.md (only if the always-async 503 status is newly documented)

## Required Tests
- tests/test_eap_alarm_service.py
- tests/test_base_chunked_duckdb_job.py
- tests/test_async_query_job_service.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- tests/integration/test_oracle_arrow_pool_lifecycle.py
- tests/integration/test_rowcount_flag_parity.py
- tests/integration/test_soak_workload.py
- tests/e2e/test_eap_alarm_e2e.py
- tests/stress/test_async_job_stress.py
- tests/stress/test_chunk_boundary.py

## Agent Work Packets

### spec-architect
- specs/changes/eap-alarm-unified-job-poc/
- docs/architecture/query-dataflow-unification.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- docs/adr/0008-eap-alarm-coarse-spool-detail-join.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/services/eap_alarm_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/eap_alarm_routes.py

### implementation-planner
- specs/changes/eap-alarm-unified-job-poc/
- docs/architecture/query-dataflow-unification.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/routes/eap_alarm_routes.py

### backend-engineer
- specs/changes/eap-alarm-unified-job-poc/
- src/mes_dashboard/workers/eap_alarm_worker.py
- src/mes_dashboard/services/eap_alarm_service.py
- src/mes_dashboard/services/eap_alarm_cache.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/eap_alarm_routes.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/config/settings.py

### test-strategist
- specs/changes/eap-alarm-unified-job-poc/
- tests/test_eap_alarm_service.py
- tests/test_base_chunked_duckdb_job.py
- tests/test_async_query_job_service.py
- tests/integration/test_eap_alarm_rq_async.py
- tests/integration/test_eap_alarm_data_boundary.py
- tests/integration/test_eap_alarm_resilience.py
- tests/integration/test_oracle_arrow_pool_lifecycle.py
- tests/integration/test_rowcount_flag_parity.py
- tests/e2e/test_eap_alarm_e2e.py

### contract-reviewer
- specs/changes/eap-alarm-unified-job-poc/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/api/error-format.md
- contracts/CHANGELOG.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- .env.example

### stress-soak-engineer
- specs/changes/eap-alarm-unified-job-poc/
- tests/stress/test_async_job_stress.py
- tests/stress/test_chunk_boundary.py
- tests/integration/test_soak_workload.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py

### ci-cd-gatekeeper
- specs/changes/eap-alarm-unified-job-poc/
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/eap-alarm-unified-job-poc/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/core/base_chunked_duckdb_job.py
    - src/mes_dashboard/core/oracle_arrow_reader.py
  reason: Cross-change dependency documentation. These modules landed in `unified-query-core-infra` (P0, merged). EapAlarmJob must implement against their template-method signatures and connection-lifecycle API. Paths are explicitly included in Allowed Paths above.
  status: approved

## Approved Expansions
- CER-001: approved (paths pre-included in Allowed Paths; documents P0→P1 cross-change dependency)
