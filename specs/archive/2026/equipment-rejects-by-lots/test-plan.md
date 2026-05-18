---
change-id: equipment-rejects-by-lots
schema-version: 0.1.0
last-changed: 2026-05-18
risk: medium
tier: 1
---

# Test Plan: equipment-rejects-by-lots

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 cross-station reject join | unit | `tests/test_query_tool_service.py` (extend) | 0 |
| AC-1 cross-station reject join | integration | `tests/test_query_tool_routes.py` (extend) | 1 |
| AC-2 detail schema — correct columns, aggregates absent | unit | `tests/test_query_tool_service.py` (extend) | 0 |
| AC-2 one row per reject event | unit | `tests/test_query_tool_sql_runtime.py` (extend) | 0 |
| AC-2 data-shape contract validates on response | contract | `tests/test_query_tool_routes.py` (extend) | 1 |
| AC-3 equipment_ids param accepted; name→id mapping in route | unit | `tests/test_query_tool_routes.py` (extend) | 0 |
| AC-3 route calls service with ids not names | integration | `tests/test_query_tool_routes.py` (extend) | 1 |
| AC-4 empty short-circuit — LOTREJECTHISTORY not queried | unit | `tests/test_query_tool_service.py` (extend) | 0 |
| AC-5 export CSV header row matches detail schema | unit | `tests/test_query_tool_service.py` (extend) | 0 |
| AC-5 export CSV row count parity with filtered results | integration | `tests/test_query_tool_routes.py` (extend) | 1 |
| AC-6 EquipmentRejectsTable renders new detail columns | unit (Vitest) | `frontend/tests/query-tool/EquipmentRejectsTable.test.js` (new) | 0 |
| AC-6 lot_rejects sub-tab unchanged after refactor | unit (Vitest) | `frontend/tests/query-tool/EquipmentRejectsTable.test.js` (new) | 0 |
| AC-7 business-rules.md documents cross-station semantic | contract | `tests/test_query_tool_no_error_dicts.py` (extend) | 1 |
| AC-8 row-limit enforcement at large CONTAINERID volume | integration | `tests/test_query_tool_heavy_join.py` (extend) | 1 |
| AC-8 pagination/limit banner surfaced in UI | e2e | `tests/e2e/test_query_tool_e2e.py` (extend) | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Pure-function + mock-DB; must fail before implementation; extend test_query_tool_service.py, test_query_tool_sql_runtime.py |
| contract | 1 | data-shape-contract + api-contract validation on response envelope; extend test_query_tool_routes.py |
| integration | 1 | Flask test-client with mocked oracledb boundary; covers route→service→CSV pipeline |
| data-boundary | 1 | Cross-station fixture (lot on EQP-A, reject recorded under EQP-B); lives in test_query_tool_service.py |
| unit (Vitest) | 0 | Vue component rendering; new frontend/tests/query-tool/EquipmentRejectsTable.test.js |
| e2e | 3 | Playwright nightly; extend frontend/tests/playwright/query-tool.spec.js for rejects sub-tab column check |

## Tests That Must Fail Before Implementation

- `test_get_equipment_rejects_cross_station_lot` — fails until SQL CTE join on CONTAINERID is wired
- `test_get_equipment_rejects_no_aggregate_columns` — fails until TOTAL_REJECT_QTY etc. are removed from payload
- `test_equipment_period_route_passes_ids_not_names` — fails until route maps selection to EQUIPMENTIDs
- `test_get_equipment_rejects_empty_short_circuit` — fails until short-circuit guard is added
- `test_export_csv_equipment_rejects_header_row` — fails until export_type=equipment_rejects branch exists

## Existing Tests to Extend (not duplicate)

- `tests/test_query_tool_service.py` — add `TestGetEquipmentRejects` class
- `tests/test_query_tool_routes.py` — add equipment-period rejects-branch cases and CSV export cases
- `tests/test_query_tool_heavy_join.py` — add row-limit enforcement assertion
- `tests/e2e/test_query_tool_e2e.py` — add equipment rejects tab interaction scenario
- `frontend/tests/playwright/query-tool.spec.js` — add rejects sub-tab column visibility check

## Out of Scope

- lot_rejects sub-tab behavior (guarded by existing tests; no new tests needed)
- LDAP/AD authentication flows
- Other query types (lot / wafer / work-order)
- Soak and stress testing (no persistent spool; query-tool is on-demand per request)

## Notes

Cross-station fixture must include a row where `LOTWIPHISTORY.EQUIPMENTID` = EQP-A's ID but `LOTREJECTHISTORY.EQUIPMENTNAME` is EQP-B; assert that row appears in results — canonical regression guard for AC-1.
Mock at oracledb connection boundary only; do not mock query_tool_service internals from route-level tests.
AC-4 short-circuit test must assert the LOTREJECTHISTORY query mock is never invoked when the WIP CTE returns zero rows.
Vitest `include` must cover `src/**/*.test.js` (or `.ts`) per existing project rule — confirm EquipmentRejectsTable.test.js is picked up before merge.
