# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- routes: query_tool_routes.py, wip_routes.py (Path C elimination + rowcount pre-check)
- routes (ASYNC_DAY_THRESHOLD removal): downtime_analysis_routes.py, hold_history_routes.py, resource_history_routes.py
- services (ASYNC_DAY_THRESHOLD removal): hold_query_job_service.py, reject_query_job_service.py, resource_query_job_service.py
- core: global_concurrency.py (semaphore semantics), query_cost_policy.py (threshold policy)
- service: batch_query_engine.py (deprecation marker), async_query_job_service.py (RQ dispatch)
- architecture blueprint: docs/architecture/query-dataflow-unification.md

## Allowed Paths
- specs/changes/query-path-c-elimination-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/adr/
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/wip_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/feature_flags.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- .env.example
- tests/test_batch_query_engine.py
- tests/contract/
- tests/integration/
- tests/e2e/test_query_tool_e2e.py
- tests/e2e/test_wip_hold_pages_e2e.py
- tests/stress/
- tests/test_job_registry.py
- tests/test_query_cost_policy.py
- .github/workflows/backend-tests.yml
- .github/workflows/contract-driven-gates.yml

## Required Contracts
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/test_batch_query_engine.py
- tests/contract/ (env-pin tests for removed vars + QUERY_TOOL_USE_RQ)
- tests/integration/ (RQ async dispatch parity, worker-blocking-elimination)
- tests/e2e/test_query_tool_e2e.py
- tests/e2e/test_wip_hold_pages_e2e.py
- tests/stress/ (RQ Oracle-concurrency bound, no worker starvation)
- tests/test_job_registry.py
- tests/test_query_cost_policy.py

## Agent Work Packets

### spec-architect
- specs/changes/query-path-c-elimination-cleanup/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/architecture/service-patterns.md
- docs/adr/
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py

### implementation-planner
- specs/changes/query-path-c-elimination-cleanup/
- docs/architecture/query-dataflow-unification.md
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/services/batch_query_engine.py
- contracts/env/env-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/query-path-c-elimination-cleanup/
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/wip_service.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/services/hold_query_job_service.py
- src/mes_dashboard/services/reject_query_job_service.py
- src/mes_dashboard/services/resource_query_job_service.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/core/global_concurrency.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/feature_flags.py
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/business/business-rules.md
- .env.example

### contract-reviewer
- specs/changes/query-path-c-elimination-cleanup/
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md

### test-strategist
- specs/changes/query-path-c-elimination-cleanup/
- tests/test_batch_query_engine.py
- tests/contract/
- tests/integration/
- tests/test_job_registry.py
- tests/test_query_cost_policy.py

### stress-soak-engineer
- specs/changes/query-path-c-elimination-cleanup/
- tests/stress/
- src/mes_dashboard/core/global_concurrency.py

### ci-cd-gatekeeper
- specs/changes/query-path-c-elimination-cleanup/
- contracts/ci/ci-gate-contract.md
- .github/workflows/backend-tests.yml
- .github/workflows/contract-driven-gates.yml
- contracts/env/env-contract.md

### qa-reviewer
- specs/changes/query-path-c-elimination-cleanup/

## Context Expansion Requests
- CER-001 status: approved — no rq_utils.py exists; enqueue_query_job is in async_query_job_service.py (already in Allowed Paths)
- CER-002 status: approved — confirmed 4 ASYNC_DAY_THRESHOLD vars (DOWNTIME_, HOLD_, RESOURCE_, REJECT_); affected files added to Allowed Paths

## Approved Expansions
- CER-001: src/mes_dashboard/services/async_query_job_service.py (confirmed as enqueue_query_job location)
- CER-002: src/mes_dashboard/services/hold_query_job_service.py, src/mes_dashboard/services/reject_query_job_service.py, src/mes_dashboard/services/resource_query_job_service.py (ASYNC_DAY_THRESHOLD callers)
