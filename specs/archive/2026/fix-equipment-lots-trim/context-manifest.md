# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- query-tool Equipment Lot Tracking (SQL + Python service/route + async RQ job)
- query-tool frontend composable (useLotEquipmentQuery.ts)
- API contract (POST /api/query-tool/equipment-period)

## Allowed Paths
- specs/changes/fix-equipment-lots-trim/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- tests/
- tests/integration/
- frontend/src/query-tool/
- frontend/tests/query-tool/
- contracts/

## Required Contracts
- contracts/api/api-contract.md
- contracts/CHANGELOG.md
- contracts/business/business-rules.md (read-only reference for QT-05/QT-06)

## Required Tests
- tests/test_query_tool_service.py
- tests/test_query_tool_routes.py
- tests/integration/test_query_tool_rq_async.py
- frontend/tests/query-tool/ (new test file for useLotEquipmentQuery.ts)

## Agent Work Packets

### change-classifier
- specs/changes/fix-equipment-lots-trim/
- specs/context/project-map.md
- specs/context/contracts-index.md

### bug-fix-engineer
- specs/changes/fix-equipment-lots-trim/
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- frontend/src/query-tool/
- contracts/

### implementation-planner
- specs/changes/fix-equipment-lots-trim/
- specs/context/project-map.md
- specs/context/contracts-index.md

### backend-engineer
- specs/changes/fix-equipment-lots-trim/
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- tests/
- tests/integration/
- contracts/

### frontend-engineer
- specs/changes/fix-equipment-lots-trim/
- frontend/src/query-tool/
- frontend/tests/query-tool/

### test-strategist
- specs/changes/fix-equipment-lots-trim/
- tests/
- tests/integration/
- frontend/tests/query-tool/

### contract-reviewer
- specs/changes/fix-equipment-lots-trim/
- contracts/

### qa-reviewer
- specs/changes/fix-equipment-lots-trim/
- contracts/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - .github/workflows/
  reason: ci-gatekeeper needs to confirm which existing required workflows (backend-tests.yml, frontend-tests.yml, contract-driven-gates.yml, openapi-sync-gate) already cover this change's surface before writing ci-gates.md
  status: approved
## Approved Expansions
- .github/workflows/
