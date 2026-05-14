# QA Report — fix-matrix-distinct-count

## Summary

Tier 2 backend-only bug fix. `_build_matrix_tree` summed non-additive leaf
`COUNT(DISTINCT CONTAINERNAME)` values up the hierarchy, inflating workcenter
and spec counts. Fixed via proposal Option C: `compute_matrix_view` emits
`SELECT DISTINCT (wc, spec, eqp_id, eqp_name, month, container)` raw tuples,
`_pandas_matrix_view` mirrors via `drop_duplicates()`, and `_build_matrix_tree`
accumulates a Python `set()` of containers per node and per node×month, deriving
`count` / `month_counts` via `len()` in `_flatten`. Node output shape unchanged.

## Gate Results

| gate | command | result |
|---|---|---|
| lint | `ruff check` (changed files) | pass — "All checks passed!" |
| backend tests | `pytest test_production_history_sql_runtime.py test_production_history_routes.py test_api_contract.py` | pass — 97 passed in 33.03s |
| contract-validate | `cdd-kit validate --contracts` | pass — "All validations passed." |
| gate-readiness | `cdd-kit gate fix-matrix-distinct-count` | pass — "gate passed" (tasks pending, warning-only non-strict) |
| type-check (mypy) | `mypy src/` | not run — mypy not installed in `mes-dashboard` conda env; informational/non-blocking per ci-gates.md |

## Acceptance-Criteria Verification

| AC | status | evidence (test name / file) |
|---|---|---|
| AC-1 — LOT through 3 SPECs under one WC shows count=1 at each spec and WC | covered | `TestMatrixDistinctCountRollup::test_one_container_three_specs_workcenter_count_is_one` — failing-first anchor, showed WC count==3 pre-fix, asserts ==1 |
| AC-2 — LOT through 2 equipment under one SPEC shows spec count=1; leaf counts unchanged | covered | `test_one_lot_two_equipment_spec_count_is_one` — asserts spec count==1, WC count==1, both equipment leaves==1 |
| AC-3 — `month_counts` at every level is independent distinct count, not sum | covered | `test_month_counts_distinct_at_every_level`, `test_lot_spanning_two_months_one_equipment`, `test_lot_same_month_two_specs` |
| AC-4 — DuckDB path and pandas fallback produce identical trees | covered | `TestMatrixDualPathParity::test_duckdb_and_pandas_produce_identical_tree`, `test_dual_path_parity_with_cross_spec_container` — end-to-end `compute_matrix_view` vs `_pandas_matrix_view` over shared parquet fixture |
| AC-5 — node shape unchanged `{label, level, count, month_counts, children}` | covered | `TestMatrixTreeNodeShape::test_node_shape_unchanged`, `test_month_columns_and_levels_preserved` |
| AC-6 — leaf (equipment×month) grain counts unchanged | covered | `test_equipment_leaf_count_unchanged`, `test_overlapping_month_buckets` |
| AC-7 — data-shape + business PH-05 updated | covered | data-shape §3.5 + business PH-05 + PH-02 cross-ref verified at source; `test_parent_count_equals_independent_distinct_not_child_sum`; `cdd-kit validate --contracts` green |

All 7 ACs covered. No partial or not-covered criteria.

## Test-Evidence Summary

- 15 new tests across 4 classes in `tests/test_production_history_sql_runtime.py`:
  `TestMatrixDistinctCountRollup` (7), `TestMatrixTreeNodeShape` (3),
  `TestMatrixDualPathParity` (2), `TestMatrixDataBoundary` (3).
- TDD failing-first confirmed: 11/15 failed pre-fix; anchor showed workcenter count==3.
- Full local sweep: 97 passed (sql_runtime + routes + api_contract), ruff clean,
  contract validation green, gate passed.

## Risks / Residual Gaps

1. **mypy not run** — not installed in the `mes-dashboard` conda env, not pinned
   in `environment.yml`. Pre-existing informational gate per ci-gate-contract; new
   code is fully type-annotated. Non-blocking, status unchanged by this change.
2. **Parity test independence** — assessed. `compute_matrix_view` and
   `_pandas_matrix_view` both feed the same `_build_matrix_tree` sink, so the
   parity tests verify the **SQL-vs-pandas row contract** (that `SELECT DISTINCT`
   and `drop_duplicates()` over the same six columns produce equivalent row
   streams), NOT the counting logic — that would be tautological. The
   **value-correctness of `_build_matrix_tree`** is covered by the 7 rollup + 3
   node-shape + 3 data-boundary unit tests feeding it rows directly. Correct
   division of coverage for an Option-C single-counting-site design — adequate.
3. **No real-Oracle / real-spool integration run** — parity uses synthetic
   parquet fixtures. Acceptable: pure in-memory aggregation fix over an unchanged
   row source; no spool schema change, no parquet cleanup needed.

## Failures

None.

## Pre-existing Failures Excluded From This Gate

None. (mypy is a tooling-availability gap, not a test failure — see Residual Gaps #1.)

## Fixback Routing

None — all gates green, all ACs covered, contracts verified at source.

## Decision

**approved** — all required gates green, all 7 ACs covered with test evidence,
contracts updated and validated, dual-path parity confirmed. The only residual
item (mypy not installed) is a pre-existing non-blocking informational gate.
