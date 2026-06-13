# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- downtime-analysis backend (routes + services + cache + SQL)
- downtime-analysis frontend feature app
- shared frontend DuckDB infrastructure (frontend/src/core/ — read-only reuse)
- spool / data-shape boundary (raw parquet)
- API, data-shape, business-rules contracts (+ conditional env/ci/css)

## Allowed Paths
- specs/changes/downtime-browser-duckdb/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_dataset_cache.py
- frontend/src/downtime-analysis/
- frontend/src/core/duckdb-client.ts
- frontend/src/core/duckdb-activation-policy.ts
- frontend/src/workers/duckdb-worker.js
- frontend/src/resource-history/useResourceHistoryDuckDB.ts
- tests/test_downtime_analysis_routes.py
- tests/test_downtime_analysis_service.py
- tests/e2e/test_downtime_analysis_e2e.py
- tests/e2e/test_resource_history_browser_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js
- tests/stress/test_resource_history_stress.py
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- docs/adr/0002-downtime-analysis-spool-namespace.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md
- contracts/env/env-contract.md (conditional)
- contracts/ci/ci-gate-contract.md (conditional)

## Required Tests
- tests/test_downtime_analysis_routes.py
- tests/test_downtime_analysis_service.py
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js
- frontend/src/downtime-analysis/__tests__/ (parity tests — new)

## Agent Work Packets

### spec-architect
- specs/changes/downtime-browser-duckdb/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/sql/downtime_analysis/
- frontend/src/resource-history/useResourceHistoryDuckDB.ts
- src/mes_dashboard/services/resource_dataset_cache.py
- docs/adr/0002-downtime-analysis-spool-namespace.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### contract-reviewer
- specs/changes/downtime-browser-duckdb/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/env/env-contract.md
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/downtime-browser-duckdb/
- tests/test_downtime_analysis_routes.py
- tests/test_downtime_analysis_service.py
- tests/e2e/test_downtime_analysis_e2e.py
- tests/e2e/test_resource_history_browser_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js
- tests/stress/test_resource_history_stress.py

### ci-cd-gatekeeper
- specs/changes/downtime-browser-duckdb/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### implementation-planner
- specs/changes/downtime-browser-duckdb/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/downtime-browser-duckdb/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/downtime_analysis_duckdb_cache.py
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/services/resource_dataset_cache.py
- tests/test_downtime_analysis_routes.py
- tests/test_downtime_analysis_service.py
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/CHANGELOG.md

### frontend-engineer
- specs/changes/downtime-browser-duckdb/
- frontend/src/downtime-analysis/
- frontend/src/core/duckdb-client.ts
- frontend/src/core/duckdb-activation-policy.ts
- frontend/src/workers/duckdb-worker.js
- frontend/src/resource-history/useResourceHistoryDuckDB.ts
- frontend/tests/playwright/downtime-analysis.spec.js

### e2e-resilience-engineer
- specs/changes/downtime-browser-duckdb/
- tests/e2e/test_downtime_analysis_e2e.py
- tests/e2e/test_resource_history_browser_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js
- frontend/src/downtime-analysis/

### stress-soak-engineer
- specs/changes/downtime-browser-duckdb/
- tests/stress/test_resource_history_stress.py
- src/mes_dashboard/services/downtime_analysis_service.py

### ui-ux-reviewer
- specs/changes/downtime-browser-duckdb/
- frontend/src/downtime-analysis/

### visual-reviewer
- specs/changes/downtime-browser-duckdb/
- frontend/src/downtime-analysis/

### qa-reviewer
- specs/changes/downtime-browser-duckdb/
- tests/test_downtime_analysis_routes.py
- tests/test_downtime_analysis_service.py
- tests/e2e/test_downtime_analysis_e2e.py
- frontend/tests/playwright/downtime-analysis.spec.js

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/
  reason: project-map truncated services directory (21 entries omitted); spec-architect/backend-engineer may need exact current export/CSV helper and `load_downtime_events` definition site; request specific files once identified rather than opening whole directory
  status: pending

- request-id: CER-002
  requested_paths:
    - frontend/src/downtime-analysis/composables/
    - frontend/src/downtime-analysis/components/
  reason: project-map shows these subtrees at max-depth; frontend-engineer needs existing composable/component file names to know which to replace; these are under the already-allowed `frontend/src/downtime-analysis/` root
  status: pending

## Approved Expansions
-
