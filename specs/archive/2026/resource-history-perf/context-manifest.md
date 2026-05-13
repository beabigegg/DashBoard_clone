# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `src/mes_dashboard/services/resource_history_duckdb_cache.py` (new — DuckDB persistent cache)
- `src/mes_dashboard/services/resource_dataset_cache.py` (DuckDB routing in execute_primary_query + TTL bifurcation)
- `src/mes_dashboard/services/resource_history_service.py` (removed wrong prewarm code)
- `src/mes_dashboard/core/spool_warmup_scheduler.py` (removed warmup-resource-history job)
- `src/mes_dashboard/app.py` (startup wiring: start_duckdb_prewarm)
- `contracts/env/env-contract.md` (RESOURCE_HISTORY_HISTORICAL_TTL, RESOURCE_HISTORY_PREWARM_MONTHS, RESOURCE_HISTORY_DUCKDB_PATH)
- `contracts/ci/ci-gate-contract.md` (DuckDB prewarm gate)
- `tests/test_resource_history_duckdb_cache.py` (new)
- `tests/test_resource_history_service.py`
- `tests/test_cache_integration.py`
- `tests/test_resource_dataset_cache.py`

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
