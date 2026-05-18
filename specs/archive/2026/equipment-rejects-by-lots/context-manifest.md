# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- query-tool feature (frontend app + backend service + SQL template)
- equipment-period API endpoint (query_type='rejects' branch)
- export CSV pipeline (equipment_rejects type)
- contracts: api, data-shape, business-rules

## Allowed Paths
- specs/changes/equipment-rejects-by-lots/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/sql/query_tool/
- frontend/src/query-tool/
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- frontend/src/shared-ui/
- frontend/tests/query-tool/
- frontend/tests/playwright/query-tool.spec.js
- frontend/tests/playwright/query-tool-url-state.spec.js
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/abort/query-tool-abort.test.js
- tests/e2e/test_query_tool_e2e.py
- tests/e2e/test_query_tool_ui_ux_e2e.py
- shared/field_contracts.json
- tests/

## Required Contracts
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/api/api-inventory.md

## Required Tests
- tests/e2e/test_query_tool_e2e.py
- tests/e2e/test_query_tool_ui_ux_e2e.py
- frontend/tests/query-tool/
- frontend/tests/playwright/query-tool.spec.js
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/abort/query-tool-abort.test.js
- (new) backend unit+integration tests for get_equipment_rejects() under tests/

## Agent Work Packets

### change-classifier
- specs/changes/equipment-rejects-by-lots/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/equipment-rejects-by-lots/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### test-strategist
- specs/changes/equipment-rejects-by-lots/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

### ci-cd-gatekeeper
- specs/changes/equipment-rejects-by-lots/
- contracts/api/api-contract.md

### implementation-planner
- specs/changes/equipment-rejects-by-lots/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/sql/query_tool/
- frontend/src/query-tool/
- tests/

### backend-engineer
- specs/changes/equipment-rejects-by-lots/
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/sql/query_tool/
- shared/field_contracts.json
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- tests/

### frontend-engineer
- specs/changes/equipment-rejects-by-lots/
- frontend/src/query-tool/
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/field-contracts.ts
- frontend/src/core/types.ts
- frontend/src/shared-ui/
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/abort/query-tool-abort.test.js

### ui-ux-reviewer
- specs/changes/equipment-rejects-by-lots/
- frontend/src/query-tool/
- frontend/src/shared-ui/

### qa-reviewer
- specs/changes/equipment-rejects-by-lots/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- tests/e2e/test_query_tool_e2e.py
- frontend/tests/playwright/query-tool.spec.js

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - tests/
  reason: project-map truncated at tests/ root; backend-engineer needs exact existing test_query_tool_*.py paths to colocate new tests
  status: pending

## Approved Expansions
-
