# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Playwright E2E test layer (frontend/tests/playwright/)
- Shared auth/navigation helpers (frontend/tests/playwright/_auth.js)

## Allowed Paths
- specs/changes/fix-e2e-spec-failures/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/tests/playwright/
- frontend/playwright.config.js
- frontend/src/production-history/App.vue
- frontend/src/portal-shell/App.vue
- frontend/src/portal-shell/sidebarState.js
- frontend/src/wip-overview/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

## Required Contracts
- none

## Required Tests
- frontend/tests/playwright/ (all 9 affected spec files must pass)

## Agent Work Packets

### implementation-planner
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/

### bug-fix-engineer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/
- frontend/src/production-history/App.vue
- frontend/src/portal-shell/App.vue
- frontend/src/wip-overview/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

### e2e-resilience-engineer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/
- frontend/src/reject-history/
- src/mes_dashboard/routes/reject_history_routes.py

### test-strategist
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/

### ci-cd-gatekeeper
- specs/changes/fix-e2e-spec-failures/
- frontend/playwright.config.js

### qa-reviewer
- specs/changes/fix-e2e-spec-failures/
- frontend/tests/playwright/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - frontend/src/production-history/App.vue
    - frontend/src/portal-shell/App.vue
    - frontend/src/portal-shell/sidebarState.js
    - frontend/src/wip-overview/
  reason: Group A/B/D fixes depend on exact data-testid (ph-query-btn), sidebar-toggle markup, and WIP matrix render-gating condition
  status: approved

- request-id: CER-002
  requested_paths:
    - frontend/src/reject-history/
    - src/mes_dashboard/routes/reject_history_routes.py
  reason: Group F mock conversion requires matching the route's actual success_response wrapper key and response shape
  status: approved

## Approved Expansions
- CER-001: approved — paths added to Allowed Paths above
- CER-002: approved — paths added to Allowed Paths above
