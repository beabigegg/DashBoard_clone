---
change-id: equipment-rejects-by-lots
schema-version: 0.1.0
last-changed: 2026-05-18
---

# Implementation Plan: equipment-rejects-by-lots

## Objective

Change the query-tool equipment "報廢" sub-tab from an aggregate-by-EQUIPMENTNAME view to a per-reject-event detail view that captures cross-station rejects. Resolve the equipment selection through `DW_MES_LOTWIPHISTORY` (by `EQUIPMENTID` + date window) to a `CONTAINERID` set, then return one detail row per `DW_MES_LOTREJECTHISTORY` event for those containers, regardless of which `EQUIPMENTNAME` the reject was logged under.

The change is a hard cutover — no feature flag, no aggregate-mode fallback. Both consumer views (`EquipmentView`, `LotEquipmentView`) and the CSV export must ship together in the same PR.

## Background (minimal)

- Current `equipment_rejects.sql` GROUPs `LOTREJECTHISTORY` by `EQUIPMENTNAME, LOSSREASONNAME` and returns `TOTAL_REJECT_QTY / TOTAL_DEFECT_QTY / AFFECTED_LOT_COUNT`.
- `LOTREJECTHISTORY` exposes only `EQUIPMENTNAME` (no `EQUIPMENTID`), so cross-station rejects (lot processed on EQP-A but reject logged on EQP-B) are silently missing from the current sub-tab.
- `lot_rejects.sql` already uses the correct CONTAINERID-based lookup; its row shape is the design template for the new equipment-rejects payload.

## Execution Scope

### In Scope
- Replace `src/mes_dashboard/sql/query_tool/equipment_rejects.sql` with a CONTAINERID-join SQL named `equipment_lot_rejects.sql` (rename + rewrite). Implementation pattern: WIP CTE on `DW_MES_LOTWIPHISTORY` (EQUIPMENTID IN (...) + date window on `TRACKINTIMESTAMP`) → `DISTINCT CONTAINERID` → JOIN `DW_MES_LOTREJECTHISTORY` (and `DW_MES_CONTAINER`, `DW_MES_SPEC_WORKCENTER_V`) by `CONTAINERID`, projecting one row per reject event. Use `equipment_lots.sql` and `lot_rejects.sql` as references.
- Change `get_equipment_rejects()` signature: `equipment_names: List[str] → equipment_ids: List[str]`. Add an explicit empty-WIP short-circuit (return `{'data': [], 'total': 0, ...}` without executing the LOTREJECTHISTORY query when the CONTAINERID set is empty).
- Update `query_tool_routes.py::query_equipment_period` `query_type='rejects'` branch to call the new service with `equipment_ids` and to validate `equipment_ids` (not `equipment_names`).
- Update `query_tool_routes.py::export_csv` `export_type='equipment_rejects'` branch to pass `equipment_ids` and update `filename`-related code if relevant. No new `_format_*_export_rows` helper unless service does not already return the final shape (prefer service-side projection).
- Rewrite `frontend/src/query-tool/components/EquipmentRejectsTable.vue` column set to match the new detail row schema. Columns are based on `LotRejectTable.vue` plus an EQUIPMENTNAME column representing **the reject event's** equipment (so users can see cross-station cases). Sorting/empty state must follow the same patterns as `LotRejectTable.vue`.
- Update `frontend/src/query-tool/composables/useEquipmentQuery.ts::exportSubTab` — the `equipment_rejects` branch's `params` payload no longer needs to send `equipment_names`; it must send `equipment_ids` (route already accepts both keys today; once the rejects branch is migrated, the rejects-only payload can drop `equipment_names`). Mirror in `useLotEquipmentQuery.ts` export path.
- Update three contract files (see Contract Updates).
- Add backend unit + integration tests and one Vitest component test (TDD: tests are written first and must fail until implementation lands).

### Out of Scope
- `lot_rejects` sub-tab (LOT tab) — unchanged. The existing `LotRejectTable.vue` and `lot_rejects.sql` keep their shape; AC-6 explicitly requires they remain stable.
- Other `query_type` branches (`status_hours`, `lots`, `materials`, `jobs`) — no signature, payload, or SQL changes.
- `equipment_rejects` aggregate response shape — fully removed; no deprecated-window kept. (Both consumers ship in the same PR; see ci-gates.md "Breaking-change note".)
- New env vars, new cache namespaces, new queues, new parquet spool, or pre-warm hooks. Query is on-demand (per CLAUDE.md: query-tool has no persistent spool — do not add parquet cleanup to rollback).
- Pagination redesign and timeline integration for the rejects sub-tab. If row-count protection is needed (AC-8), enforce a server-side row cap surfaced via a meta flag, not a new pagination contract.
- Frontend `selectedEquipmentNames` computed and `equipment_names` payload field for non-rejects branches — leave untouched.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend SQL | Create `src/mes_dashboard/sql/query_tool/equipment_lot_rejects.sql` (CTE: WIP DISTINCT CONTAINERID → JOIN LOTREJECTHISTORY); delete `src/mes_dashboard/sql/query_tool/equipment_rejects.sql` | backend-engineer |
| IP-2 | backend service | Rewrite `get_equipment_rejects()` in `query_tool_service.py`: signature `equipment_ids: List[str]`, validate via `validate_equipment_input`, load `query_tool/equipment_lot_rejects`, return detail rows. Add empty-WIP short-circuit guarded so `read_sql_df_slow` for LOTREJECTHISTORY is never invoked when WIP CTE is empty (implement as a separate WIP-probe query OR rely on SQL's empty join — but ensure AC-4 unit test passes by mocking the runtime appropriately). | backend-engineer |
| IP-3 | backend route | Update `query_equipment_period()` `query_type='rejects'` branch in `query_tool_routes.py` to call `get_equipment_rejects(equipment_ids, ...)` and validate `equipment_ids` (replace `equipment_names` validation). Update `export_csv()` `equipment_rejects` branch likewise. | backend-engineer |
| IP-4 | API contract | Add new sub-bullet under `contracts/api/api-contract.md §10 Compatibility Notes` documenting the breaking shape change for `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`). | backend-engineer |
| IP-5 | data-shape contract | Add a new sub-section `### 3.7 Query-Tool Equipment-Lot-Rejects Row` to `contracts/data/data-shape-contract.md §3` with the new column table. Update `§5 Export / Import Format` to mention the new CSV column list (or reference §3.7). Remove the old aggregate fields from any prior mention. | backend-engineer |
| IP-6 | business rule | Add `QT-07` row to `contracts/business/business-rules.md` "Query Tool Rules" table documenting the cross-station semantic ("equipment rejects = rejects of any lot that passed through this equipment in the window; reject event may be logged on a different EQUIPMENTNAME"). | backend-engineer |
| IP-7 | API inventory | Add a one-line patch note (date + change-id) to `contracts/api/api-inventory.md` so the api-contract entry references this change. | backend-engineer |
| IP-8 | backend tests (TDD) | Add `TestGetEquipmentRejects` to `tests/test_query_tool_service.py` and new cases to `tests/test_query_tool_routes.py`, `tests/test_query_tool_heavy_join.py`, and `tests/test_query_tool_no_error_dicts.py`. Tests listed under test-plan.md §"Tests That Must Fail Before Implementation" MUST be authored first and observed to fail before implementing IP-1..IP-3. | backend-engineer |
| IP-9 | frontend table | Rewrite `frontend/src/query-tool/components/EquipmentRejectsTable.vue` with the new column set (model on `LotRejectTable.vue`). Surface `EQUIPMENTNAME` (reject event's equipment) and `WORKCENTERNAME`, `LOSSREASONNAME`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `TXN_TIME`, plus the LOT identification columns (`CONTAINERNAME`, `PJ_TYPE`, `PRODUCTLINENAME`, `PJ_FUNCTION`, `PRODUCTNAME`, `SPECNAME`, `REJECTCOMMENT`). Reuse `useSortableTable`, `BlockLoadingState`, `formatCellValue` patterns from `LotRejectTable.vue`. | frontend-engineer |
| IP-10 | frontend export payload | Update `useEquipmentQuery.ts::exportSubTab` rejects branch to send `equipment_ids` (drop reliance on `equipment_names`). Mirror in `useLotEquipmentQuery.ts`. | frontend-engineer |
| IP-11 | frontend tests | New `frontend/tests/query-tool/EquipmentRejectsTable.test.js` (Vitest) — assert new columns render, aggregate fields are not referenced, empty state shows. Verify Vitest `include` glob picks the file up (see CLAUDE.md note on `src/**/*.test.ts`). | frontend-engineer |
| IP-12 | e2e | Extend `tests/e2e/test_query_tool_e2e.py` and `frontend/tests/playwright/query-tool.spec.js` with the rejects sub-tab column-visibility + export-csv scenario. Nightly only (informational at merge). | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-request.md | "Constraints" + "Known Context" | scope of SQL/service signature change |
| change-classification.md | "Inferred Acceptance Criteria" AC-1 … AC-8 | acceptance criteria text (do not duplicate) |
| test-plan.md | "Acceptance Criteria — Test Mapping" table | exact test file paths and AC→test mapping |
| test-plan.md | "Tests That Must Fail Before Implementation" | TDD order for IP-8 |
| ci-gates.md | "Required Gates" table | verification commands per tier |
| ci-gates.md | "Breaking-change note" | aggregate-field removal must be co-shipped with both consumers |
| ci-gates.md | "Rollback Policy" | no parquet cleanup required (query-tool on-demand) |
| context-manifest.md | "Allowed Paths" | read-boundary for all agents |
| contracts/business/business-rules.md | QT-01..QT-06 (Query Tool Rules table) | placement and style for new QT-07 |
| contracts/data/data-shape-contract.md | §3.6 (Query-Tool Lot-History / Equipment-Lots / Adjacent-Lots Row) | template for new §3.7 row table |
| contracts/api/api-contract.md | §10 Compatibility Notes (last "Query-Tool partial-trackout" entry) | placement for new compatibility note |
| src/mes_dashboard/sql/query_tool/equipment_lots.sql | WIP CTE structure (EQUIPMENTID filter, date window) | SQL template basis |
| src/mes_dashboard/sql/query_tool/lot_rejects.sql | LOTREJECTHISTORY projection + spec_map join + ordering | reject row shape and ordering reference |
| src/mes_dashboard/services/query_tool_service.py | `get_equipment_lots()` (lines around 2399–2467) | parameter-validation + QueryBuilder + SQLLoader pattern reference |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/sql/query_tool/equipment_lot_rejects.sql` | create | New file. CTE: WIP CONTAINERIDs from `DW_MES_LOTWIPHISTORY` filtered by `EQUIPMENTID IN (...)` and `TRACKINTIMESTAMP` window → `DISTINCT CONTAINERID` → JOIN `DW_MES_LOTREJECTHISTORY` ON `CONTAINERID`, LEFT JOIN `DW_MES_CONTAINER` and `DW_MES_SPEC_WORKCENTER_V` (mirror lot_rejects.sql projection list). Bind via `{{ EQUIPMENT_FILTER }}` placeholder. |
| `src/mes_dashboard/sql/query_tool/equipment_rejects.sql` | delete | Hard cutover; no fallback. |
| `src/mes_dashboard/services/query_tool_service.py` | edit | Rewrite `get_equipment_rejects()` (lines ~2525–2577). Signature: `equipment_ids: List[str], start_date: str, end_date: str`. Validate via `validate_equipment_input`. Use `QueryBuilder.add_in_condition("h.EQUIPMENTID", equipment_ids)`. Call `SQLLoader.load_with_params("query_tool/equipment_lot_rejects", EQUIPMENT_FILTER=...)`. Return `{'data': records, 'total': len(records), 'date_range': {...}}`. Empty short-circuit: when `equipment_ids` is empty raise `UserInputError` (existing behavior); when WIP set is empty inside SQL the join returns zero rows naturally — but for AC-4 unit test, the test will mock the SQL runtime. Implementer choice: keep single-SQL design (relying on inner-join emptiness) OR split into two-step probe (`SELECT DISTINCT CONTAINERID` then conditional `LOTREJECTHISTORY`). Document the chosen path in PR description so reviewer can match the AC-4 test expectation. |
| `src/mes_dashboard/routes/query_tool_routes.py` | edit | (1) `query_equipment_period` `query_type=='rejects'` branch: replace `equipment_names` guard + call with `equipment_ids` guard + `get_equipment_rejects(equipment_ids, ...)`. (2) `export_csv` `equipment_rejects` branch: replace `params.get('equipment_names', [])` with `params.get('equipment_ids', [])`. (3) No new `_format_equipment_rejects_export_rows` helper — service returns final shape. |
| `frontend/src/query-tool/components/EquipmentRejectsTable.vue` | rewrite | New column set (see IP-9). Use `DataTable`/`DataTableColumn` if keeping current shell, OR mirror `LotRejectTable.vue`'s native `<table>` + `useSortableTable` pattern. Choose the pattern that best matches existing query-tool table conventions; if uncertain, follow `LotRejectTable.vue` for consistency. Default sort: `TXN_TIME DESC` then `WORKCENTERNAME ASC` then `REJECT_TOTAL_QTY DESC` (mirror lot_rejects). |
| `frontend/src/query-tool/composables/useEquipmentQuery.ts` | edit | `exportSubTab` rejects branch (line ~336): no longer relies on `equipment_names` (route now reads `equipment_ids`). Send `equipment_ids` only for the rejects export params. Other branches untouched. |
| `frontend/src/query-tool/composables/useLotEquipmentQuery.ts` | edit | Same as above; rejects export must send `equipment_ids` from `resolvedEquipmentIds`. |
| `frontend/src/query-tool/components/EquipmentView.vue` | no-op for emits/props | Already wires `rejectsRows` to `EquipmentRejectsTable`. Confirm no aggregate-specific UI exists in this file (it does not). |
| `frontend/src/query-tool/components/LotEquipmentView.vue` | no-op for emits/props | Same as above. |
| `contracts/api/api-contract.md` | edit | Add §10 Compatibility Notes entry per IP-4. |
| `contracts/data/data-shape-contract.md` | edit | Add §3.7 row table per IP-5. Reference new CSV column list under §5 if helpful (or just point to §3.7). |
| `contracts/business/business-rules.md` | edit | Add `QT-07` row per IP-6 to the "Query Tool Rules" table. |
| `contracts/api/api-inventory.md` | edit | Add patch note per IP-7. |
| `tests/test_query_tool_service.py` | extend | Add `TestGetEquipmentRejects` class covering AC-1 (cross-station), AC-2 (detail row shape, no aggregate fields), AC-4 (empty short-circuit — assert LOTREJECTHISTORY query mock not invoked), AC-5 (export header row). |
| `tests/test_query_tool_routes.py` | extend | Add rejects-branch cases for AC-2 (data-shape contract assertion), AC-3 (route passes ids not names), AC-5 (CSV export row-count parity). |
| `tests/test_query_tool_sql_runtime.py` | extend | Add SQL parameter-binding + one-row-per-reject-event assertions for AC-2. |
| `tests/test_query_tool_heavy_join.py` | extend | Add AC-8 row-limit assertion at realistic worst-case CONTAINERID volume. |
| `tests/test_query_tool_no_error_dicts.py` | extend | AC-7: assert business-rules.md QT-07 is present + references cross-station semantic. |
| `frontend/tests/query-tool/EquipmentRejectsTable.test.js` | create | AC-6 Vitest unit: new columns render; old aggregate column headers absent; empty/loading state. Verify Vitest `include` (see CLAUDE.md migrate-shared-ui-ts note) picks up the file. |
| `frontend/tests/playwright/query-tool.spec.js` | extend | AC-6 + AC-8 e2e: rejects sub-tab column visibility, export download. |
| `tests/e2e/test_query_tool_e2e.py` | extend | Equipment rejects tab interaction scenario per test-plan.md. |

## Contract Updates

- **API** (`contracts/api/api-contract.md`): Append a new sub-bullet under §10 Compatibility Notes:
  - Title: `Query-Tool equipment-rejects detail rewrite (2026-05-18, equipment-rejects-by-lots)` — breaking shape change for `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`). Aggregate fields `TOTAL_REJECT_QTY`, `TOTAL_DEFECT_QTY`, `AFFECTED_LOT_COUNT` removed; payload now matches §3.7. Both consumer views (`EquipmentView`, `LotEquipmentView`) ship in the same PR. Service param renamed `equipment_names → equipment_ids` (route accepts both keys today; rejects branch is migrated). Note: not a deprecate-2-minors case because both backend payload producer and only-two frontend consumers ship together; document this departure explicitly here.
- **CSS/UI**: none.
- **Env**: none. No new env vars; existing `QUERY_TOOL_*` envs apply unchanged.
- **Data shape** (`contracts/data/data-shape-contract.md`): Add `### 3.7 Query-Tool Equipment-Lot-Rejects Row` with column table (mirror §3.6 style). Columns: `CONTAINERID, CONTAINERNAME, WORKCENTERNAME, WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PRODUCTLINENAME, PJ_FUNCTION, PJ_TYPE, PRODUCTNAME, SPECNAME, LOSSREASONNAME, EQUIPMENTNAME (reject event's equipment, may differ from queried equipment), REJECTCOMMENT, REJECT_QTY, STANDBY_QTY, QTYTOPROCESS_QTY, INPROCESS_QTY, PROCESSED_QTY, REJECT_TOTAL_QTY, DEFECT_QTY, TXN_TIME, TXNDATE, TXN_DAY`. Update §5 export section to either reference §3.7 directly or list the CSV column order. Explicitly call out that aggregate columns from prior `query_type='rejects'` payload have been removed (see §10 of api-contract.md).
- **Business logic** (`contracts/business/business-rules.md`): Add `QT-07` row under "Query Tool Rules" table:
  - `QT-07 | Equipment-rejects cross-station semantic | get_equipment_rejects() resolves the queried EQUIPMENTIDs against LOTWIPHISTORY (TRACKINTIMESTAMP within window) to a DISTINCT CONTAINERID set, then returns LOTREJECTHISTORY rows for those CONTAINERIDs. The reject event's EQUIPMENTNAME may differ from the queried equipment (cross-station case is intentional, not a bug). LOTREJECTHISTORY has no EQUIPMENTID, so CONTAINERID is the only correct join key. Empty WIP set → empty result (LOTREJECTHISTORY query short-circuited per AC-4). | unit + integration tests`
- **CI/CD**: none (per ci-gates.md "no new workflow files required").

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 cross-station reject join | `pytest tests/test_query_tool_service.py::TestGetEquipmentRejects::test_get_equipment_rejects_cross_station_lot -x` | row with `EQUIPMENTNAME != queried_equipment` returned |
| AC-1 integration | `pytest tests/test_query_tool_routes.py -k equipment_rejects_cross_station -x` | response contains cross-station row |
| AC-2 detail row schema | `pytest tests/test_query_tool_service.py::TestGetEquipmentRejects::test_get_equipment_rejects_no_aggregate_columns -x` | no `TOTAL_REJECT_QTY` / `TOTAL_DEFECT_QTY` / `AFFECTED_LOT_COUNT` keys in any row |
| AC-2 one row per reject event | `pytest tests/test_query_tool_sql_runtime.py -k equipment_rejects -x` | row count equals reject event count, not aggregate count |
| AC-2 data-shape contract | `pytest tests/test_query_tool_routes.py -k equipment_rejects_shape -x` + `cdd-kit validate` | data-shape-contract §3.7 satisfied |
| AC-3 route passes ids not names | `pytest tests/test_query_tool_routes.py::test_equipment_period_route_passes_ids_not_names -x` | service called with `equipment_ids` kw; `equipment_names` ignored in rejects branch |
| AC-4 empty short-circuit | `pytest tests/test_query_tool_service.py::TestGetEquipmentRejects::test_get_equipment_rejects_empty_short_circuit -x` | LOTREJECTHISTORY query mock not invoked when WIP CTE empty |
| AC-5 export CSV header | `pytest tests/test_query_tool_service.py::TestGetEquipmentRejects::test_export_csv_equipment_rejects_header_row -x` | CSV header matches §3.7 column list |
| AC-5 export CSV row parity | `pytest tests/test_query_tool_routes.py -k equipment_rejects_export -x` | CSV row count == filtered API row count |
| AC-6 frontend column render | `cd frontend && npm run test -- --run tests/query-tool/EquipmentRejectsTable.test.js` | new columns present, aggregate columns absent |
| AC-6 lot_rejects unchanged | implicit — `frontend/tests/query-tool/EquipmentRejectsTable.test.js` (asserts no overlap with LotRejectTable surface) + existing LotRejectTable tests stay green | green |
| AC-7 business-rules QT-07 present | `pytest tests/test_query_tool_no_error_dicts.py -k QT_07 -x` | rule text present and references cross-station |
| AC-8 row-limit at scale | `pytest tests/test_query_tool_heavy_join.py -k equipment_rejects_row_limit -x` | response stays within latency / row budget OR `_meta.truncated=true` set |
| AC-8 UI surfacing | `npx playwright test frontend/tests/playwright/query-tool.spec.js -g "rejects row limit"` | banner visible if truncated (nightly) |
| Required gates (full) | per ci-gates.md "Required Gates" table | all Tier 0 + Tier 1 green at merge; Tier 3 informational |

TDD ordering for backend-engineer:
1. Write all five "Tests That Must Fail Before Implementation" listed in test-plan.md.
2. Run `pytest tests/test_query_tool_service.py tests/test_query_tool_routes.py tests/test_query_tool_sql_runtime.py -x` and capture failure output as TDD evidence in agent-log.
3. Implement IP-1 (SQL), then IP-2 (service), then IP-3 (route). Re-run pytest until green.
4. Update contracts (IP-4..IP-7) and run `cdd-kit validate`.
5. Hand off to frontend-engineer for IP-9..IP-12.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- CER-001 (in `context-manifest.md`) is `pending` for the `tests/` root. Backend-engineer should not enumerate `tests/` beyond the files explicitly named in test-plan.md / this plan; if a new test file is needed, request approval first.
- Do NOT introduce a feature flag or aggregate-mode fallback — change-classification.md "Assumption" explicitly states hard cutover.
- Do NOT touch `lot_rejects.sql`, `LotRejectTable.vue`, or the LOT tab — AC-6 protects this surface.
- Do NOT change `equipment_names` plumbing for non-rejects branches (`materials`, `lots`, `jobs`, `status_hours`) — out of scope per change-classification.md.
- Frontend column choices need an `ui-ux-reviewer` read-only pass before merge per change-classification.md "Required Agents".

## Known Risks

- **Row volume blow-up**: aggregate → detail can multiply response size by O(rejects-per-lot). AC-8 (heavy-join test + UI banner) is the only guard. If preliminary heavy-join numbers exceed the existing query-tool latency budget, escalate via Context Expansion Request before relaxing the row cap.
- **WIP CTE empty path** (AC-4): implementer must keep the LOTREJECTHISTORY query un-invoked in the empty WIP case. If the chosen design uses a single combined SQL, the AC-4 unit test must mock at a level that still proves the LOTREJECTHISTORY data-path is short-circuited (e.g., via an explicit pre-probe). Document the chosen design in the PR.
- **CSV vs API row parity** (AC-5): if `_format_*_export_rows` is added for column renaming, it must not change row count. Prefer letting service projection match CSV header 1:1.
- **Hidden consumer**: no schema entries in `frontend/src/core/endpoint-schemas.ts` or `shared/field_contracts.json` reference `equipment_rejects` today (verified during planning). If any new consumer is added between plan and implementation, audit with `rg equipment_rejects` before merge.
- **Test discovery**: Vitest `include` must list `src/**/*.test.ts` (or the new `tests/query-tool/*.test.js`) per CLAUDE.md note. Confirm the new EquipmentRejectsTable test file is actually executed (non-zero test count) before declaring AC-6 green.
- **Cross-station EQUIPMENTNAME semantics**: the new EQUIPMENTNAME column reflects the **reject event's** equipment, NOT the queried equipment. UI label must make this unambiguous (e.g., "報廢登錄設備" or explicit tooltip) — flag for `ui-ux-reviewer`.
