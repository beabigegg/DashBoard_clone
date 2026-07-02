# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- backend report service + Oracle read path (new production-achievement service; `DW_MES_LOTWIPHISTORY`)
- backend persistence — direct MySQL (target-value table, permission-flag table) via `core/mysql_client.py`
- backend authorization (`core/permissions.py` — new independent gate)
- shared reuse (`services/filter_cache.py` `get_spec_workcenter_mapping()`)
- backend routes (new report + target-value + admin-permission endpoints)
- frontend new report app (`frontend/src/production-achievement/`) + portal-shell navigation/registry
- admin UI permission block (`frontend/src/admin-*`)
- migration/config manifests (`docs/migration/full-modernization-architecture-blueprint/*`, `data/page_status.json`)
- contracts (api, data, business, env, css, ci)

## Allowed Paths
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/config/
- src/mes_dashboard/sql/
- src/mes_dashboard/app.py
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json
- tests/

Note: `frontend/src/production-achievement/` is a new directory to be created (naming follows existing report-app convention: `production-history/`, `yield-alert-center/`).

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- tests/ (backend unit/contract/integration/resilience/data-boundary — new modules)
- tests/e2e/ (new production-achievement E2E)
- tests/integration/ (MySQL target/permission round-trip, `MYSQL_OPS_ENABLED` fallback)
- frontend/tests/ (new report app unit + validation)
- frontend/tests/playwright/ (new page + admin permission E2E; data-boundary dir for target-input malformed cases)

## Agent Work Packets

### change-classifier
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/api/api-contract.md
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/services/filter_cache.py

### implementation-planner
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md

### backend-engineer
- specs/changes/production-achievement-kanban/
- contracts/api/
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/config/
- src/mes_dashboard/sql/
- src/mes_dashboard/app.py
- tests/

### frontend-engineer
- specs/changes/production-achievement-kanban/
- contracts/css/
- contracts/api/api-contract.md
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json

### test-strategist
- specs/changes/production-achievement-kanban/
- tests/
- frontend/tests/

### contract-reviewer
- specs/changes/production-achievement-kanban/
- contracts/

### ui-ux-reviewer
- specs/changes/production-achievement-kanban/
- contracts/css/
- frontend/src/production-achievement/
- frontend/src/admin-pages/

### visual-reviewer
- specs/changes/production-achievement-kanban/
- contracts/css/
- frontend/src/production-achievement/

### qa-reviewer
- specs/changes/production-achievement-kanban/
- contracts/

### ci-cd-gatekeeper
- specs/changes/production-achievement-kanban/
- contracts/ci/ci-gate-contract.md
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/filter_cache.py
    - src/mes_dashboard/core/permissions.py
    - src/mes_dashboard/core/mysql_client.py
    - src/mes_dashboard/core/sync_worker.py
  reason: spec-architect and backend-engineer must read the exact signatures of `get_spec_workcenter_mapping()`, the existing `is_admin`/`admin_required` shape in `permissions.py`, the `mysql_client` connection/OPS API surface, and the `sync_worker` pattern being deviated from, to design the new gate and direct-MySQL path without guessing.
  status: approved
- request-id: CER-002
  requested_paths:
    - frontend/src/portal-shell/navigationManifest.js
    - frontend/src/portal-shell/nativeModuleRegistry.js
    - frontend/src/production-history/
  reason: frontend-engineer must read the existing 生產輔助 drawer entry and native-module mount gate to add the new page additively, and needs production-history as the reference report-page architecture (filter orchestration + DataTable/chart).
  status: approved

## Approved Expansions
- CER-001: approved — paths folded into Allowed Paths above.
- CER-002: approved — paths folded into Allowed Paths above.
