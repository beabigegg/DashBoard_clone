# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- resource-status feature page (frontend `resource-status` app + backend resource services/routes/cache)

## Allowed Paths
- specs/changes/resource-status-package-group/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/CHANGELOG.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_service.py
- src/mes_dashboard/routes/resource_routes.py
- frontend/src/resource-status/
- frontend/src/resource-shared/
- frontend/src/shared-ui/components/
- frontend/src/core/
- tests/test_resource_cache.py
- tests/test_resource_service.py
- tests/test_resource_routes.py
- frontend/tests/legacy/resource-status.test.js

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md

## Required Tests
- tests/test_resource_cache.py
- tests/test_resource_service.py
- tests/test_resource_routes.py
- frontend/tests/legacy/resource-status.test.js

## Agent Work Packets

### contract-reviewer
- specs/changes/resource-status-package-group/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- src/mes_dashboard/services/resource_service.py
- src/mes_dashboard/routes/resource_routes.py

### test-strategist
- specs/changes/resource-status-package-group/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- tests/test_resource_cache.py
- tests/test_resource_service.py
- tests/test_resource_routes.py
- frontend/tests/legacy/resource-status.test.js

### ci-cd-gatekeeper
- specs/changes/resource-status-package-group/
- specs/context/project-map.md
- contracts/

### implementation-planner
- specs/changes/resource-status-package-group/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_service.py
- src/mes_dashboard/routes/resource_routes.py
- frontend/src/resource-status/
- tests/test_resource_cache.py
- tests/test_resource_service.py
- tests/test_resource_routes.py

### backend-engineer
- specs/changes/resource-status-package-group/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/resource_cache.py
- src/mes_dashboard/services/resource_service.py
- src/mes_dashboard/routes/resource_routes.py
- tests/test_resource_cache.py
- tests/test_resource_service.py
- tests/test_resource_routes.py

### frontend-engineer
- specs/changes/resource-status-package-group/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/api/api-contract.md
- frontend/src/resource-status/
- frontend/src/resource-shared/
- frontend/src/shared-ui/components/
- frontend/src/core/
- frontend/tests/legacy/resource-status.test.js

### ui-ux-reviewer
- specs/changes/resource-status-package-group/
- contracts/css/css-contract.md
- frontend/src/resource-status/

### qa-reviewer
- specs/changes/resource-status-package-group/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - tests/test_resource_service.py
    - tests/test_resource_routes.py
    - tests/test_resource_cache.py
  reason: Exact backend unit-test files for resource_service / resource_routes / resource_cache needed to verify snapshot-path and Oracle-path coverage for the new `package_groups` filter kwarg.
  status: approved (files confirmed at path)

- request-id: CER-002
  requested_paths:
    - frontend/src/resource-status/components/
  reason: Component filenames (FilterBar.vue, EquipmentCard.vue, MatrixSection.vue) needed before frontend-engineer begins.
  status: approved (confirmed: FilterBar.vue, EquipmentCard.vue, MatrixSection.vue, EquipmentGrid.vue, FloatingTooltip.vue, StatusHeader.vue)

## Approved Expansions
- CER-001: tests/test_resource_service.py, tests/test_resource_routes.py, tests/test_resource_cache.py
- CER-002: frontend/src/resource-status/components/
