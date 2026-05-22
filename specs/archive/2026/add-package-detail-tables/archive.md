# Archive: add-package-detail-tables

## Change Summary

Audited all detail tables in the MES Dashboard that display lot or workorder data and added the missing `PRODUCTLINENAME` (Package) field to five surfaces that lacked it: hold-history detail, query-tool LotHistoryTable, query-tool EquipmentLotsTable, query-tool EquipmentRejectsTable (frontend only — SQL already had the column), and material-consumption detail. The rule applied: any table with a LOT ID or WORKORDER column must surface package/type information. CSV exports for EquipmentLots and material-consumption were updated in the same pass.

## Final Behavior

- **hold-history detail** (`/api/hold-history/list`): response now includes `package` (snake_case, via `_clean_text()`). Spool backward-compat: `hold_history_sql_runtime._query_list` uses `DESCRIBE hold_src` at runtime to detect old parquets lacking the column and falls back to `NULL AS package`.
- **query-tool LotHistoryTable** (`/api/query-tool/lots/history`): response now passes through `PRODUCTLINENAME`; frontend label `PACKAGE`.
- **query-tool EquipmentLotsTable** (`/api/query-tool/lots/equipment`): response and CSV export now include `PRODUCTLINENAME`.
- **query-tool EquipmentRejectsTable** (`/api/query-tool/lots/rejects`): SQL already returned `PRODUCTLINENAME` at line 52; frontend template now renders and sorts by it.
- **material-consumption detail** (`/api/material-consumption/detail/page`, `/export`): spool query and DuckDB runtime now include `PRODUCTLINENAME`; CSV export header updated.

## Final Contracts Updated

| Contract | Version bump | Change |
|---|---|---|
| `contracts/api/api-contract.md` | 1.10.0 → 1.11.0 | Added `PRODUCTLINENAME`/`package` to §10 for all 5 endpoints; additive, backward-compatible |
| `contracts/api/api-inventory.md` | 1.1.9 → 1.1.10 | Updated table rows for `hold_history_routes.py`, `query_tool_routes.py`, `material_consumption_routes.py` |
| `contracts/data/data-shape-contract.md` | 1.9.0 → 1.10.0 | Added PRODUCTLINENAME to §3.6 (QT lot rows) with `_PARTIAL_NONKEY_COLS_LOT` note; added to §3.9.2 (material-consumption spool); added new §3.11 (hold-history detail row — first-time baseline documentation) |
| `contracts/CHANGELOG.md` | — | Added three header entries: `[api 1.11.0]`, `[api-inventory 1.1.10]`, `[data 1.10.0]` |

Evidence: `agent-log/contract-reviewer.yml`

## Final Tests Added / Updated

| File | Tests | Coverage |
|---|---|---|
| `tests/test_hold_history_service.py` | `TestHoldHistoryListPackageField` (4 tests) | trimmed value, null, empty-string normalization, existing columns unchanged |
| `tests/test_query_tool_sql_runtime.py` | 8 tests across 5 classes | `_PARTIAL_NONKEY_COLS_LOT` membership, partial-trackout preservation, CHAR trim in serialize_rows, NULL safety, LotHistory/EquipmentLots response+export, EquipmentRejects response+export |
| `tests/test_material_consumption_service.py` | 6 tests | fixture discipline, spool-path response, trailing-space trim, NULL safety, AC-7 regression guard, CSV export header |

Full suite result: **4123 passed, 550 skipped, 0 failed**. Evidence: `agent-log/backend-engineer.yml`.

## Final CI/CD Gates

All Tier 1 gates required: `backend-unit`, `frontend-unit`, `type-check`, `css-governance`, `contract-validate`. `python-lint` informational only. No new workflow files. Parquet cleanup required on deploy/rollback for material-consumption: `rm -f tmp/query_spool/material_consumption/detail-*.parquet`. Evidence: `ci-gates.md`.

## Production Reality Findings

- `equipment_lot_rejects.sql` already had `PRODUCTLINENAME` at line 52 but the frontend template never rendered it. The SQL was correct; only the frontend was missing the column.
- `hold_history_sql_runtime._query_list` required a `DESCRIBE`-based spool-compat guard rather than a simple column add, because old parquet spools would cause a `BinderException` at `read_parquet` time without it.
- Two-layer SQL add was required for `hold_history/list.sql`: column must appear in both the `ranked` CTE's SELECT and the outer final SELECT.
- `_PARTIAL_NONKEY_COLS_LOT` in `query_tool_sql_runtime.py` must include every non-key column returned by lot-history/equipment-lots SQL; omitting `PRODUCTLINENAME` would have caused the QT-06 strict guard to silently collapse rows with divergent package values.
- material-consumption spool parquet schema change is the sole deployment risk — hold-history and query-tool have no persistent spool files.

## Lessons Promoted to Standards

All promotions target `CLAUDE.md` only (guidance). No contract schema version bumps required.

| Lesson | Target | Evidence |
|---|---|---|
| CTE SQL changes require updates in both CTE SELECT and outer SELECT | `CLAUDE.md` § SQL Architecture Notes | `backend-engineer.yml` (lot_history.sql:36,59-61; equipment_lots.sql:34,57-61; hold_history/list.sql:70,89) |
| `_PARTIAL_NONKEY_COLS_LOT` must include every non-key column returned by lot-history/equipment-lots SQL | `CLAUDE.md` § QueryBuilder Architecture Notes | `contract-reviewer.yml` key-finding; `backend-engineer.yml` line 28 |
| hold-history spool `DESCRIBE`-based column detection for backward compat | `CLAUDE.md` § Cache Architecture Notes | `backend-engineer.yml` line 17,30 |
| SQL-to-frontend column gap invisible to backend-only audits | `CLAUDE.md` § SQL Architecture Notes | `backend-engineer.yml` line 29 (equipment_lot_rejects.sql confirmed read-only) |

Candidate 4 (material-consumption parquet cleanup) not promoted — duplicates existing "Spool schema breaking changes" rule already in `CLAUDE.md`.

## Follow-up Work

- None identified. All 5 surfaces fully covered including exports.

---

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
