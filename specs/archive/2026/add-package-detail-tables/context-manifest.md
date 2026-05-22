# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- hold-history (frontend DetailTable + backend SQL/service + export)
- query-tool (LotHistoryTable, EquipmentLotsTable, EquipmentRejectsTable + SQL + export)
- material-consumption (frontend DetailTable + backend SQL/service + export)

## Allowed Paths
- specs/changes/add-package-detail-tables/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/css/
- frontend/src/hold-history/components/
- frontend/src/query-tool/components/
- frontend/src/query-tool/utils/
- frontend/src/material-consumption/components/
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/material_consumption/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/hold_history_service.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_consumption_duckdb_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/routes/material_consumption_routes.py
- tests/test_query_tool_sql_runtime.py
- tests/test_hold_history_service.py
- tests/test_material_consumption_service.py

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md

## Required Tests
- tests/test_query_tool_sql_runtime.py
- tests/test_hold_history_service.py
- tests/test_material_consumption_service.py

## Agent Work Packets

### change-classifier
- specs/changes/add-package-detail-tables/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/add-package-detail-tables/
- contracts/api/
- contracts/data/
- contracts/css/

### backend-engineer
- specs/changes/add-package-detail-tables/
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/sql/hold_history/
- src/mes_dashboard/sql/material_consumption/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/hold_history_service.py
- src/mes_dashboard/services/hold_history_sql_runtime.py
- src/mes_dashboard/services/material_consumption_service.py
- src/mes_dashboard/services/material_consumption_duckdb_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- src/mes_dashboard/routes/hold_history_routes.py
- src/mes_dashboard/routes/material_consumption_routes.py
- tests/test_query_tool_sql_runtime.py
- tests/test_hold_history_service.py
- tests/test_material_consumption_service.py

### frontend-engineer
- specs/changes/add-package-detail-tables/
- frontend/src/hold-history/components/
- frontend/src/query-tool/components/
- frontend/src/query-tool/utils/
- frontend/src/material-consumption/components/

### test-strategist
- specs/changes/add-package-detail-tables/
- tests/test_query_tool_sql_runtime.py
- tests/test_hold_history_service.py
- tests/test_material_consumption_service.py

### ui-ux-reviewer
- specs/changes/add-package-detail-tables/
- contracts/css/
- frontend/src/hold-history/components/
- frontend/src/query-tool/components/
- frontend/src/material-consumption/components/

### qa-reviewer
- specs/changes/add-package-detail-tables/
- contracts/

## Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/sql/query_tool/lot_history.sql
    - src/mes_dashboard/sql/query_tool/equipment_lots.sql
    - src/mes_dashboard/sql/query_tool/equipment_lot_rejects.sql
    - src/mes_dashboard/sql/hold_history/
    - src/mes_dashboard/sql/material_consumption/
  reason: Individual SQL file names are under collapsed max-depth directories in project-map.md; implementation requires editing these specific files. The parent directories are already in Allowed Paths.
  status: approved

## Approved Expansions
- CER-001 approved: SQL files under already-allowed parent directories
