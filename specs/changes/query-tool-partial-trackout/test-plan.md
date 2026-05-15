---
change-id: query-tool-partial-trackout
schema-version: 0.1.0
last-changed: 2026-05-15
risk: medium
tier: 1
---

# Test Plan: query-tool-partial-trackout

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_query_tool_partial_trackout.py::TestLotHistoryAggregation | 0 |
| AC-1 | unit | tests/test_query_tool_partial_trackout.py::TestLotHistorySqlStructure | 0 |
| AC-2 | unit | tests/test_query_tool_partial_trackout.py::TestEquipmentLotsAggregation | 0 |
| AC-2 | unit | tests/test_query_tool_partial_trackout.py::TestEquipmentLotsSqlStructure | 0 |
| AC-3 | unit | tests/test_query_tool_partial_trackout.py::TestAdjacentLotsAggregation | 0 |
| AC-3 | unit | tests/test_query_tool_partial_trackout.py::TestAdjacentLotsRelativePosition | 0 |
| AC-4 | unit | tests/test_query_tool_partial_trackout.py::TestStrictGuardLotHistory | 0 |
| AC-4 | unit | tests/test_query_tool_partial_trackout.py::TestStrictGuardEquipmentLots | 0 |
| AC-4 | unit | tests/test_query_tool_partial_trackout.py::TestStrictGuardAdjacentLots | 0 |
| AC-5 | unit | tests/test_query_tool_partial_trackout.py::TestDecrementingTrackinQty | 0 |
| AC-6 | unit | tests/test_query_tool_partial_trackout.py::TestDecrementingTrackinQty | 0 |
| AC-7 | contract | tests/test_query_tool_partial_trackout.py::TestApiResponseShape | 0 |
| AC-7 | contract | tests/test_query_tool_sql_runtime.py (extend existing) | 0 |
| AC-8 | contract | tests/test_query_tool_partial_trackout.py::TestContractFilePresence | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | SQL structure checks (no GROUP BY + rn=1; GROUP BY + aggregates present); Python aggregation helper logic via DuckDB in-process |
| contract | 0 | File-presence assertions for business-rules.md PH-06/PH-07 query-tool enumeration; data-shape partial_count; API additive field |
| data-boundary | 0 | Divergent non-key columns per SQL path trigger raw-row fallback; decrementing TRACKINQTY fixture per SQL file |
| integration | 1 | End-to-end lot_history / equipment_lots / adjacent_lots query paths using parquet fixture fed through DuckDB runtime |

## Test Names (one per line, no bodies)

**`tests/test_query_tool_partial_trackout.py`** — new file

`TestLotHistorySqlStructure::test_lot_history_sql_has_no_row_number_dedup`
`TestLotHistorySqlStructure::test_lot_history_sql_has_group_by_four_tuple`
`TestLotHistorySqlStructure::test_lot_history_sql_projects_partial_count`
`TestLotHistorySqlStructure::test_lot_history_sql_projects_trackinqty_max`
`TestLotHistorySqlStructure::test_lot_history_sql_projects_trackoutqty_sum`

`TestEquipmentLotsSqlStructure::test_equipment_lots_sql_has_no_row_number_dedup`
`TestEquipmentLotsSqlStructure::test_equipment_lots_sql_has_group_by_four_tuple`
`TestEquipmentLotsSqlStructure::test_equipment_lots_sql_projects_partial_count`

`TestAdjacentLotsSqlStructure::test_adjacent_lots_inner_dedup_is_group_by_three_tuple`
`TestAdjacentLotsSqlStructure::test_adjacent_lots_outer_row_number_preserved`
`TestAdjacentLotsSqlStructure::test_adjacent_lots_sql_projects_partial_count`

`TestLotHistoryAggregation::test_two_partials_same_trackin_merge_to_one_row`
`TestLotHistoryAggregation::test_partial_count_equals_group_size`
`TestLotHistoryAggregation::test_different_trackin_timestamps_not_merged`
`TestLotHistoryAggregation::test_trackouttimestamp_is_max_over_group`

`TestEquipmentLotsAggregation::test_two_partials_same_trackin_merge_to_one_row`
`TestEquipmentLotsAggregation::test_partial_count_equals_group_size`
`TestEquipmentLotsAggregation::test_trackinqty_is_max_trackoutqty_is_sum`

`TestAdjacentLotsAggregation::test_two_partials_same_trackin_merge_in_inner_dedup`
`TestAdjacentLotsAggregation::test_relative_position_of_target_is_zero`
`TestAdjacentLotsRelativePosition::test_neighbors_have_correct_relative_positions_after_aggregation`

`TestStrictGuardLotHistory::test_divergent_equipmentname_emits_raw_rows_partial_count_one`
`TestStrictGuardLotHistory::test_divergent_workcentername_emits_raw_rows`
`TestStrictGuardLotHistory::test_divergent_finishedruncard_emits_raw_rows`
`TestStrictGuardLotHistory::test_consistent_non_key_columns_merge_normally`

`TestStrictGuardEquipmentLots::test_divergent_pj_type_emits_raw_rows_partial_count_one`
`TestStrictGuardEquipmentLots::test_consistent_non_key_columns_merge_normally`

`TestStrictGuardAdjacentLots::test_divergent_specname_emits_raw_rows_partial_count_one`
`TestStrictGuardAdjacentLots::test_consistent_non_key_columns_merge_normally`

`TestDecrementingTrackinQty::test_lot_history_decrementing_trackinqty_produces_max_and_sum`
`TestDecrementingTrackinQty::test_equipment_lots_decrementing_trackinqty_produces_max_and_sum`
`TestDecrementingTrackinQty::test_adjacent_lots_decrementing_trackinqty_produces_max_and_sum`

`TestApiResponseShape::test_lot_history_response_includes_partial_count_field`
`TestApiResponseShape::test_equipment_lots_response_includes_partial_count_field`
`TestApiResponseShape::test_trackinqty_trackoutqty_field_names_unchanged`

`TestContractFilePresence::test_business_rules_enumerates_query_tool_ph06`
`TestContractFilePresence::test_business_rules_enumerates_query_tool_ph07`
`TestContractFilePresence::test_data_shape_contract_includes_partial_count_query_tool`

## Fixture Discipline

Every decrementing-TRACKINQTY fixture must use the arithmetic pattern from CLAUDE.md: partial N+1 TRACKINQTY = partial N TRACKINQTY − partial N TRACKOUTQTY. Minimum required fixture per SQL file:

- Partial 1: TRACKINQTY=99424, TRACKOUTQTY=72800, TRACKINTIMESTAMP=T
- Partial 2: TRACKINQTY=26624 (=99424−72800), TRACKOUTQTY=26624, TRACKINTIMESTAMP=T

Expected aggregated result: TRACKINQTY=MAX=99424, TRACKOUTQTY=SUM=99424, partial_count=2.

A uniform-TRACKINQTY fixture (both rows TRACKINQTY=99424) is insufficient alone — it cannot distinguish 4-tuple from 5-tuple keying.

## Extend vs Create

- **Extend** `tests/test_query_tool_sql_runtime.py`: add `TestTryComputePageFromSpool::test_partial_count_present_in_returned_data` when spool contains partial rows.
- **Create** `tests/test_query_tool_partial_trackout.py` for all aggregation, SQL structure, strict-guard, and contract families above.

## Out of Scope

- E2E / browser tests (no UI change)
- Frontend display of partial_count
- Stress, soak, and monkey tests (query-tool is on-demand; classification §stress-soak-report: no)
- Other SQL files in `src/mes_dashboard/sql/query_tool/` (lot_rejects, equipment_jobs, etc. — no partial-trackout dedup)
- Oracle real-infra integration (nightly gate only; not pre-merge)

## Notes

SQL structure tests use `SQLLoader.load("query_tool/<file>")` + regex/substring checks — no Oracle connection needed; these are Tier 0.
DuckDB aggregation tests write a parquet fixture via `pandas.DataFrame.to_parquet` then call the service runtime helper directly — mirroring `TestPartialMergeAggregation` in `test_production_history_sql_runtime.py`.
Strict-guard column lists differ per SQL: lot_history/equipment_lots guard = {WORKCENTERNAME, EQUIPMENTNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID}; adjacent_lots guard = {EQUIPMENTNAME, SPECNAME, FINISHEDRUNCARD, PJ_WORKORDER, CONTAINERNAME, PJ_TYPE, PJ_BOP, WAFER_LOT_ID}.
Run command: `conda run -n mes-dashboard pytest tests/test_query_tool_partial_trackout.py tests/test_query_tool_sql_runtime.py -v`
