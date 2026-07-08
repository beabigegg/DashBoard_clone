# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Admin UI surface — `admin-dashboard` app (target), `admin-pages` app (source), `admin-shared` (shared components/composables)

## Allowed Paths
- specs/changes/move-target-permissions-panel/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/
- contracts/api/

## Required Contracts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/api/api-contract.md (read-only confirmation of no change)

## Required Tests
- frontend/tests/legacy/admin-dashboard.test.js
- frontend/tests/playwright/admin-dashboard.spec.ts
- frontend/tests/playwright/admin-pages.spec.ts

## Agent Work Packets

### change-classifier
- specs/changes/move-target-permissions-panel/
- specs/context/project-map.md
- specs/context/contracts-index.md

### implementation-planner
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- contracts/css/
- contracts/api/

### frontend-engineer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/

### contract-reviewer
- specs/changes/move-target-permissions-panel/
- contracts/css/
- contracts/api/

### ui-ux-reviewer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/

### visual-reviewer
- specs/changes/move-target-permissions-panel/
- frontend/src/admin-dashboard/

### test-strategist
- specs/changes/move-target-permissions-panel/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/css/
- contracts/api/

### qa-reviewer
- specs/changes/move-target-permissions-panel/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - frontend/src/portal-shell/routeContracts.js
    - frontend/src/portal-shell/navigationManifest.js
    - frontend/src/portal-shell/nativeModuleRegistry.js
    - docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
    - docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
  reason: Only needed IF implementation-planner determines the new tab requires route/manifest touchpoints. The change-request states a new tab is NOT a new route and manifest edits should be avoided; request stays pending unless the planner confirms a wiring need.
  status: not-needed
  resolution: implementation-planner's DECISION-4 confirmed a new tab inside an existing SPA is not a new route — no route/manifest wiring required. No agent read these paths.

## Approved Expansions
- none required (CER-001 resolved as not-needed)
