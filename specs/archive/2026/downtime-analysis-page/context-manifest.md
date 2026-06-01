# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend: new downtime-analysis route + service + SQL + spool/cache
- frontend: new downtime-analysis Vue3 app + portal-shell registration
- contracts: API, data-shape, business-rules, css-inventory, CHANGELOG
- modernization-policy: page_status, asset_readiness, route_scope_matrix + hardening test
- reference: resource-history (architecture pattern to mirror)

## Allowed Paths
- specs/changes/downtime-analysis-page/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/app.py
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/downtime_analysis/
- src/mes_dashboard/sql/resource_history/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- frontend/src/downtime-analysis/
- frontend/src/resource-history/
- frontend/src/resource-shared/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/styles/tailwind.css
- frontend/src/portal-shell/nativeModuleRegistry.js
- frontend/src/portal-shell/routeContracts.js
- frontend/src/portal-shell/router.js
- frontend/src/portal-shell/sidebarState.js
- frontend/index.html
- frontend/vite.config.ts
- frontend/tailwind.config.js
- frontend/tsconfig.json
- frontend/package.json
- frontend/scripts/css-governance-check.js
- frontend/tests/playwright/
- frontend/tests/legacy/
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- docs/migration/full-modernization-architecture-blueprint/route_contracts.json
- tests/test_modernization_policy_hardening.py
- tests/test_api_contract.py
- tests/test_app_factory.py
- tests/e2e/test_resource_history_e2e.py
- tests/e2e/conftest.py
- tests/conftest.py

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

## Required Tests
- tests/test_modernization_policy_hardening.py (extend)
- tests/test_api_contract.py (extend)
- tests/e2e/test_downtime_analysis_e2e.py (NEW)
- frontend/tests/playwright/downtime-analysis.spec.js (NEW)
- tests/test_downtime_analysis_service.py (NEW)
- tests/test_downtime_analysis_routes.py (NEW)
- frontend/src/downtime-analysis/__tests__/ (NEW)

## Agent Work Packets

### spec-architect
- specs/changes/downtime-analysis-page/
- specs/context/project-map.md
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- src/mes_dashboard/sql/resource_history/

### contract-reviewer
- specs/changes/downtime-analysis-page/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/downtime-analysis-page/
- contracts/
- tests/test_resource_history_service.py
- tests/test_resource_history_routes.py
- tests/test_modernization_policy_hardening.py
- tests/e2e/test_resource_history_e2e.py
- frontend/tests/playwright/

### ci-cd-gatekeeper
- specs/changes/downtime-analysis-page/
- contracts/ci/ci-gate-contract.md
- .github/workflows/

### implementation-planner
- specs/changes/downtime-analysis-page/
- contracts/
- src/mes_dashboard/routes/resource_history_routes.py
- src/mes_dashboard/services/resource_history_service.py
- src/mes_dashboard/services/resource_dataset_cache.py
- frontend/src/resource-history/

### backend-engineer
- specs/changes/downtime-analysis-page/
- contracts/api/
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- src/mes_dashboard/app.py
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/
- src/mes_dashboard/core/
- src/mes_dashboard/config/
- tests/
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- docs/migration/full-modernization-architecture-blueprint/route_contracts.json

### frontend-engineer
- specs/changes/downtime-analysis-page/
- contracts/css/
- contracts/data/data-shape-contract.md
- contracts/api/api-contract.md
- frontend/src/downtime-analysis/
- frontend/src/resource-history/
- frontend/src/resource-shared/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/src/styles/tailwind.css
- frontend/src/portal-shell/nativeModuleRegistry.js
- frontend/src/portal-shell/routeContracts.js
- frontend/src/portal-shell/router.js
- frontend/src/portal-shell/sidebarState.js
- frontend/index.html
- frontend/vite.config.ts
- frontend/tailwind.config.js
- frontend/tsconfig.json
- frontend/package.json
- frontend/scripts/css-governance-check.js
- frontend/tests/playwright/
- frontend/tests/legacy/

### ui-ux-reviewer
- specs/changes/downtime-analysis-page/
- contracts/css/
- frontend/src/downtime-analysis/
- frontend/src/portal-shell/nativeModuleRegistry.js
- frontend/src/shared-ui/
- frontend/src/styles/tailwind.css

### visual-reviewer
- specs/changes/downtime-analysis-page/
- frontend/src/downtime-analysis/
- contracts/css/css-contract.md

### qa-reviewer
- specs/changes/downtime-analysis-page/
- contracts/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- frontend/src/downtime-analysis/
- tests/
- frontend/tests/playwright/

## Context Expansion Requests
-

## Approved Expansions
-
