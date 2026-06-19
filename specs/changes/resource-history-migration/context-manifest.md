# Context Manifest

## Change ID: resource-history-migration

This manifest defines the approved context boundaries for agents working on this change.
The forbidden-paths baseline lives in `.cdd/context-policy.json` and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- resource-history query execution engine (services + worker job)
- shared chunked-job core (base_chunked_duckdb_job, query_cost_policy, job_registry)
- env / business / data-shape / ci contracts
- async RQ worker dispatch (routing already exists; engine swapped)

## Allowed Paths
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
- src/mes_dashboard/services/resource_query_job_service.py
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
- tests/test_resource_history_unified_job.py
- tests/integration/test_resource_history_rq_async.py

## Approved Context Expansions
(none yet)

## Context Expansion Requests
(none pending)
