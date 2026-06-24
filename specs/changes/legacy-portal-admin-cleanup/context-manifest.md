# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Backend portal entry route (`portal_index` / `/` in `app.py`) + its server-rendered templates (`portal.html` to delete)
- `PORTAL_SPA_ENABLED` flag's non-portal consumers (`modernization_policy`, status payload) — read-only preservation
- Frontend `admin-pages` module (dead-CSS removal + a11y)
- Backend tests covering portal render + app-factory route registration

## Allowed Paths
- specs/changes/legacy-portal-admin-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/app.py
- src/mes_dashboard/templates/
- src/mes_dashboard/core/modernization_policy.py
- frontend/src/admin-pages/
- tests/test_template_integration.py
- tests/test_portal_shell_routes.py
- tests/test_hold_routes.py
- tests/test_yield_alert_shell_coverage.py
- tests/test_app_factory.py
- docs/adr/0012-navigation-source-of-truth-code-manifest.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/css/css-inventory.md

## Required Contracts
- none expected (read-only no-change confirmation only): contracts/env/env-contract.md, contracts/env/env.schema.json, contracts/css/css-inventory.md

## Required Tests
- tests/test_template_integration.py (remove portal.html render tests)
- tests/test_portal_shell_routes.py (remove PORTAL_SPA_ENABLED=false branch)
- tests/test_hold_routes.py (remove PORTAL_SPA_ENABLED=false branch)
- tests/test_yield_alert_shell_coverage.py (remove PORTAL_SPA_ENABLED=false branch)
- tests/test_app_factory.py (keep/strengthen: `/` registers under name `portal_index`)
- frontend/src/admin-pages/ (vitest a11y assertions)

## Agent Work Packets
<!-- Documentation only — gate enforces Allowed Paths, not individual packets. -->

### spec-architect
- specs/changes/legacy-portal-admin-cleanup/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/app.py
- src/mes_dashboard/templates/
- src/mes_dashboard/core/modernization_policy.py
- docs/adr/0012-navigation-source-of-truth-code-manifest.md

### implementation-planner
- specs/changes/legacy-portal-admin-cleanup/
- src/mes_dashboard/app.py
- src/mes_dashboard/templates/
- src/mes_dashboard/core/modernization_policy.py
- frontend/src/admin-pages/
- tests/test_template_integration.py
- tests/test_portal_shell_routes.py
- tests/test_hold_routes.py
- tests/test_yield_alert_shell_coverage.py
- tests/test_app_factory.py

### backend-engineer
- specs/changes/legacy-portal-admin-cleanup/
- src/mes_dashboard/app.py
- src/mes_dashboard/templates/
- src/mes_dashboard/core/modernization_policy.py
- tests/test_template_integration.py
- tests/test_portal_shell_routes.py
- tests/test_hold_routes.py
- tests/test_yield_alert_shell_coverage.py
- tests/test_app_factory.py

### frontend-engineer
- specs/changes/legacy-portal-admin-cleanup/
- frontend/src/admin-pages/

### test-strategist
- specs/changes/legacy-portal-admin-cleanup/
- tests/test_template_integration.py
- tests/test_portal_shell_routes.py
- tests/test_hold_routes.py
- tests/test_yield_alert_shell_coverage.py
- tests/test_app_factory.py
- frontend/src/admin-pages/

### contract-reviewer
- specs/changes/legacy-portal-admin-cleanup/
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/css/css-inventory.md
- src/mes_dashboard/app.py

### ui-ux-reviewer
- specs/changes/legacy-portal-admin-cleanup/
- frontend/src/admin-pages/

### ci-cd-gatekeeper
- specs/changes/legacy-portal-admin-cleanup/

### qa-reviewer
- specs/changes/legacy-portal-admin-cleanup/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
    - docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
  reason: Only if spec-architect finds that removing portal.html / the non-SPA render path touches a tracked modernization manifest. Default assumption is it does NOT (portal.html is the legacy home, not a tracked report page).
  status: resolved
  resolution: spec-architect confirmed NO manifest touch (portal.html is the legacy home, not a tracked report page); paths not read.

## Approved Expansions
-
