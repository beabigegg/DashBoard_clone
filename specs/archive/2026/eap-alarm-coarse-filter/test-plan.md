---
change-id: eap-alarm-coarse-filter
schema-version: 0.1.0
last-changed: 2026-06-30
risk: medium
tier: 1
---

# Test Plan: eap-alarm-coarse-filter

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1: lot_ids → LOT_ID IN (...); spool key reflects lot_ids | unit | tests/test_eap_alarm_service.py::TestSpoolKeyComposition | 0 |
| AC-1: lot_ids → LOT_ID IN (...); spool key reflects lot_ids | integration | tests/integration/test_eap_alarm_rq_async.py | 1 |
| AC-2: product_dims → EXISTS semi-join; no row duplication | unit | tests/test_eap_alarm_service.py::TestProductDimsFilter | 0 |
| AC-2: product_dims → EXISTS semi-join; no row duplication | data-boundary | tests/integration/test_eap_alarm_data_boundary.py | 1 |
| AC-3: machines optional; at least one of three required; all-empty → 400 | unit | tests/test_eap_alarm_service.py::TestAtLeastOneFilterRequired | 0 |
| AC-3: all-empty → 400 route response | resilience | tests/integration/test_eap_alarm_resilience.py | 1 |
| AC-4: same params = same key; any dim change = different key; schema_version=3 | unit | tests/test_eap_alarm_service.py::TestSchemaVersionIsPinned | 0 |
| AC-4: lot_ids/product_dims change → different spool key | unit | tests/test_eap_alarm_service.py::TestSpoolKeyComposition | 0 |
| AC-5: mixed-axis AND; whitespace/duplicate lot_ids normalized | unit | tests/test_eap_alarm_service.py::TestLotIdNormalization | 0 |
| AC-5: CHAR-padded CONTAINERNAME; mixed-axis intersection | data-boundary | tests/integration/test_eap_alarm_data_boundary.py | 1 |
| AC-6: FilterBar LOT_ID textarea + TYPE/PKG/BOP MultiSelects; buildCoarseParams per-kwarg | unit | frontend/tests/unit/eap-alarm-filter.test.js | 0 |
| AC-6: FilterBar flow; machines-optional submission | e2e | frontend/tests/playwright/eap-alarm-filters.spec.ts | 1 |
| AC-7: Oracle error during EXISTS → resilience contract; cache miss → empty arrays | resilience | tests/integration/test_eap_alarm_resilience.py | 1 |
| AC-8: `_build_equipment_filter([])` → `1=1` no-op (not `IN ()`); regression proof | unit | tests/test_eap_alarm_service.py::TestEquipmentFilterEmptyNoOp | 0 |
| AC-8: `eqp_types=[]` + `product_lines`-only reaches worker SQL without ORA-00936 | resilience | tests/integration/test_eap_alarm_resilience.py::test_empty_eqp_types_with_product_dims_only_builds_valid_sql | 1 |
| AC-9: `eqp_types` validation accepts any non-empty stripped string (no enum) | unit | tests/test_eap_alarm_service.py::TestMachinesValidation | 0 |
| AC-9: real `EQUIPMENT_ID`-shaped value (e.g. `GWBK-0241`) passes validation | unit | tests/test_eap_alarm_service.py::TestMachinesValidation::test_full_equipment_id_string_no_error | 0 |
| AC-10: family-only (no machine) expands submitted `machines` to full filtered `machineOptions` | unit | frontend/tests/unit/eap-alarm-filter.test.js::describe('FilterBar handleSubmit family expansion') | 0 |
| AC-10: family + specific machine(s) selected submits exactly those machines unchanged | unit | frontend/tests/unit/eap-alarm-filter.test.js::describe('FilterBar handleSubmit family expansion') | 0 |
| AC-10: neither family nor machine selected submits empty `machines` unchanged | unit | frontend/tests/unit/eap-alarm-filter.test.js::describe('FilterBar handleSubmit family expansion') | 0 |
| AC-10: family-only submission end-to-end (mocked API) reaches backend with full machine list | e2e | frontend/tests/playwright/eap-alarm-filters.spec.ts | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Extend `tests/test_eap_alarm_service.py`: new classes `TestAtLeastOneFilterRequired`, `TestLotIdNormalization`, `TestProductDimsFilter`; update `TestSchemaVersionIsPinned` to assert `== 3`; extend `TestSpoolKeyComposition` for lot_ids and product_dim dims. Use `call_args.kwargs[key]` per-kwarg assertions throughout. |
| data-boundary | 1 | Extend `tests/integration/test_eap_alarm_data_boundary.py`: whitespace-only lot_ids, duplicate lot_ids, CHAR-padded CONTAINERNAME, over-200-lot_ids boundary (strictly > 200), product-dim no-match returns zero rows, lot_ids + product_dims combined returns intersection only. |
| resilience | 1 | Extend `tests/integration/test_eap_alarm_resilience.py`: `test_oracle_error_during_exists_semijoin`, `test_container_filter_cache_miss_returns_empty_arrays` (not 500), `test_all_filters_empty_returns_400`. |
| integration | 1 | Extend `tests/integration/test_eap_alarm_rq_async.py`: `TestEapAlarmWorkerFnNewDims` — mock Oracle, assert lot_ids IN clause and EXISTS semi-join in SQL; assert route forwards `lot_ids`, `pj_types`, `product_lines`, `pj_bops` per-kwarg with non-default values. |
| unit (frontend) | 0 | Extend `frontend/tests/unit/eap-alarm-filter.test.js`: `describe('buildCoarseParams')` — lot_ids forwarded per-kwarg, pj_types/product_lines/pj_bops forwarded per-kwarg, empty dims omitted, machines-absent accepted when lot_ids present. |
| e2e | 1 | New `frontend/tests/playwright/eap-alarm-filters.spec.ts`: LOT_ID textarea visible and submittable; TYPE/PKG/BOP MultiSelects load product-filter-options; machines-optional submission accepted (200); all-empty submit shows inline 400 error. |
| unit (round-2 regression) | 0 | New `tests/test_eap_alarm_service.py::TestEquipmentFilterEmptyNoOp` — direct call of `_build_equipment_filter([])`, assert returned SQL fragment is `1=1`, not `e.EQUIPMENT_ID IN ()`. Pure function, no mocking. |
| resilience (round-2 regression) | 1 | Extend `tests/integration/test_eap_alarm_resilience.py`: `test_empty_eqp_types_with_product_dims_only_builds_valid_sql` — mock `read_sql_df_slow` (same pattern as `test_oracle_failure_during_spool`), call `run_eap_alarm_query_job(eqp_types=[], product_lines=["SOT-223"])`, assert captured SQL contains `1=1` and does NOT contain `IN ()`; this is the exact EA-08-legal combo that produced ORA-00936 in production. |
| unit (round-2 regression, frontend) | 0 | Extend `frontend/tests/unit/eap-alarm-filter.test.js` (mount `FilterBar.vue` via `@vue/test-utils`): family selected + `filters.machines=[]` → emitted `submit` payload's `machines` equals all `machineOptions` names for that family; family + explicit machines → emitted payload unchanged; no family/no machine → emitted `machines` stays `[]`. |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_eap_alarm_service.py::TestSchemaVersionIsPinned::test_schema_version_equals_two | update | schema_version 2→3 per AC-4; assert `== 3` |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_empty_list_raises_value_error | update | machines now optional; error message changes to at-least-one-of-three contract per AC-3 |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_none_raises_value_error | update | same as above |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_single_valid_eqp_type_no_error (L160-162) | update | D-7: asserts `eqp_types=["GWBK"]` passes; still true post-fix but no longer proves an enum check — rename/repurpose to prove non-enum acceptance (no assertion change needed, docstring/name only) |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_multiple_valid_eqp_types_no_error (L164-166) | update | D-7: asserts `["GDBA","GWBK","GWBA"]` passes against the closed enum; enum is dropped, so this must be re-scoped to "any non-empty strings pass" (values stay enum-shaped incidentally, not because of membership) |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_empty_string_in_list_raises_value_error (L180-183) | keep | blank-string rejection is unaffected by D-7 (mirrors `lot_ids` blank-entry rule) |
| (new) tests/test_eap_alarm_service.py::TestMachinesValidation::test_full_equipment_id_string_no_error | add | D-7: `eqp_types=["GWBK-0241"]` (real `EQUIPMENT_ID` shape, not a 4-char code) must pass — this is the exact value class the old enum rejected/never matched; proves the enum removal, not just its absence |
| (new) tests/test_eap_alarm_service.py::TestMachinesValidation::test_out_of_old_enum_value_no_longer_raises | add | D-7: a value that was never in `_VALID_EQP_TYPES` (e.g. `"ZZZZ"`) must now pass validation — proves the membership check is gone, not merely untested |

## Out of Scope

- Stress / soak / monkey: coarse filter reduces query volume; not a new high-load path.
- Visual snapshot regression: covered by agent-log/visual-reviewer.yml.
- Real Oracle / real Redis: `integration_real` (Tier 3 nightly) — no new cases needed in this PR.
- v2 parquet migration: schema_version bump auto-invalidates; no backfill tests required.

## Notes

- `TestSchemaVersionIsPinned` update is the required red-green signal: it must fail before implementation and pass after.
- Over-limit lot_ids boundary test must use `len(lot_ids) > 200` (strictly exceeds cap, not `== 200`).
- Both `test_eap_alarm_data_boundary.py` and `test_eap_alarm_resilience.py` use `pytestmark = pytest.mark.integration`; new cases in those files must not add `integration_real`.
- Route forwarding assertions must use `call_args.kwargs[key]` per individual kwarg, not `assert_called_once_with()` whitelist.
- **Round 2 (D-6/D-7/D-8):** `test_empty_eqp_types_with_product_dims_only_builds_valid_sql` (AC-8) is the required red-green signal for this round — it must fail (ORA-00936-shaped `IN ()` present in captured SQL) before the `_build_equipment_filter` fix and pass after, same role `TestSchemaVersionIsPinned` played in round 1.
- **Root cause of the escaped defect:** round-1's AC-1/AC-2 unit tests exercised `eqp_types` non-empty (spool-key/IN-clause cases) and `product_dims` non-empty separately, but never the combination `eqp_types=[]` + a non-empty product dim — the one EA-08-legal shape that hits the unconditional `AND {equipment_filter}` splice with an empty list. AC-8's two new rows close that exact gap; do not let `_build_equipment_filter` tests stay single-argument-only again.
