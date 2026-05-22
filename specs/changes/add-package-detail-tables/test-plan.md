---
change-id: add-package-detail-tables
schema-version: 0.1.0
last-changed: 2026-05-22
risk: low
tier: 0
---

# Test Plan: add-package-detail-tables

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_hold_history_service.py | 0 |
| AC-2 (lot-history) | unit | tests/test_query_tool_sql_runtime.py | 0 |
| AC-2 (equip-lots) | unit | tests/test_query_tool_sql_runtime.py | 0 |
| AC-2 (equip-rejects) | unit | tests/test_query_tool_sql_runtime.py | 0 |
| AC-3 | unit | tests/test_material_consumption_service.py | 0 |
| AC-4 | contract | contracts/data/data-shape-contract.md §3.6, §3.9.2, §3.11 | 1 |
| AC-5 | unit | tests/test_hold_history_service.py, tests/test_query_tool_sql_runtime.py, tests/test_material_consumption_service.py | 0 |
| AC-6 | unit | tests/test_hold_history_service.py, tests/test_query_tool_sql_runtime.py, tests/test_material_consumption_service.py | 0 |
| AC-7 | unit | tests/test_hold_history_service.py, tests/test_query_tool_sql_runtime.py, tests/test_material_consumption_service.py | 0 |
| AC-8 | contract | contracts/api/api-contract.md §10 | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Primary gate; all behavioral assertions on service/runtime functions |
| contract | 1 | Data-shape and API contracts already updated; gate validates they hold |

## New Test Functions

### tests/test_hold_history_service.py (extend existing class TestHoldHistoryServiceFunctions)

- `test_get_hold_detail_includes_package_field` — fixture row with `PRODUCTLINENAME = "PKG-A  "` (trailing spaces); asserts response row has key `package` with value `"PKG-A"` (trimmed)
- `test_get_hold_detail_package_null_when_missing` — fixture row with `PRODUCTLINENAME = None`; asserts `package` key is present and value is `None`
- `test_get_hold_detail_package_empty_string_normalized` — fixture row with `PRODUCTLINENAME = "   "`; asserts `package` is `None` or `""` (not a padded string)
- `test_hold_detail_export_csv_includes_package_column` — invokes export helper with fixture; asserts CSV header contains `Package` and data row matches trimmed value
- `test_get_hold_detail_existing_columns_unchanged` — fixture row with both existing and new columns; asserts all pre-existing keys still present with original values (AC-7 regression guard)

### tests/test_query_tool_sql_runtime.py (extend existing class / add new classes)

- `test_partial_nonkey_cols_lot_includes_productlinename` — asserts `"PRODUCTLINENAME"` in `_PARTIAL_NONKEY_COLS_LOT` constant (QT-06 strict guard)
- `test_aggregate_partial_trackouts_preserves_productlinename` — fixture rows with `PRODUCTLINENAME = "PKG-B"`; asserts aggregated row carries the value through
- `test_lot_history_response_includes_productlinename` — mock Oracle returning a DataFrame with `PRODUCTLINENAME`; asserts response rows contain the field
- `test_equipment_lots_response_includes_productlinename` — same pattern for equipment-lots query path
- `test_equipment_lots_export_csv_includes_productlinename` — asserts export CSV header contains `PRODUCTLINENAME`
- `test_equipment_rejects_response_includes_productlinename` — assert field present in response (field already in SQL; test confirms not dropped in serialization)
- `test_equipment_rejects_export_csv_includes_productlinename` — asserts export CSV already carries field (regression guard that confirms AC-5)
- `test_productlinename_trailing_space_trimmed_in_serialization` — `_serialize_rows` with `PRODUCTLINENAME = "PKG-C  "`; asserts trimmed output (AC-6)

### tests/test_material_consumption_service.py (extend _sample_detail_df and existing classes)

- `test_sample_detail_df_includes_productlinename_column` — asserts updated `_sample_detail_df()` helper emits `PRODUCTLINENAME` column (fixture discipline guard)
- `test_get_detail_page_includes_productlinename` — spool path; fixture with `PRODUCTLINENAME = "PKG-D"`; asserts returned page rows contain the field
- `test_get_detail_page_productlinename_trailing_space_trimmed` — fixture with `PRODUCTLINENAME = "PKG-D  "`; asserts trimmed in response (AC-6)
- `test_get_detail_page_productlinename_null_safe` — fixture with `PRODUCTLINENAME = None`; no exception raised and field present in response
- `test_detail_export_csv_includes_productlinename` — export path; asserts `PRODUCTLINENAME` column in CSV output (AC-5)
- `test_get_detail_page_existing_columns_unchanged` — asserts all existing columns in `_sample_detail_df()` survive after schema extension (AC-7 regression guard)

## Out of Scope

- Frontend component rendering (AC-4) — covered by visual review and contract gate; no Vitest SFC tests added for column visibility because the column mapping is a trivial v-for/column-def addition
- query-tool Lot History export — no export feature exists for this tab; explicitly excluded per AC-5
- E2E / Playwright tests — additive column with no new interaction surface; data-boundary and unit tests are sufficient
- Performance / soak tests — column addition does not change query cost characteristics

## Notes

- All new tests must fail before implementation (TDD); run `pytest tests/test_hold_history_service.py tests/test_query_tool_sql_runtime.py tests/test_material_consumption_service.py -x` to confirm red before green.
- AC-6 (trailing-space trim) is the highest-risk silent failure: Oracle CHAR pads to fixed width; a missing `TRIM()` or `_clean_text()` call ships invisible whitespace to JSON. Each service has its own trim mechanism — test each independently.
- `_PARTIAL_NONKEY_COLS_LOT` membership test (`test_partial_nonkey_cols_lot_includes_productlinename`) must be added before any aggregate path is implemented or QT-06 strict guard will silently drop the column on merge.
- Do NOT use `mock.assert_called_once_with(...)` — use `mock.assert_called_once()` plus per-kwarg `call_args.kwargs[key]` assertions per CLAUDE.md Test Coverage Discipline.
