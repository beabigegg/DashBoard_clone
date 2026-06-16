# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- hold-overview report page (frontend Vue app + backend route/service)
- `/api/hold-overview/lots` API endpoint (export / full-data mode)
- CSV data-export boundary

## Allowed Paths
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-overview/
- frontend/src/hold-history/
- frontend/src/core/post-export.ts
- frontend/src/core/
- frontend/src/query-tool/components/
- frontend/src/shared-ui/
- frontend/tests/
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- src/mes_dashboard/routes/hold_overview_routes.py
- src/mes_dashboard/services/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- contracts/env/env-contract.md
- tests/contract/samples/
- tests/stress/

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md (conditional — only if new authored CSS)

## Required Tests
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- tests/contract/samples/
- tests/stress/ (bounded large-result test, conditional)

## Agent Work Packets

### change-classifier
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md

### implementation-planner
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

### backend-engineer
- specs/changes/hold-overview-export-csv/
- src/mes_dashboard/routes/hold_overview_routes.py
- src/mes_dashboard/services/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- tests/contract/samples/
- tests/stress/

### frontend-engineer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/
- frontend/src/core/post-export.ts
- frontend/src/core/
- frontend/src/query-tool/components/
- frontend/src/shared-ui/
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### contract-reviewer
- specs/changes/hold-overview-export-csv/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/hold-overview-export-csv/
- frontend/tests/
- tests/contract/samples/
- tests/stress/

### ui-ux-reviewer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/
- contracts/css/css-contract.md

### visual-reviewer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/

### qa-reviewer
- specs/changes/hold-overview-export-csv/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - frontend/src/hold-overview/components/
    - frontend/src/hold-history/components/
  reason: The project-map truncates these component directories at max depth, so the exact DetailTable / card-header component files that host the table and the export button are not enumerable from the index. Implementation needs the precise component file paths to place the button and reuse the hold-history CSV helpers.
  status: approved

- request-id: CER-002
  requested_paths:
    - contracts/env/env-contract.md
  reason: Backend-engineer needs to add HOLD_OVERVIEW_EXPORT_MAX_ROWS env var entry to the env contract.
  status: approved

## Approved Expansions
- CER-001: frontend/src/hold-overview/components/, frontend/src/hold-history/components/ (approved — button lives in App.vue, components dirs needed for reference)
- CER-002: contracts/env/env-contract.md (approved — HOLD_OVERVIEW_EXPORT_MAX_ROWS must be documented)
