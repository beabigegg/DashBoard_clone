# Change Classification

## Change Types
- primary: `feature-enhancement` (additive API + data-shape change: new Package/PRODUCTLINENAME field in 5 detail-table responses/exports), `ui-only-change` (new Package column in 5 frontend tables)
- secondary: `api-only-change` (additive response field across multiple endpoints)

## Risk Level
- medium

Rationale: additive-only change (no removal/rename of existing fields), but spans 5 endpoints across 3 feature modules, touches API + data-shape contracts, and modifies CSV/Excel export shape.

## Impact Radius
- cross-module (hold-history, query-tool, material-consumption — three independent feature apps + backend services/SQL + export paths)

## Tier
- 2

## Architecture Review Required
- no
- reason: Each SQL file already JOINs `DW_MES_CONTAINER`; the change adds an existing column (`c.PRODUCTLINENAME`) to SELECT and forwards it as an additive API/export field. No new module boundary, no data-flow redesign, no migration/rollback decision. Repeats one well-understood pattern across surfaces.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | additive field; existing columns/values untouched |
| proposal.md | no | field name and placement are deterministic |
| spec.md | no | no separate spec investigation needed |
| design.md | no | no architecture review required |
| qa-report.md | no | create only if blocking/approved-with-risk finding emerges |
| regression-report.md | no | additive change — no existing-behavior modification expected |
| visual-review-report.md | no | capture as agent-log pointer unless layout defect found |
| monkey-test-report.md | no | not applicable to a column-add |
| stress-soak-report.md | no | no high-load/queue/auto-refresh behavior introduced |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, excluded pre-existing failures, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: contracts/api/api-contract.md — additive response field on 5 affected endpoints; contracts/api/api-inventory.md — per additive policy
- CSS/UI: contracts/css/css-contract.md — read-only confirmation of `.theme-<feature>` scoping; edit only if a new class is added
- Env: none
- Data shape: contracts/data/data-shape-contract.md — new field in detail-row payload and CSV/Excel export schema
- Business logic: none
- CI/CD: none

## Required Tests
- unit: backend service tests asserting each affected service forwards `PRODUCTLINENAME` to API response; frontend component tests asserting Package column appears in COLUMN_DEFS/headers
- contract: API contract test confirming additive field present for 5 endpoints; data-shape contract test for detail-row + export schema
- integration: SQL-runtime tests confirming `c.PRODUCTLINENAME` selected and aliased for each affected SQL file (lot_history, equipment_lots, equipment_lot_rejects, hold_history detail, material_consumption detail)
- E2E: light E2E optional (confirm Package column visible in query-tool tabs and one of hold-history/material-consumption)
- visual: confirm new column does not break table layout/overflow (capture as agent-log pointer)
- data-boundary: export includes Package column; NULL/empty + Oracle CHAR trailing-space values handled safely (`strip()`); rows with no JOIN match render safely
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- `contract-reviewer`
- `test-strategist`
- `ci-cd-gatekeeper`
- `implementation-planner`
- `backend-engineer`
- `frontend-engineer`
- `ui-ux-reviewer`
- `qa-reviewer`

## Inferred Acceptance Criteria
- AC-1: hold-history detail table API response includes `PRODUCTLINENAME`/Package field (additive), selected from already-JOINed `DW_MES_CONTAINER`.
- AC-2: query-tool Lot History, Equipment Lots, and Equipment Rejects tab responses each include the Package field; for Equipment Rejects, SQL already has `PRODUCTLINENAME` (equipment_lot_rejects.sql:52) and only API/frontend surfacing must be confirmed.
- AC-3: material-consumption detail table API response includes the Package field.
- AC-4: Each of the 5 frontend components (hold-history DetailTable, query-tool LotHistoryTable / EquipmentLotsTable / EquipmentRejectsTable, material-consumption DetailTable) renders a Package column in its COLUMN_DEFS/header and displays the value per row.
- AC-5: CSV/Excel export for hold-history, query-tool Equipment Lots, query-tool Equipment Rejects, and material-consumption includes the Package column (header + per-row value). query-tool Lot History tab has no export — not applicable.
- AC-6: Rows where `PRODUCTLINENAME` is NULL/empty or whose container has no JOIN match render and export safely (no crash, blank-or-placeholder cell); Oracle CHAR trailing-space values are trimmed before display/export.
- AC-7: All existing columns, values, sort/filter behavior, and export rows for the 5 tables remain unchanged (additive-only; no regression).
- AC-8: API and data-shape contracts are updated to document the new additive field for affected endpoints and export schemas.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.5, 2.6, 3.3, 3.5, 4.3, 5.2

(1.3=design/arch not required; 2.2=CSS contract confirm-only no edit; 2.3=no env change; 2.5=no business rule change; 2.6=no CI workflow change; 3.3=Tier 2 light E2E optional not mandatory; 3.5=no stress/soak; 4.3=no env/deploy; 5.2=visual review as agent-log pointer only)

## Clarifications or Assumptions
- Stable snake_case API JSON key for the new field to be confirmed during planning (candidate: `product_line_name` or `package`).
- query-tool has no persistent spool (per CLAUDE.md) — no parquet cleanup needed for query-tool.
- hold-history and material-consumption may use spool/parquet; if parquet column schema changes, deploy runbook must add cleanup — confirm in `ci-gates.md §Rollback Policy`.
- No new CSS token or unscoped rule introduced; new column header reuses existing table-header styling under `.theme-<feature>` scope.

## Context Manifest Draft

### Affected Surfaces
- hold-history (frontend DetailTable + backend SQL/service + export)
- query-tool (LotHistoryTable, EquipmentLotsTable, EquipmentRejectsTable + SQL + export)
- material-consumption (frontend DetailTable + backend SQL/service + export)

### Allowed Paths
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

### Agent Work Packets

#### change-classifier
- specs/changes/add-package-detail-tables/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/add-package-detail-tables/
- contracts/api/
- contracts/data/
- contracts/css/

#### backend-engineer
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

#### frontend-engineer
- specs/changes/add-package-detail-tables/
- frontend/src/hold-history/components/
- frontend/src/query-tool/components/
- frontend/src/query-tool/utils/
- frontend/src/material-consumption/components/

#### test-strategist
- specs/changes/add-package-detail-tables/
- tests/test_query_tool_sql_runtime.py
- tests/test_hold_history_service.py
- tests/test_material_consumption_service.py

#### ui-ux-reviewer
- specs/changes/add-package-detail-tables/
- contracts/css/
- frontend/src/hold-history/components/
- frontend/src/query-tool/components/
- frontend/src/material-consumption/components/

#### qa-reviewer
- specs/changes/add-package-detail-tables/
- contracts/

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/sql/query_tool/lot_history.sql
    - src/mes_dashboard/sql/query_tool/equipment_lots.sql
    - src/mes_dashboard/sql/query_tool/equipment_lot_rejects.sql
    - src/mes_dashboard/sql/hold_history/
    - src/mes_dashboard/sql/material_consumption/
  reason: Individual SQL file names are under collapsed max-depth directories in project-map.md; implementation requires editing these specific files. The parent directories are already in Allowed Paths; this CER documents the specific files for traceability.
  status: approved
