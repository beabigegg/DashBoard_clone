# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- mid-section-defect (backend route + service)
- mid-section-defect (frontend app: App.vue, FilterBar)
- shared filter infrastructure (`container_filter_cache`, production-history cross-filter pattern as reference)

## Allowed Paths
- specs/changes/msd-type-package-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/mid_section_defect_routes.py
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/sql/mid_section_defect/
- frontend/src/mid-section-defect/
- frontend/src/production-history/composables/
- frontend/src/shared-ui/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- tests/test_mid_section_defect_service.py
- tests/test_container_filter_cache.py
- tests/contract/
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md (only if new authored CSS source is added)

## Required Tests
- tests/test_mid_section_defect_service.py
- tests/test_container_filter_cache.py
- tests/contract/
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts

## Agent Work Packets

### contract-reviewer
- specs/changes/msd-type-package-filter/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md

### test-strategist
- specs/changes/msd-type-package-filter/
- tests/test_mid_section_defect_service.py
- tests/test_container_filter_cache.py
- tests/contract/
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/playwright/mid-section-defect.spec.ts

### implementation-planner
- specs/changes/msd-type-package-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### backend-engineer
- specs/changes/msd-type-package-filter/
- src/mes_dashboard/routes/mid_section_defect_routes.py
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/container_filter_cache.py
- src/mes_dashboard/sql/mid_section_defect/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- tests/test_mid_section_defect_service.py
- tests/test_container_filter_cache.py
- tests/contract/

### frontend-engineer
- specs/changes/msd-type-package-filter/
- frontend/src/mid-section-defect/
- frontend/src/production-history/composables/
- frontend/src/shared-ui/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts

### ui-ux-reviewer
- specs/changes/msd-type-package-filter/
- frontend/src/mid-section-defect/
- contracts/css/css-contract.md

### visual-reviewer
- specs/changes/msd-type-package-filter/
- frontend/src/mid-section-defect/

### qa-reviewer
- specs/changes/msd-type-package-filter/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/msd_duckdb_runtime.py
  reason: detection DataFrame may be materialized in the msd duckdb runtime rather than the service module; needed to locate the post-query filter insertion point if not in mid_section_defect_service.py
  status: resolved-not-needed

## Approved Expansions
-
