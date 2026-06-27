# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend: routes + services (new db-scheduling read-only query over DWH.DW_MES_LOT_V)
- frontend: new db-scheduling Vue app + portal-shell navigation (new drawer order 7)
- contracts: api, data-shape, business-rules, css-inventory

## Allowed Paths
- specs/changes/add-db-scheduling-page/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/response.py
- src/mes_dashboard/core/database.py
- src/mes_dashboard/app.py
- frontend/src/db-scheduling/
- frontend/src/portal-shell/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/
- tests/
- data/page_status.json
- docs/migration/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-inventory.md

## Required Tests
- tests/ (backend unit/contract/integration for db-scheduling)
- frontend/tests/playwright/ (db-scheduling E2E spec)
- tests/contract/samples/ (new endpoint sample)

## Agent Work Packets

### change-classifier
- specs/changes/add-db-scheduling-page/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/add-db-scheduling-page/
- contracts/

### test-strategist
- specs/changes/add-db-scheduling-page/
- tests/
- frontend/tests/
- tests/contract/samples/

### spec-architect
- specs/changes/add-db-scheduling-page/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/
- src/mes_dashboard/core/database.py

### ci-cd-gatekeeper
- specs/changes/add-db-scheduling-page/
- contracts/

### implementation-planner
- specs/changes/add-db-scheduling-page/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### backend-engineer
- specs/changes/add-db-scheduling-page/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/response.py
- src/mes_dashboard/core/database.py
- src/mes_dashboard/app.py
- tests/

### frontend-engineer
- specs/changes/add-db-scheduling-page/
- contracts/css/css-inventory.md
- frontend/src/db-scheduling/
- frontend/src/portal-shell/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/
- data/page_status.json
- docs/migration/

### ui-ux-reviewer
- specs/changes/add-db-scheduling-page/
- frontend/src/db-scheduling/
- frontend/src/portal-shell/
- contracts/css/css-inventory.md

### visual-reviewer
- specs/changes/add-db-scheduling-page/
- frontend/src/db-scheduling/

### qa-reviewer
- specs/changes/add-db-scheduling-page/
- contracts/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/wip_service.py
    - src/mes_dashboard/core/database.py
  reason: Confirm how DWH.DW_MES_LOT_V is queried / cached for WIP; spec-architect and backend-engineer need this to decide cache-vs-Oracle data-flow.
  status: approved

- request-id: CER-002
  requested_paths:
    - frontend/src/portal-shell/navigationManifest.js
    - frontend/src/portal-shell/nativeModuleRegistry.js
    - frontend/src/portal-shell/router.js
  reason: frontend-engineer needs exact manifest/router registration shape to add 生產輔助 drawer at order 7 and /db-scheduling route.
  status: approved

## Approved Expansions
- CER-001: src/mes_dashboard/services/wip_service.py, src/mes_dashboard/core/database.py
- CER-002: frontend/src/portal-shell/navigationManifest.js, frontend/src/portal-shell/nativeModuleRegistry.js, frontend/src/portal-shell/router.js
