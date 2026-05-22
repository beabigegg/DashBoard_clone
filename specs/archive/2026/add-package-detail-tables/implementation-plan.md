---
change-id: add-package-detail-tables
schema-version: 0.1.0
last-changed: 2026-05-22
---

# Implementation Plan: add-package-detail-tables

## Objective

Surface the existing `DW_MES_CONTAINER.PRODUCTLINENAME` (Package) column as an
additive field in 5 detail-table endpoints, their frontend tables, and their
CSV/Excel exports, across three feature modules (hold-history, query-tool,
material-consumption). No existing field, value, sort/filter, or export row may
change (AC-7). Trailing-space / NULL / no-JOIN values must be handled safely
(AC-6).

## Execution Scope

### In Scope
- hold-history detail: SQL select, service forward to JSON, export column, frontend column (AC-1, AC-4, AC-5).
- query-tool Lot History + Equipment Lots: SQL select, `_PARTIAL_NONKEY_COLS_LOT` extension, response/export forward, frontend columns (AC-2, AC-4, AC-5).
- query-tool Equipment Rejects: SQL already has the column — confirm/surface in response, export, and frontend only (AC-2, AC-4, AC-5).
- material-consumption detail: SQL select, spool/parquet schema + response forward, export column, frontend column (AC-3, AC-4, AC-5).
- API + data-shape contract documentation of the additive field (AC-8).
- Failing-test-first (TDD) per `test-plan.md` New Test Functions.

### Out of Scope
- Frontend Vitest SFC tests for column visibility (see `test-plan.md` Out of Scope; covered by contract gate + visual review).
- query-tool Lot History export (no export feature exists for that tab — `test-plan.md` Out of Scope).
- E2E / Playwright, performance, soak, monkey, stress (per `change-classification.md` Required Tests + `test-plan.md` Out of Scope).
- Any cross-filter / narrowing change; any new SQL JOIN where one already exists; any field rename or removal.
- Editing `css-contract.md` (read-only confirmation only — `change-classification.md` task 2.2 not-applicable). No new CSS class or token.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | hold-history SQL | Add `c.PRODUCTLINENAME` to the `ranked` CTE select AND to the outer final SELECT in `list.sql`, aliased to `package`; wrap in `TRIM(...)` for CHAR padding | backend-engineer |
| IP-2 | hold-history service | Forward `package` from SQL row to JSON response item using the existing camelCase/snake mapping; ensure `_clean_text()`/strip applied so trailing space and NULL are safe | backend-engineer |
| IP-3 | hold-history export | Confirm export CSV path emits the `package`/`Package` column (header + per-row); add if export builds its own column list rather than reusing row dicts | backend-engineer |
| IP-4 | query-tool runtime guard | Add `"PRODUCTLINENAME"` to `_PARTIAL_NONKEY_COLS_LOT` (query_tool_sql_runtime.py:31-34) BEFORE/with SQL change so QT-06 strict guard preserves it on partial-trackout merge | backend-engineer |
| IP-5 | query-tool SQL (lot history) | Add `c.PRODUCTLINENAME` (wrapped `TRIM(...)`) to `lot_history.sql` SELECT; JOIN `c` already present | backend-engineer |
| IP-6 | query-tool SQL (equip lots) | Add `c.PRODUCTLINENAME` (wrapped `TRIM(...)`) to `equipment_lots.sql` SELECT; JOIN `c` already present | backend-engineer |
| IP-7 | query-tool equip rejects | No SQL change (column at `equipment_lot_rejects.sql:52`). Confirm `_df_to_records()` pass-through includes it in response and that export columns for `export_type=equipment_rejects` already carry it; add only if missing | backend-engineer |
| IP-8 | query-tool serialization/trim | Ensure `_serialize_rows` trims `PRODUCTLINENAME` trailing space and is NULL-safe (AC-6) | backend-engineer |
| IP-9 | material-consumption SQL | Add `c.PRODUCTLINENAME` (wrapped `TRIM(...)`) to `detail_rows.sql` SELECT; LEFT JOIN `DWH.DW_MES_CONTAINER c` already present (detail_rows.sql:21-22) | backend-engineer |
| IP-10 | material-consumption runtime | Carry `PRODUCTLINENAME` through the parquet spool write in `material_consumption_duckdb_runtime.py` and forward it in the detail-page response; NULL/trailing-space safe | backend-engineer |
| IP-11 | material-consumption export | Confirm/add `PRODUCTLINENAME` column to detail CSV export in `material_consumption_routes.py` | backend-engineer |
| IP-12 | hold-history frontend | Add Package column to `DetailTable.vue` column list | frontend-engineer |
| IP-13 | query-tool frontend (lot history) | Add `PRODUCTLINENAME: 'PACKAGE'` to `COLUMN_LABELS` in `LotHistoryTable.vue` and ensure render | frontend-engineer |
| IP-14 | query-tool frontend (equip lots) | Add `{ key: 'PRODUCTLINENAME', label: 'PACKAGE' }` to `COLUMN_DEFS` in `EquipmentLotsTable.vue` | frontend-engineer |
| IP-15 | query-tool frontend (equip rejects) | Add Package column to headers + row rendering in `EquipmentRejectsTable.vue` (currently missing despite SQL having it) | frontend-engineer |
| IP-16 | material-consumption frontend | Add `{ key: 'PRODUCTLINENAME', label: 'Package', sortable: true }` to `TABLE_COLUMNS` in `DetailTable.vue` | frontend-engineer |
| IP-17 | contracts | Document the additive field per `change-classification.md` Required Contracts (see Contract Updates below) | contract-reviewer |
| IP-18 | tests | Author all New Test Functions from `test-plan.md` (red first, then green) | test-strategist / backend-engineer |

> JSON-key decision: hold-history uses snake/camel mapping → key `package`
> (per change summary). query-tool and material-consumption pass the raw Oracle
> column through their record serializers → key `PRODUCTLINENAME` (matches the
> existing pass-through convention in those two modules; do NOT rename to keep
> AC-7 additive). Confirm against `data-shape-contract.md` §3.6/§3.9.2/§3.11
> before finalizing.

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | "New Test Functions" (per file) | exact failing tests to author first |
| test-plan.md | "Acceptance Criteria → Test Mapping" (AC-1..AC-8) | AC ↔ test/file mapping |
| test-plan.md | "Notes" (TRIM/CHAR + `_PARTIAL_NONKEY_COLS_LOT` ordering + no `assert_called_once_with`) | implementation ordering + assertion style |
| ci-gates.md | "Required Gates for This Change" table | verification commands (backend-unit, frontend-unit, type-check, css-governance, contract-validate) |
| ci-gates.md | "Rollback Policy" (parquet cleanup) | material-consumption deploy/rollback runbook step |
| change-classification.md | "Required Contracts" | which contracts to update and how (additive) |
| change-classification.md | "Inferred Acceptance Criteria" AC-1..AC-8 | scope + acceptance |
| CLAUDE.md | "Oracle CHAR column lookup dicts require strip()" + MES Domain Semantics (TRACKINQTY / PH-06) | CHAR trim discipline + partial-trackout merge correctness (QT-06) |
| CLAUDE.md | "Query-tool has no persistent spool" | no parquet cleanup for query-tool |

## File-Level Plan

Backend first (so frontend can bind to confirmed JSON keys), then frontend.

| path or glob | action | notes / test reference |
|---|---|---|
| tests/test_hold_history_service.py | edit (TDD red) | Add 5 funcs per test-plan New Test Functions §hold-history. Fixture row must include `PRODUCTLINENAME` AND every existing detail column (AC-7 guard). |
| tests/test_query_tool_sql_runtime.py | edit (TDD red) | Add 8 funcs per test-plan §query-tool incl. `_PARTIAL_NONKEY_COLS_LOT` membership test + partial-trackout preservation. |
| tests/test_material_consumption_service.py | edit (TDD red) | Extend `_sample_detail_df()` to emit `PRODUCTLINENAME`; add 6 funcs per test-plan §material-consumption. |
| src/mes_dashboard/services/query_tool_sql_runtime.py | edit | IP-4: append `"PRODUCTLINENAME"` to `_PARTIAL_NONKEY_COLS_LOT` (line 31-34). IP-8: trim in `_serialize_rows`. |
| src/mes_dashboard/sql/query_tool/lot_history.sql | edit | IP-5: add `TRIM(c.PRODUCTLINENAME) AS PRODUCTLINENAME` to SELECT. |
| src/mes_dashboard/sql/query_tool/equipment_lots.sql | edit | IP-6: add `TRIM(c.PRODUCTLINENAME) AS PRODUCTLINENAME` to SELECT. |
| src/mes_dashboard/sql/query_tool/equipment_lot_rejects.sql | confirm only | IP-7: column already at line 52 — do NOT re-add. |
| src/mes_dashboard/services/query_tool_service.py | edit/confirm | IP-7: confirm equipment_rejects response + `export_type=equipment_rejects` export columns include `PRODUCTLINENAME`; equip-lots export column. |
| src/mes_dashboard/sql/hold_history/list.sql | edit | IP-1: add to `ranked` CTE select (currently selects `c.PRODUCTNAME` only, line 57) AND outer final SELECT (lines 75-91); alias `package`; use `TRIM`. |
| src/mes_dashboard/services/hold_history_service.py and/or hold_history_sql_runtime.py | edit | IP-2: forward `package` to response item; locate the existing row→item mapping; apply strip/`_clean_text()`. |
| src/mes_dashboard/routes/hold_history_routes.py | confirm/edit | IP-3: ensure export emits Package column. |
| src/mes_dashboard/sql/material_consumption/detail_rows.sql | edit | IP-9: add `TRIM(c.PRODUCTLINENAME) AS PRODUCTLINENAME`; JOIN exists (lines 21-22). |
| src/mes_dashboard/services/material_consumption_duckdb_runtime.py | edit | IP-10: include `PRODUCTLINENAME` in parquet spool write + detail-page response forward. Spool schema change → triggers parquet cleanup (see ci-gates §Rollback). |
| src/mes_dashboard/services/material_consumption_service.py | confirm/edit | IP-10: confirm detail-page response carries field through service layer. |
| src/mes_dashboard/routes/material_consumption_routes.py | confirm/edit | IP-11: ensure detail export CSV includes `PRODUCTLINENAME`. |
| frontend/src/hold-history/components/DetailTable.vue | edit | IP-12: add Package column to column list. |
| frontend/src/query-tool/components/LotHistoryTable.vue | edit | IP-13: `COLUMN_LABELS` `PRODUCTLINENAME: 'PACKAGE'` + render. |
| frontend/src/query-tool/components/EquipmentLotsTable.vue | edit | IP-14: add to `COLUMN_DEFS`. |
| frontend/src/query-tool/components/EquipmentRejectsTable.vue | edit | IP-15: add header + row cell. |
| frontend/src/material-consumption/components/DetailTable.vue | edit | IP-16: add to `TABLE_COLUMNS`. |
| contracts/api/api-contract.md | edit | IP-17: §10 — additive field on 5 endpoints (AC-8). |
| contracts/api/api-inventory.md | edit | IP-17: per additive policy. |
| contracts/data/data-shape-contract.md | edit | IP-17: §3.6, §3.9.2, §3.11 — detail-row + export schema. |
| contracts/css/css-contract.md | read-only | confirm `.theme-<feature>` scoping; no edit unless a new class is introduced (none expected). |

## Contract Updates

- API: `contracts/api/api-contract.md §10` — document additive `package` / `PRODUCTLINENAME` response field on hold-history detail, query-tool lot-history / equipment-lots / equipment-rejects, material-consumption detail. `contracts/api/api-inventory.md` — additive-policy entry. (AC-8)
- CSS/UI: `contracts/css/css-contract.md` — read-only confirmation of `.theme-<feature>` scoping; edit only if a new class is added (none expected).
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md §3.6, §3.9.2, §3.11` — new field in detail-row payload and CSV/Excel export schema. (AC-4 contract gate, AC-8)
- Business logic: none.
- CI/CD: none (existing workflows fire — `ci-gates.md §CI/CD Workflow`).

## Test Execution Plan

TDD: author all New Test Functions (`test-plan.md`) and confirm RED first:
`conda run -n mes-dashboard pytest tests/test_hold_history_service.py tests/test_query_tool_sql_runtime.py tests/test_material_consumption_service.py -x`
then implement to GREEN.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_hold_history_service.py (`test_get_hold_detail_includes_package_field`) | response row has `package` (trimmed) |
| AC-2 lot-history | tests/test_query_tool_sql_runtime.py (`test_lot_history_response_includes_productlinename`, `test_partial_nonkey_cols_lot_includes_productlinename`, `test_aggregate_partial_trackouts_preserves_productlinename`) | field present + preserved on merge |
| AC-2 equip-lots | tests/test_query_tool_sql_runtime.py (`test_equipment_lots_response_includes_productlinename`) | field present in response |
| AC-2 equip-rejects | tests/test_query_tool_sql_runtime.py (`test_equipment_rejects_response_includes_productlinename`) | field not dropped in serialization |
| AC-3 | tests/test_material_consumption_service.py (`test_get_detail_page_includes_productlinename`, `test_sample_detail_df_includes_productlinename_column`) | spool-path response carries field |
| AC-4 | `cdd-kit validate` (data-shape contract §3.6/§3.9.2/§3.11) | cdd-kit exit 0; frontend column via visual review pointer |
| AC-5 | `*_export_csv_includes_*` funcs across all 3 test files | CSV header + row include Package/PRODUCTLINENAME |
| AC-6 | `*trailing_space*` / `*null*` / `*empty_string*` funcs across all 3 test files | trimmed value; NULL/empty safe, no crash |
| AC-7 | `*existing_columns_unchanged` funcs across all 3 test files | all pre-existing keys/values retained |
| AC-8 | `cdd-kit validate` (api-contract §10) | cdd-kit exit 0 |

Gate verification commands (`ci-gates.md` Required Gates table):
- `conda run -n mes-dashboard pytest`
- `cd frontend && npm run test`
- `cd frontend && npm run type-check`
- `cd frontend && npm run css:check`
- `cdd-kit validate`

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- IP-4 (`_PARTIAL_NONKEY_COLS_LOT`) MUST land before/with IP-5/IP-6 or QT-06 strict guard silently drops the column on partial-trackout merge (`test-plan.md` Notes).
- Use `mock.assert_called_once()` + per-kwarg `call_args.kwargs[...]` assertions — never `assert_called_once_with(...)` whitelist (CLAUDE.md Test Coverage Discipline).
- Oracle CHAR `PRODUCTLINENAME` is space-padded: apply `TRIM` in SQL AND verify the service trim/`_clean_text()` runs at serialization (CLAUDE.md CHAR strip rule). Each module trims independently — test each (AC-6).
- material-consumption spool parquet schema changes: deploy/rollback runbook MUST run `rm -f tmp/query_spool/material_consumption/detail-*.parquet` (already in `ci-gates.md §Rollback Policy`). query-tool has NO persistent spool — do not add cleanup for it (CLAUDE.md).

## Known Risks

- CHAR trailing-space silent leak: highest-risk per `test-plan.md` Notes — a missing `TRIM`/strip ships invisible whitespace to JSON/CSV. Mitigated by AC-6 tests on each module independently.
- QT-06 partial-trackout merge: omitting IP-4 makes the merge drop `PRODUCTLINENAME` even though SQL selects it; the membership + preservation tests guard this.
- Spool schema mismatch: stale material-consumption parquet files without the new column raise schema-mismatch at next `read_parquet`; mitigated only by the runbook cleanup step at deploy/rollback.
- Export-path divergence: hold-history and material-consumption exports may build their own column lists rather than reusing row dicts; IP-3/IP-11 require confirming the actual export code path, not assuming reuse (CLAUDE.md "Route forwarding must be asserted per-kwarg").
- JSON-key inconsistency across modules (`package` vs `PRODUCTLINENAME`): intentional to preserve each module's existing pass-through convention and stay additive (AC-7); contract docs (IP-17) must reflect the per-endpoint key, not a single unified key.
