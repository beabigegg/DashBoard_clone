# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces

- production-history backend route (`routes/production_history_routes.py`)
- production-history service (`services/production_history_service.py`, `services/production_history_sql_runtime.py`)
- production-history SQL templates (`sql/production_history/`)
- `container_filter_cache` service + Redis L2 schema
- production-history frontend app (`frontend/src/production-history/`)
- shared-ui / shared-composables (MultiSelect, multi-line input parser reuse from `material-trace`)
- Contracts: api, data, business, css (conditional), env (conditional), ci

## Allowed Paths

- specs/changes/prod-history-first-tier-cache-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/css/
- contracts/env/
- contracts/ci/
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/request_validation.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/loader.py
- frontend/src/production-history/
- frontend/src/material-trace/
- frontend/src/shared-ui/components/
- frontend/src/shared-ui/index.ts
- frontend/src/shared-composables/
- frontend/src/core/api.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/test_production_history_sql_runtime.py
- tests/test_container_filter_cache.py
- tests/test_common_filters.py
- tests/test_cache.py
- tests/test_cache_updater_lock_behavior.py
- tests/property/
- tests/routes/_fuzz_payloads.py
- tests/routes/test_fuzz_routes.py
- tests/integration/_multi_worker_harness.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_real_multi_worker.py
- tests/integration/test_redis_chaos.py
- tests/integration/test_redis_timeout_fallback.py
- tests/stress/
- tests/e2e/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/abort/
- frontend/tests/playwright/
- shared/field_contracts.json
- data/table_schema_info.json
- .github/workflows/

## Required Contracts

- contracts/api/api-contract.md (new filter-options endpoint + extended main-query params with wildcard semantics)
- contracts/data/data-shape-contract.md (filter-options response shape, cache payload schema version)
- contracts/business/business-rules.md (wildcard grammar, multi-line parser rules, cross-filter semantics)
- contracts/ci/ci-gate-contract.md (cache rollback + fuzz gate)
- contracts/css/css-contract.md (conditional — only if new UI classes introduced)
- contracts/env/env-contract.md (conditional — only if new env var introduced)

## Required Tests

- Unit: backend cache + wildcard parser + multi-line parser; frontend cross-filter loader
- Contract: api/data/business shape assertions
- Integration: cross-filter chains, cache hit/miss, lock contention, multi-worker (nightly real)
- E2E: Playwright cross-filter UX + multi-line paste + wildcard query
- Visual: filter rows layout, second-tier chip suppression
- Data-boundary: empty cache, stale-schema cache, PJ_FUNCTION null
- Resilience: Redis down, cache lock holder crash
- Fuzz/monkey: wildcard injection (mandatory)
- Stress: cache rebuild thundering herd, high-cardinality IN list

## Agent Work Packets

### change-classifier
- specs/changes/prod-history-first-tier-cache-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- contracts/api/
- contracts/data/
- contracts/business/

### contract-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/css/
- contracts/env/
- contracts/ci/
- shared/field_contracts.json

### test-strategist
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/api/
- contracts/data/
- contracts/business/
- tests/property/
- tests/routes/_fuzz_payloads.py
- tests/integration/_multi_worker_harness.py

### backend-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/services/reason_filter_cache.py
- src/mes_dashboard/services/material_trace_service.py
- src/mes_dashboard/services/resource_history_duckdb_cache.py
- src/mes_dashboard/core/cache.py
- src/mes_dashboard/core/cache_plane.py
- src/mes_dashboard/core/redis_client.py
- src/mes_dashboard/core/request_validation.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/loader.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/test_production_history_sql_runtime.py
- tests/test_container_filter_cache.py
- tests/test_common_filters.py
- tests/test_cache_updater_lock_behavior.py

### frontend-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/src/material-trace/
- frontend/src/shared-ui/components/
- frontend/src/shared-ui/index.ts
- frontend/src/shared-composables/
- frontend/src/core/api.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/abort/

### dependency-security-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/core/request_validation.py
- contracts/api/
- contracts/business/

### e2e-resilience-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- tests/e2e/
- tests/integration/_multi_worker_harness.py
- tests/integration/test_multi_worker_concurrency.py
- tests/integration/test_real_multi_worker.py
- tests/integration/test_redis_chaos.py
- tests/integration/test_redis_timeout_fallback.py
- frontend/tests/playwright/

### monkey-test-engineer
- specs/changes/prod-history-first-tier-cache-filters/
- tests/routes/_fuzz_payloads.py
- tests/routes/test_fuzz_routes.py
- tests/property/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/core/request_validation.py
- contracts/business/

### ui-ux-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- contracts/css/

### visual-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- frontend/src/production-history/
- frontend/tests/playwright/

### ci-cd-gatekeeper
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/ci/
- .github/workflows/

### qa-reviewer
- specs/changes/prod-history-first-tier-cache-filters/
- contracts/
- tests/
- frontend/tests/

## Context Expansion Requests

<!--
Agents must request context expansion instead of reading outside their work
packet. Format example for real requests:

- request-id: CER-001
  requested_paths:
    - src/example.ts
  reason: why this file is required
  status: pending
-->
-

## Approved Expansions
-
