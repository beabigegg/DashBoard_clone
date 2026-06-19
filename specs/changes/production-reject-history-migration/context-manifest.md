# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Production History query/job pipeline (service + job + route + sql_runtime)
- Reject History query/job pipeline (service + dataset cache + route)
- Shared async-job core (base_chunked_duckdb_job, query_cost_policy, job_registry, async_query_job_service, oracle_arrow_reader)
- Worker deployment (reject worker service unit; production worker if added)
- Contracts: env, business, ci, data-shape

## Allowed Paths
- specs/changes/production-reject-history-migration/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- deploy/mes-dashboard-reject-worker.service
- tests/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/adr/

## Required Contracts
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md

## Required Tests
- tests/test_base_chunked_duckdb_job.py
- tests/test_production_history*.py
- tests/test_reject_history*.py
- tests/test_async_query_job_service.py
- tests/integration/test_resource_history_rq_async.py (pattern reference)
- tests/integration/test_eap_alarm_rq_async.py (pattern reference)
- tests/stress/test_production_history_stress.py
- tests/stress/test_reject_history_stress.py
- tests/e2e/test_production_history_e2e.py
- tests/e2e/test_reject_history_e2e.py

## Agent Work Packets

### implementation-planner
- specs/changes/production-reject-history-migration/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/adr/
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/production-reject-history-migration/
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- deploy/mes-dashboard-reject-worker.service
- tests/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md

### test-strategist
- specs/changes/production-reject-history-migration/
- tests/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/core/base_chunked_duckdb_job.py

### contract-reviewer
- specs/changes/production-reject-history-migration/
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md

### ci-cd-gatekeeper
- specs/changes/production-reject-history-migration/
- contracts/ci/ci-gate-contract.md
- deploy/mes-dashboard-reject-worker.service
- tests/integration/
- tests/stress/

### qa-reviewer
- specs/changes/production-reject-history-migration/
- contracts/
- tests/

## Context Expansion Requests
-

## Approved Expansions
-
