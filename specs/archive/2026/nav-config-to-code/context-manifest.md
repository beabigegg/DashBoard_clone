# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend admin API + service layer: drawer CRUD removal, `PUT /api/pages` shrink to status-only, slimmed `GET /api/pages`, page status get/set on the shrunk store
- Frontend portal-shell navigation pipeline: code-manifest read replacing runtime drawer fetch
- Frontend admin-pages app: retire drawer create/edit/reorder/rename; status-toggle-only UI
- Writable data store: `data/page_status.json` → minimal `route → status` map
- Modernization manifests: `asset_readiness_manifest.json`, `route_scope_matrix.json`
- API / Data / CI contracts + contract samples; ADR / design record

## Allowed Paths
<!-- Directory-level union of paths any agent may read for this change. -->
- specs/changes/nav-config-to-code/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/portal-shell/
- frontend/src/admin-pages/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/services/page_registry.py
- src/mes_dashboard/app.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- docs/architecture/modernization-policy.md
- docs/adr/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/ci/
- contracts/CHANGELOG.md
- contracts/openapi.json
- tests/contract/
- tests/test_admin_routes.py
- tests/test_page_registry.py
- tests/test_app.py
- tests/test_app_factory.py
- tests/test_auth_integration.py
- frontend/tests/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md  (conditional — visibility-semantics wording only)
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Tests
- tests/test_admin_routes.py
- tests/contract/samples/get_admin_pages.json   (regenerate, slimmed)
- tests/contract/samples/get_admin_drawers.json  (retire)
- tests/contract/samples/delete_admin_drawers_id.json  (retire)
- tests/contract/test_schema_coverage.py
- tests/contract/test_manifest_completeness.py
- tests/contract/test_api_contract.py
- tests/contract/capture_samples.py
- tests/contract/response-samples.json
- frontend/tests/  (portal-shell navigation unit + admin-pages / portal-shell-login Playwright)

## Agent Work Packets
<!-- Documentation only — gate enforces Allowed Paths, not individual packets. -->

### spec-architect
- specs/changes/nav-config-to-code/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/portal-shell/
- frontend/src/admin-pages/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/services/page_registry.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- docs/architecture/modernization-policy.md
- docs/adr/
- contracts/api/
- contracts/data/

### contract-reviewer
- specs/changes/nav-config-to-code/
- contracts/api/
- contracts/data/
- contracts/business/
- contracts/ci/
- contracts/CHANGELOG.md
- contracts/openapi.json
- docs/migration/full-modernization-architecture-blueprint/

### test-strategist
- specs/changes/nav-config-to-code/
- tests/test_admin_routes.py
- tests/contract/
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/nav-config-to-code/
- contracts/ci/
- tests/contract/

### implementation-planner
- specs/changes/nav-config-to-code/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/ci/

### backend-engineer
- specs/changes/nav-config-to-code/
- src/mes_dashboard/routes/admin_routes.py
- src/mes_dashboard/services/page_registry.py
- data/page_status.json
- docs/migration/full-modernization-architecture-blueprint/
- contracts/openapi.json
- contracts/api/
- tests/test_admin_routes.py
- tests/contract/

### frontend-engineer
- specs/changes/nav-config-to-code/
- frontend/src/portal-shell/
- frontend/src/admin-pages/
- frontend/tests/

### ui-ux-reviewer
- specs/changes/nav-config-to-code/
- frontend/src/admin-pages/
- frontend/src/portal-shell/

### qa-reviewer
- specs/changes/nav-config-to-code/
- contracts/api/
- contracts/data/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/page_registry.py
  reason: Locate the service module owning drawer CRUD + page_status get/set (project-map truncated the services dir).
  status: approved

- request-id: CER-002
  requested_paths:
    - tests/contract/capture_samples.py
    - tests/contract/response-samples.json
  reason: Regenerating/retiring admin contract samples requires the capture harness + canonical sample registry.
  status: approved

- request-id: CER-003
  requested_paths:
    - src/mes_dashboard/app.py
  reason: >
  status: approved
## Approved Expansions
- CER-001 → src/mes_dashboard/services/page_registry.py (resolved; single confirmed owner)
- CER-002 → tests/contract/capture_samples.py, tests/contract/response-samples.json
- src/mes_dashboard/app.py
