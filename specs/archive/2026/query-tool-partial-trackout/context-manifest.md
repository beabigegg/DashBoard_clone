# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- query-tool backend (SQL + service runtime)
- query-tool API response shape (additive partial_count)
- business-rules contract (PH-06/PH-07 scope extension to query-tool)
- data-shape contract (partial_count field)

## Allowed Paths
- specs/changes/query-tool-partial-trackout/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- tests/
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- .github/workflows/

## Required Contracts
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/api/api-contract.md

## Required Tests
- tests/ (existing test_query_tool_*.py; new partial-trackout aggregation tests)

## Agent Work Packets

### change-classifier
- specs/changes/query-tool-partial-trackout/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/query-tool-partial-trackout/
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py

### test-strategist
- specs/changes/query-tool-partial-trackout/
- tests/
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### ci-cd-gatekeeper
- specs/changes/query-tool-partial-trackout/
- contracts/ci/ci-gate-contract.md
- .github/workflows/

### implementation-planner
- specs/changes/query-tool-partial-trackout/
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/api/api-contract.md

### backend-engineer
- specs/changes/query-tool-partial-trackout/
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- tests/

### qa-reviewer
- specs/changes/query-tool-partial-trackout/
- tests/

## Context Expansion Requests
-

## Approved Expansions
-
