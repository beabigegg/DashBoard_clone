# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `src/mes_dashboard/services/resource_history_service.py` (pre-warm method + TTL logic)
- `src/mes_dashboard/routes/resource_history_routes.py` (new progress endpoint)
- `src/mes_dashboard/core/cache.py` (or `cache_plane.py` — TTL assignment)
- `src/mes_dashboard/core/spool_warmup_scheduler.py` (reference for async startup pattern)
- `src/mes_dashboard/services/batch_query_engine.py` (query_id lifecycle reference)
- `src/mes_dashboard/services/async_query_job_service.py` (query_id generation reference)
- `frontend/src/resource-history/App.vue` (progress bar + polling loop)
- `frontend/src/shared-composables/useAsyncJobPolling.ts` (reuse candidate)
- `contracts/api/api-contract.md` (new endpoint)
- `contracts/api/api-inventory.md` (new endpoint registration)
- `contracts/data/data-shape-contract.md` (progress response shape)
- `contracts/env/env-contract.md` (new env vars if added)
- `contracts/ci/ci-gate-contract.md` (integration test gate)
- `tests/test_resource_history_service.py`
- `tests/test_resource_history_routes.py`
- `tests/test_cache_integration.py`
- `tests/e2e/test_resource_history_e2e.py`
- `tests/e2e/test_resource_history_browser_e2e.py`
- `tests/stress/test_resource_history_stress.py`
- `tests/integration/test_redis_chaos.py`
- `frontend/tests/legacy/resource-history.test.js`

## Allowed Paths
- specs/changes/resource-history-perf/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/async_query_job_service.py
- frontend/src/resource-history/
- frontend/src/shared-composables/useAsyncJobPolling.ts
- contracts/api/
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py
- tests/test_cache_integration.py
- tests/test_api_contract.py
- tests/e2e/test_resource_history_e2e.py
- tests/e2e/test_resource_history_browser_e2e.py
- tests/stress/test_resource_history_stress.py
- tests/integration/test_redis_chaos.py
- frontend/tests/legacy/resource-history.test.js

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py
- tests/test_cache_integration.py
- tests/test_api_contract.py
- tests/e2e/test_resource_history_e2e.py
- tests/e2e/test_resource_history_browser_e2e.py
- tests/stress/test_resource_history_stress.py
- tests/integration/test_redis_chaos.py
- frontend/tests/legacy/resource-history.test.js

## Agent Work Packets

### change-classifier
- specs/changes/resource-history-perf/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/resource-history-perf/
- contracts/api/
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### spec-architect
- specs/changes/resource-history-perf/
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/async_query_job_service.py

### test-strategist
- specs/changes/resource-history-perf/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/routes/resource_history_routes.py
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py
- tests/test_cache_integration.py

### backend-engineer
- specs/changes/resource-history-perf/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/services/batch_query_engine.py
- src/mes_dashboard/services/async_query_job_service.py
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py
- tests/test_cache_integration.py

### frontend-engineer
- specs/changes/resource-history-perf/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- frontend/src/resource-history/
- frontend/src/shared-composables/useAsyncJobPolling.ts

### ci-cd-gatekeeper
- specs/changes/resource-history-perf/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/resource-history-perf/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/routes/resource_history_routes.py
- frontend/src/resource-history/App.vue
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py

## Context Expansion Requests
-

## Approved Expansions
-
