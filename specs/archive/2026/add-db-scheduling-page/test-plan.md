---
change-id: add-db-scheduling-page
schema-version: 0.1.0
last-changed: 2026-06-26
risk: medium
tier: 2
---

# Test Plan: add-db-scheduling-page

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1: all D/B-START lots appear in queue | unit | tests/test_db_scheduling_service.py::test_all_db_start_lots_included | 0 |
| AC-1: null BOP → zero rows, no error | unit | tests/test_db_scheduling_service.py::test_null_bop_returns_empty_rows | 0 |
| AC-2: WORKFLOWNAME match → equipment set, matchSource=workflow | unit | tests/test_db_scheduling_service.py::test_workflow_match_sets_equipment_and_source | 0 |
| AC-3: BOP prefix U→Eutectic, E→Epoxy D/B, P→DBCB group | unit | tests/test_db_scheduling_service.py::test_bop_fallback_prefix_routing | 0 |
| AC-3: BOP fallback sets matchSource=bop-fallback | unit | tests/test_db_scheduling_service.py::test_bop_fallback_match_source | 0 |
| AC-4: sort PACKAGE_LEF→PJ_TYPE→WAFERLOT→UTS ASC NULLS LAST | unit | tests/test_db_scheduling_service.py::test_sort_order_nulls_last | 0 |
| AC-5: matchSource=none when no workflow match and no BOP | unit | tests/test_db_scheduling_service.py::test_no_match_no_bop_returns_none_source | 0 |
| AC-6: 401 if unauthenticated | unit | tests/test_db_scheduling_routes.py::test_queue_requires_auth_returns_401 | 0 |
| AC-6: 200 + correct response envelope for authenticated call | unit | tests/test_db_scheduling_routes.py::test_queue_authenticated_returns_200_with_shape | 0 |
| AC-6: matchSource closed enum (workflow/bop-fallback/none only) | contract | tests/test_db_scheduling_routes.py::test_queue_match_source_values_in_closed_enum | 1 |
| AC-7: 生產輔助 drawer at order 7 in navigationManifest | unit | tests/test_db_scheduling_navigation.py::test_page_status_db_scheduling_is_dev_or_released | 0 |
| AC-7: /db-scheduling route present in all-pages list | unit | tests/test_db_scheduling_navigation.py::test_db_scheduling_in_all_pages | 0 |
| AC-7: page_status.json entry present for db-scheduling | unit | tests/test_db_scheduling_navigation.py::test_page_status_entry_exists | 0 |
| AC-8: queue table renders with all required columns | e2e | frontend/tests/playwright/db-scheduling.spec.ts::renders queue table columns | 1 |
| AC-8: empty state shown when API returns no lots | e2e | frontend/tests/playwright/db-scheduling.spec.ts::empty state on zero lots | 1 |
| AC-8: CSS scoped to .theme-db-scheduling | gate | npm run css:check (changed-area gate) | 1 |
| AC-1..6: contract sample captured for new endpoint | contract | tests/contract/test_capture_samples.py (extend sample count) | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Service: lot filtering, workflow match, BOP prefix dispatch, sort. Route: auth guard, response envelope. Navigation: drawer order + link. All Oracle calls mocked. |
| contract | 1 | matchSource enum validation; extend test_capture_samples.py count by 1 for new endpoint sample. |
| e2e | 1 | Playwright with mocked /api/db-scheduling/queue: table render, empty state. Register catch-all FIRST, specific route LAST (LIFO). |
| data-boundary | 1 | All-null sort keys (NULLS LAST); lot with EQUIPMENTS IS NULL (no workflow match); BOP unknown prefix → matchSource=none. |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/contract/test_capture_samples.py (sample count assertion) | update | +1 sample for /api/db-scheduling/queue |

## Out of Scope

- MES write paths (endpoint is read-only per AC-5 / DB-05)
- Redis cache or RQ async path (sync endpoint, no async flag)
- Oracle XE real-infra integration (mocked at oracle boundary in Tier-0)
- Stress / soak tests (read-only, single query, no concurrency concern in V1)
- Cross-filter UI narrowing (no filter controls in V1)

## Notes

- `tests/test_db_scheduling_service.py` and `tests/test_db_scheduling_routes.py` are new files to create.
- BOP fallback test must cover all three defined prefix branches (U, E, P) plus unknown prefix → none.
- Sort test must include rows where PACKAGE_LEF and UTS are NULL to prove NULLS LAST, not just happy-path sorted data.
- `db-scheduling.spec.ts` must follow LIFO route registration: catch-all first, specific API route last.
- Extend `tests/test_navigation_contract.py` or add `tests/test_db_scheduling_navigation.py`; do not duplicate the drawer-validation logic.
