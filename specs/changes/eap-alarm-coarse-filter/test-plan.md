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

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Extend `tests/test_eap_alarm_service.py`: new classes `TestAtLeastOneFilterRequired`, `TestLotIdNormalization`, `TestProductDimsFilter`; update `TestSchemaVersionIsPinned` to assert `== 3`; extend `TestSpoolKeyComposition` for lot_ids and product_dim dims. Use `call_args.kwargs[key]` per-kwarg assertions throughout. |
| data-boundary | 1 | Extend `tests/integration/test_eap_alarm_data_boundary.py`: whitespace-only lot_ids, duplicate lot_ids, CHAR-padded CONTAINERNAME, over-200-lot_ids boundary (strictly > 200), product-dim no-match returns zero rows, lot_ids + product_dims combined returns intersection only. |
| resilience | 1 | Extend `tests/integration/test_eap_alarm_resilience.py`: `test_oracle_error_during_exists_semijoin`, `test_container_filter_cache_miss_returns_empty_arrays` (not 500), `test_all_filters_empty_returns_400`. |
| integration | 1 | Extend `tests/integration/test_eap_alarm_rq_async.py`: `TestEapAlarmWorkerFnNewDims` — mock Oracle, assert lot_ids IN clause and EXISTS semi-join in SQL; assert route forwards `lot_ids`, `pj_types`, `product_lines`, `pj_bops` per-kwarg with non-default values. |
| unit (frontend) | 0 | Extend `frontend/tests/unit/eap-alarm-filter.test.js`: `describe('buildCoarseParams')` — lot_ids forwarded per-kwarg, pj_types/product_lines/pj_bops forwarded per-kwarg, empty dims omitted, machines-absent accepted when lot_ids present. |
| e2e | 1 | New `frontend/tests/playwright/eap-alarm-filters.spec.ts`: LOT_ID textarea visible and submittable; TYPE/PKG/BOP MultiSelects load product-filter-options; machines-optional submission accepted (200); all-empty submit shows inline 400 error. |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_eap_alarm_service.py::TestSchemaVersionIsPinned::test_schema_version_equals_two | update | schema_version 2→3 per AC-4; assert `== 3` |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_empty_list_raises_value_error | update | machines now optional; error message changes to at-least-one-of-three contract per AC-3 |
| tests/test_eap_alarm_service.py::TestMachinesValidation::test_none_raises_value_error | update | same as above |

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
