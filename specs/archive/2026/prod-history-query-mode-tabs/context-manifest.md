# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- Frontend: `frontend/src/production-history/` (App.vue, composables/, style.css)
- Backend: `src/mes_dashboard/services/production_history_service.py`, `src/mes_dashboard/services/production_history_sql_runtime.py`, `src/mes_dashboard/routes/production_history_routes.py`, `src/mes_dashboard/sql/production_history/`
- Contracts: api, business, css
- Tests: frontend validation + E2E, backend unit/contract/integration

## Allowed Paths
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/production-history/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/sql/production_history/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/ci/
- tests/test_api_contract.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/stress/test_production_history_stress.py
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/abort/
- frontend/tests/playwright/

## Required Contracts
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/data/data-shape-contract.md (review only)

## Required Tests
- tests/test_api_contract.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/stress/test_production_history_stress.py
- frontend/tests/validation/useProductionHistory.validation.test.js
- frontend/tests/playwright/production-history-*.spec.ts

## Agent Work Packets

### change-classifier
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/

### backend-engineer
- specs/changes/prod-history-query-mode-tabs/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/sql/production_history/
- tests/test_api_contract.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/stress/test_production_history_stress.py
- contracts/api/api-contract.md
- contracts/business/business-rules.md

### frontend-engineer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/abort/
- frontend/tests/playwright/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### test-strategist
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- tests/
- frontend/tests/

### contract-reviewer
- specs/changes/prod-history-query-mode-tabs/
- contracts/

### ui-ux-reviewer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- contracts/css/

### visual-reviewer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- contracts/css/

### ci-cd-gatekeeper
- specs/changes/prod-history-query-mode-tabs/
- contracts/ci/

### qa-reviewer
- specs/changes/prod-history-query-mode-tabs/
- contracts/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - tests/test_production_history_service.py
    - tests/test_production_history_routes.py
  reason: project-map's tests/ listing is truncated at cap=50; exact backend test filenames could not be confirmed from the index.
  status: resolved
  resolution: main Claude confirmed both files exist; paths added to Allowed Paths. No expansion needed.

## Approved Expansions
-
