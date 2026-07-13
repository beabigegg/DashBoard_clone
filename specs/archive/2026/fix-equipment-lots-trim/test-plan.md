---
change-id: fix-equipment-lots-trim
schema-version: 0.1.0
last-changed: 2026-07-09
risk: medium
tier: 2
---

# Test Plan: fix-equipment-lots-trim

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (SQL TRIM correctness) | unit | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_containername_trimmed_char_padded | 0 |
| AC-1 (sibling structural pin) | unit | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_sql_trims_containername_like_productlinename | 0 |
| AC-2 (production records render non-empty) | unit | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_char_padded_fixture_returns_nonempty_rows | 0 |
| AC-3/AC-7 (frontend defensive trim + regression) | data-boundary | frontend/tests/query-tool/useLotEquipmentQuery.test.js (DONE — 3 tests, see Notes) | 0 |
| AC-4 (container_names filter, service semantics) | unit | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_container_names_filters_via_upper_trim_in | 0 |
| AC-4 (route forwarding, per-kwarg) | contract | tests/test_query_tool_routes.py::TestEquipmentPeriodEndpoint::test_equipment_lots_forwards_container_names_kwarg | 1 |
| AC-5 (narrowing before pagination clamp) | data-boundary | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_container_names_applied_in_sql_where_not_python_postfilter | 0 |
| AC-6 (backward compatible, field omitted) | unit | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_omitted_container_names_unchanged_behavior | 0 |
| AC-6 (route omitted-field regression) | contract | tests/test_query_tool_routes.py::TestEquipmentPeriodEndpoint::test_equipment_lots_forwards_pagination (existing, extend) | 1 |
| Sync/async parity — lots sub-type | integration | tests/integration/test_query_tool_rq_async.py::TestEquipmentPeriodLotsParity::test_async_job_forwards_container_names_same_as_sync_route | 1 |
| Sync/async parity — worker signature bind | integration | tests/integration/test_query_tool_rq_async.py::TestEquipmentPeriodLotsParity::test_execute_query_tool_job_lots_branch_binds_container_names_kwarg | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | tests/test_query_tool_service.py — `get_equipment_lots()` (query_tool_service.py:2430-2500 pre-fix); mock `read_sql_df_slow` per existing pattern (`test_equipment_lots_response_includes_productlinename`, lines 363-399) |
| contract | 1 | tests/test_query_tool_routes.py — extends `TestEquipmentPeriodEndpoint`/`test_equipment_lots_forwards_pagination` (lines 877-903): per-kwarg assertion on `mock_lots.call_args.kwargs`, not whitelist |
| integration | 1 | tests/integration/test_query_tool_rq_async.py — extends file; existing tests only cover `query_sub_type='status_hours'` (lines 39-169), none cover `'lots'` — new class required |
| data-boundary | 0/1 | CHAR-padded + case-variant CONTAINERNAME fixtures, backend (unit, pending) + frontend (already done) |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

None. Existing tests (`test_equipment_lots_forwards_pagination`, `TestFlagOnOversizedQuery`/`TestFlagOffParity` in test_query_tool_rq_async.py) keep their current expectations unchanged; this change only adds new tests/cases alongside them.

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope
- E2E / visual / resilience / fuzz / stress / soak (per change-classification.md Required Tests — all `no`)
- CSV export path (`_format_equipment_lots_export_rows`, query_tool_routes.py:310-329) — no container_names wiring requested for export
- `materials`/`jobs`/`status_hours` sub-types — container_names is `lots`-only per AC-4/change-request scope

## Notes
- Frontend (DONE): `frontend/tests/query-tool/useLotEquipmentQuery.test.js` — 3 tests: (1) `queryLots` trims/uppercases CHAR-padded CONTAINERNAME regression, (2) same for `queryRejects`, (3) contract test proving `container_names` appears only on `query_type='lots'` POST body, absent on `jobs`/`rejects`. Ran via `cdd-kit test run`; vitest + vue-tsc green; recorded in test-evidence.yml.
- Backend SQL fixture: mock `read_sql_df_slow` returning a DataFrame with `CONTAINERNAME` values like `'ga25081329-a01   '` (CHAR-padded, mixed case) to prove trim+match end-to-end through `get_equipment_lots()` → `_df_to_records`.
- AC-5 test must assert the WHERE-clause SQL/`QueryBuilder` params carry `container_names`, not that Python filters `records` post-`_df_to_records` — pin via `mock_load.call_args.kwargs`, mirroring the `_resolve_by_work_order` pattern (test_query_tool_service.py lines 359-368).
- Worker signature check: `inspect.signature(execute_query_tool_job).bind(**expected_kwargs)` per docs/architecture/test-discipline.md §Async Route↔Worker Signature Contract — the `query_sub_type == "lots"` branch (query_tool_service.py:2893-2894 pre-fix) currently omits `container_names` when calling `get_equipment_lots()`; this is the exact parity gap AC-4 requires closing.
- Existing `TestFlagOnOversizedQuery`/`TestFlagOffParity` classes only exercise `status_hours`; do not duplicate flag-on/off coverage, only add the `lots`+`container_names` parity gap.
