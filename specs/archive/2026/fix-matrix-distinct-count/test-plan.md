---
change-id: fix-matrix-distinct-count
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# Test Plan: fix-matrix-distinct-count

All tests extend `tests/test_production_history_sql_runtime.py`. **Decision:** no
test lands in `tests/test_api_contract.py` — that file is route/envelope-scoped
(Flask client + `ROUTE_CONTRACT_MATRIX`); the matrix tree distinct-count semantics
are a service-layer data-shape concern proven directly against the three functions.
Contract assertions (AC-7) therefore also live in the runtime test file, asserting
the structural rule the contract text encodes (data-shape §3.5, business PH-05).

The DuckDB and pandas paths share the `_build_matrix_tree` sink where the SUM bug
lives, so unit tests feed it flat aggregation rows directly; the parity test
additionally drives `compute_matrix_view` and `_pandas_matrix_view` end-to-end
over one identical parquet spool fixture.

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_production_history_sql_runtime.py | 0 |
| AC-2 | unit | tests/test_production_history_sql_runtime.py | 0 |
| AC-3 | unit | tests/test_production_history_sql_runtime.py | 0 |
| AC-4 | integration | tests/test_production_history_sql_runtime.py | 1 |
| AC-5 | contract | tests/test_production_history_sql_runtime.py | 0 |
| AC-6 | unit | tests/test_production_history_sql_runtime.py | 0 |
| AC-7 | contract | tests/test_production_history_sql_runtime.py | 0 |
| AC-1..AC-3 | data-boundary | tests/test_production_history_sql_runtime.py | 0 |

## Test Families Required

unit / contract / integration / data-boundary

| family | tier | notes |
|---|---|---|
| unit | 0 | `_build_matrix_tree` distinct-count assignment per grain; AC-1 anchor written failing-first. |
| contract | 0 | node-shape invariance + structural rule of data-shape §3.5 / business PH-05. |
| integration | 1 | `compute_matrix_view` (DuckDB) vs `_pandas_matrix_view` (pandas) tree equality over one shared spool fixture — central regression risk. |
| data-boundary | 0 | single-row, empty input, overlapping month buckets. |

## Test Cases (one line each — file: tests/test_production_history_sql_runtime.py)

### class TestMatrixDistinctCountRollup (unit)
- `test_one_container_three_specs_workcenter_count_is_one` — **FAILING-FIRST anchor (AC-1)**: one CONTAINERNAME across 3 SPECs under one workcenter → each spec `count == 1` AND workcenter `count == 1` (currently 3).
- `test_one_lot_two_equipment_spec_count_is_one` — AC-2: one CONTAINERNAME across 2 equipment under one spec → spec `count == 1` (currently 2).
- `test_equipment_leaf_count_unchanged` — AC-6: equipment-level leaf `count` and `month_counts` unchanged by the fix.
- `test_month_counts_distinct_at_every_level` — AC-3: spec/workcenter `month_counts[m]` = independent distinct count at that grain×month, not sum of children.
- `test_lot_spanning_two_months_one_equipment` — AC-3: one CONTAINERNAME tracked-in across 2 months at one equipment → counted once per month bucket, equipment total `count == 1`.
- `test_lot_same_month_two_specs` — AC-3: one CONTAINERNAME in the same month under 2 specs → that month_counts entry is 1 at workcenter and 1 at each spec.
- `test_distinct_containers_still_additive_when_disjoint` — guard: disjoint CONTAINERNAMEs across specs still roll up to the true distinct total (fix must not under-count).

### class TestMatrixTreeNodeShape (contract)
- `test_node_shape_unchanged` — AC-5: every tree node has exactly `{label, level, count, month_counts, children}` (equipment node also keeps `equipment_name`); no key added or removed.
- `test_parent_count_equals_independent_distinct_not_child_sum` — AC-7: structural assertion of data-shape §3.5 / business PH-05 — parent `count` ≠ Σ child `count` when a container spans children, and equals the independent distinct count.
- `test_month_columns_and_levels_preserved` — AC-5/AC-7: `level` values (`workcenter`/`spec`/`equipment`) and `month_columns` ordering preserved.

### class TestMatrixDualPathParity (integration)
- `test_duckdb_and_pandas_produce_identical_tree` — AC-4: build one parquet spool fixture, run `compute_matrix_view` and `_pandas_matrix_view` over it, assert returned trees + `month_columns` are deep-equal.
- `test_dual_path_parity_with_cross_spec_container` — AC-4: same parity assertion using a fixture where a CONTAINERNAME spans specs/equipment (exercises the rollup path on both engines).

### class TestMatrixDataBoundary (data-boundary)
- `test_single_row_input` — single aggregation row → one workcenter→spec→equipment chain, all counts == 1.
- `test_empty_input` — empty rows → `{"tree": [], "month_columns": []}`.
- `test_overlapping_month_buckets` — same (wc,spec,eqp) across multiple month buckets → per-month counts isolated, total = distinct over all months.

## Out of Scope

- E2E / visual — no UI or route behavior change; node shape unchanged.
- Detail table, main/count query, cross-filter cache, wildcard/identifier modes — not touched.
- Workcenter-group mapping and sort order — unchanged; not re-tested here.
- resilience / fuzz / monkey / stress / soak — pure aggregation correctness fix.
- Frontend `ProductionMatrix.vue` — consumes unchanged node shape (CER-002 resolved).

## Notes

- AC-1 anchor must be committed failing before the fix lands (TDD gate).
- Parity test is the central regression guard — both engines must converge.
- Contract AC-7 tests assert the *structural rule*; contract prose itself is
  reviewed by contract-reviewer, not string-matched here.
