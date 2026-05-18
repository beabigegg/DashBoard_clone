# Change Classification

## Change Types
- primary: business-logic-change, api-only-change (response shape)
- secondary: ui-only-change (table column redesign), bug-fix (cross-station rejects were being missed)

## Risk Level
- medium

## Impact Radius
- module-level (query-tool feature only; equipment-period API endpoint, EquipmentView + LotEquipmentView consumers)

## Tier
- 2

## Architecture Review Required
- no
- reason: reuses the proven LOTWIPHISTORY→LOTREJECTHISTORY two-step pattern that lot_rejects sub-tab already uses; no new module boundary, no new data-flow direction

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | current aggregate behavior summarized inline in implementation-plan.md §Background |
| proposal.md | no | scope and approach captured in change-request.md + implementation-plan.md |
| spec.md | no | behavior change captured in business-rules + data-shape contracts |
| design.md | no | architecture review not required; reuses existing pattern |
| qa-report.md | no | routine evidence in agent-log YAML pointers |
| regression-report.md | no | regression scope bounded to query-tool equipment-rejects; covered by test-plan |
| visual-review-report.md | no | column rewrite uses existing DataTable shell; agent-log pointer sufficient |
| monkey-test-report.md | no | not a high-load or chaos surface |
| stress-soak-report.md | no | data volume may increase but no auto-refresh/queue/cache change; load assessment in test-plan |

## Required Contracts
- API: yes — contracts/api/api-contract.md (equipment-period rejects response shape changes from aggregate to detail row schema)
- CSS/UI: no
- Env: no
- Data shape: yes — contracts/data/data-shape-contract.md (equipment_rejects payload row schema: aggregate fields removed; detail fields added)
- Business logic: yes — contracts/business/business-rules.md (new rule: equipment-rejects = rejects-of-lots-processed-on-equipment via LOTWIPHISTORY CONTAINERID resolution; cross-station rejects intentionally included)
- CI/CD: no

## Required Tests
- unit: yes — get_equipment_rejects() parameter contract, SQL template parameter binding, empty short-circuit, row-shape mapping
- contract: yes — equipment-period API response shape for query_type='rejects'; export CSV type equipment_rejects column shape
- integration: yes — cross-station reject fixture, empty-equipment short-circuit, realistic CONTAINERID set
- E2E: yes — equipment tab → rejects sub-tab renders new columns; LotEquipmentView same; export CSV download
- visual: no
- data-boundary: yes — export CSV header/row count parity vs on-screen table
- resilience: no
- fuzz/monkey: no
- stress: consideration only (row-count ceiling probe in test-plan; no separate stress run gated)
- soak: no

## Required Agents
- contract-reviewer (read-only): confirm api/data/business contract diffs
- test-strategist (write): test-plan.md
- ci-cd-gatekeeper (write): ci-gates.md
- implementation-planner (write): implementation-plan.md
- backend-engineer (write): new SQL, service signature change, route param mapping, unit+integration tests (TDD)
- frontend-engineer (write): EquipmentRejectsTable.vue column rewrite, consumer updates, component tests
- ui-ux-reviewer (read-only): column choice, sort/filter/empty-state for new detail table
- qa-reviewer (read-only): release readiness

## Inferred Acceptance Criteria
- AC-1: Given a lot was processed on equipment E in the date window (LOTWIPHISTORY), when the user opens the rejects sub-tab for E, then any LOTREJECTHISTORY rows for that lot's CONTAINERID appear even when the reject event's EQUIPMENTNAME is not E (cross-station case).
- AC-2: The rejects sub-tab returns one row per reject event (detail); columns include at minimum CONTAINERNAME, WORKCENTERNAME, LOSSREASONNAME, REJECTQTY, TXN_TIME; aggregate-only fields (TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) are removed from the payload.
- AC-3: The backend service get_equipment_rejects() accepts equipment_ids (List[str]) instead of equipment_names; the equipment-period API route maps equipment selection to EQUIPMENTIDs before invoking the service.
- AC-4: When the equipment processed zero lots in the date window, the service short-circuits and returns empty without issuing the LOTREJECTHISTORY query.
- AC-5: Export CSV for type equipment_rejects produces a header row and row content matching the new detail schema; row count equals on-screen filtered row count (data-shape parity).
- AC-6: Both EquipmentView and LotEquipmentView render the new detail columns; the lot_rejects sub-tab (LOT tab) is unchanged.
- AC-7: business-rules.md documents the new semantic: "equipment rejects = rejects of any lot that passed through this equipment in the window," with explicit note that the reject event may be logged on a different EQUIPMENTNAME.
- AC-8: Query response under realistic worst-case CONTAINERID volume returns within the existing query-tool latency budget, or pagination/row-limit is enforced and surfaced to the UI.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.6, 3.5, 4.3, 5.2

## Clarifications or Assumptions
- Assumption: The equipment-period route maps equipment selection to EQUIPMENTIDs server-side; this is a backend-internal change between route and service, not necessarily a public API parameter rename. Backend-engineer to confirm; if the public API param must change, api-contract.md needs a deprecation note.
- Assumption: equipment_rejects.sql will be replaced/renamed to equipment_lot_rejects.sql (hard cutover; no feature flag).
- Assumption: No new env var, no new cache namespace, no new queue. Query is on-demand (no persistent spool per CLAUDE.md).
- Assumption: LotRejectTable.vue is the design reference for new EquipmentRejectsTable.vue column set.
- Open question: confirm whether EQUIPMENTNAME of the reject event (the "registered-on" station) should be surfaced in the table to make cross-station cases visible to users.

## Context Manifest Draft

### Affected Surfaces
- query-tool feature (frontend app + backend service + SQL template)
- equipment-period API endpoint (query_type='rejects' branch)
- export CSV pipeline (equipment_rejects type)
- contracts: api, data-shape, business-rules

### Allowed Paths
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
