# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- WIP detail async query path (sync↔RQ routing at L3 threshold)
- RQ worker registration + global concurrency slot (Oracle-bound)
- Dead-code removal: `merge_chunks` in WIP service

## Allowed Paths
- specs/changes/wip-rq-worker-chunks-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/rq_worker_preload.py
- deploy/
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_redis_timeout_fallback.py
- tests/integration/test_soak_workload.py
- tests/stress/test_rq_semaphore_stress.py
- tests/test_job_registry.py
- tests/test_query_cost_policy.py
- frontend/tests/playwright/
- docs/adr/0011-global-concurrency-semaphore-rq-oracle-bound.md
- docs/adr/0006-duckdb-prewarm-via-rq-queue.md
- docs/architecture/service-patterns.md
- docs/architecture/cache-spool-patterns.md
- .github/workflows/

## Required Contracts
- contracts/api/api-contract.md (WIP detail async 202 routing)
- contracts/env/env-contract.md + contracts/env/env.schema.json (conditional: only if new RQ feature flag introduced)

## Required Tests
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/integration/test_redis_timeout_fallback.py
- tests/stress/test_rq_semaphore_stress.py
- tests/integration/test_soak_workload.py
- tests/test_job_registry.py
- tests/test_query_cost_policy.py

## Agent Work Packets

### spec-architect
- specs/changes/wip-rq-worker-chunks-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/env/env-contract.md
- docs/adr/0011-global-concurrency-semaphore-rq-oracle-bound.md
- docs/adr/0006-duckdb-prewarm-via-rq-queue.md
- docs/architecture/service-patterns.md
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/routes/wip_routes.py

### contract-reviewer
- specs/changes/wip-rq-worker-chunks-cleanup/
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/env/env-contract.md
- contracts/env/env.schema.json

### test-strategist
- specs/changes/wip-rq-worker-chunks-cleanup/
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/integration/test_redis_timeout_fallback.py
- tests/test_job_registry.py
- tests/test_query_cost_policy.py
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

### ci-cd-gatekeeper
- specs/changes/wip-rq-worker-chunks-cleanup/
- contracts/ci/ci-gate-contract.md
- .github/workflows/

### implementation-planner
- specs/changes/wip-rq-worker-chunks-cleanup/
- contracts/api/api-contract.md
- contracts/env/env-contract.md
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/sql/wip/

### backend-engineer
- specs/changes/wip-rq-worker-chunks-cleanup/
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/
- src/mes_dashboard/workers/
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/rq_worker_preload.py
- deploy/
- tests/integration/test_wip_rowcount_rq_routing.py
- tests/integration/test_rq_semaphore_wiring.py
- tests/test_job_registry.py
- tests/test_query_cost_policy.py

### e2e-resilience-engineer
- specs/changes/wip-rq-worker-chunks-cleanup/
- tests/integration/test_redis_timeout_fallback.py
- frontend/tests/playwright/
- src/mes_dashboard/routes/wip_routes.py

### stress-soak-engineer
- specs/changes/wip-rq-worker-chunks-cleanup/
- tests/stress/test_rq_semaphore_stress.py
- tests/integration/test_soak_workload.py
- tests/integration/test_multi_worker_concurrency.py
- src/mes_dashboard/core/global_concurrency.py

### qa-reviewer
- specs/changes/wip-rq-worker-chunks-cleanup/
- contracts/api/api-contract.md

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/wip_service.py
    - src/mes_dashboard/services/wip_query_job_service.py
  reason: project-map.md truncates `services/` at cap=50; exact WIP service file hosting `merge_chunks` and existence/name of WIP async job-service module cannot be confirmed from index. Already covered by directory-level path `src/mes_dashboard/services/` in Allowed Paths — resolved implicitly.
  status: resolved (covered by src/mes_dashboard/services/ directory path)

## Approved Expansions
- CER-001: src/mes_dashboard/services/ directory path covers all WIP service files including wip_service.py and any wip_query_job_service.py
