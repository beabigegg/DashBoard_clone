# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- resource-history caching (Redis spool key strategy + background warmup)
- shared spool/warmup infrastructure (read/verify only)

## Allowed Paths
- specs/changes/resource-history-cache-fix/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/resource_history/
- contracts/env/env-contract.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- docs/cache-strategy.md
- docs/adr/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_service.py
- tests/test_resource_history_sql_parity.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/

## Required Contracts
- contracts/api/api-contract.md (read-only verification: shape unchanged)
- contracts/data/data-shape-contract.md (read-only verification: source columns unchanged)
- contracts/env/env-contract.md (conditional: update if Phase 2 TTL env var is added)
- contracts/business/business-rules.md (review for any cache-strategy invariant)

## Required Tests
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_sql_runtime.py
- tests/test_resource_history_routes.py
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/integration/

## Agent Work Packets

### spec-architect
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/spool_warmup_scheduler.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- docs/cache-strategy.md
- docs/adr/

### contract-reviewer
- specs/changes/resource-history-cache-fix/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/resource-history-cache-fix/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/

### ci-cd-gatekeeper
- specs/changes/resource-history-cache-fix/
- .github/workflows/

### implementation-planner
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py

### backend-engineer
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/services/resource_history_sql_runtime.py
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/redis_df_store.py
- src/mes_dashboard/sql/resource_history/
- tests/test_resource_cache.py
- tests/test_resource_cache_version_check.py
- tests/test_resource_dataset_cache.py
- tests/test_resource_history_duckdb_cache.py
- tests/test_resource_history_routes.py
- tests/test_resource_history_sql_runtime.py
- tests/integration/
- contracts/env/env-contract.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/resource-history-cache-fix/
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/routes/resource_history_routes.py
- tests/integration/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - tests/test_resource_dataset_cache.py
    - tests/test_resource_history_sql_runtime.py
    - tests/test_resource_history_routes.py
  reason: Confirm exact test file paths before backend-engineer/test-strategist edit them
  status: approved (confirmed via ls tests/ — files exist)

- request-id: CER-002
  requested_paths:
    - docs/adr/0001-material-consumption-summary-spool-granularity-key.md
  reason: Precedent ADR for spool-granularity key decisions; spec-architect should reference it
  status: approved (confirmed via ls docs/adr/ — file exists)

## Approved Expansions
- CER-001: test file paths confirmed
- CER-002: ADR-0001 confirmed at docs/adr/0001-material-consumption-summary-spool-granularity-key.md
