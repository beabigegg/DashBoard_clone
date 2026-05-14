# Archive — fix-matrix-distinct-count

## Change Summary

Tier 2 backend-only bug fix. `_build_matrix_tree` in
`production_history_sql_runtime.py` summed non-additive leaf
`COUNT(DISTINCT CONTAINERNAME)` values up the workcenter × equipment matrix
hierarchy, inflating workcenter and spec counts (e.g. one LOT across 3 specs
showed workcenter count=3 instead of 1). Fixed via Option C: the matrix view
now emits raw `SELECT DISTINCT (wc, spec, eqp_id, eqp_name, month, container)`
tuples and `_build_matrix_tree` accumulates a Python `set()` of containers per
node and per node×month, deriving `count` / `month_counts` via `len()` in
`_flatten`. Single counting site — canonical workcenter-group dedup happens
naturally because containers land in the same group node's set.

## Final Behavior

Parent (workcenter, spec) `count` and `month_counts` are now independent
distinct counts re-evaluated at each grain, not the sum of child counts. Leaf
(equipment × month) grain is unchanged. Node output shape is unchanged
(`{label, level, count, month_counts, children}`). DuckDB and pandas-fallback
paths produce identical trees.

## Final Contracts Updated

- `contracts/data/data-shape-contract.md` 1.2.0 → 1.3.0 — added §3.5
  Production-History Matrix Tree Node (node shape + distinct-count grain rule:
  parent counts non-additive); tightened §3.4 trailing sentence.
- `contracts/business/business-rules.md` 1.4.0 → 1.5.0 — added PH-05 (matrix
  distinct-count non-additivity) + PH-02 cross-reference clause.
- `contracts/CHANGELOG.md` — 2 entries dated 2026-05-14.

## Final Tests Added / Updated

15 new tests in `tests/test_production_history_sql_runtime.py` across 4 classes:
`TestMatrixDistinctCountRollup` (7, incl. failing-first anchor
`test_one_container_three_specs_workcenter_count_is_one`),
`TestMatrixTreeNodeShape` (3), `TestMatrixDualPathParity` (2),
`TestMatrixDataBoundary` (3). TDD failing-first confirmed (11/15 failed
pre-fix). Full local sweep: 97 passed.

## Final CI/CD Gates

No new workflow files. 15 new tests absorbed by the existing
`unit-mock-integration` gate. ci-gates.md Rollback Policy: pure in-memory
aggregation fix over an unchanged row source — revert is code-only, no parquet
cleanup needed. CI green on commit `ff6ec44` (user-confirmed 2026-05-14).

## Production Reality Findings

- mypy not run — not installed in the `mes-dashboard` conda env, not pinned in
  `environment.yml`. Pre-existing informational gate; new code is fully
  type-annotated. Status unchanged by this change.
- Dual-path parity tests verify the SQL-vs-pandas row contract, not the
  counting logic (that would be tautological since both feed the same
  `_build_matrix_tree` sink) — value-correctness is covered by the unit +
  node-shape + data-boundary tests feeding rows directly.

## Lessons Promoted to Standards

None promoted at close. The durable rule (parent matrix counts are
non-additive distinct counts re-evaluated per grain) was already promoted
**during /cdd-new** to `contracts/data/data-shape-contract.md` §3.5 and
`contracts/business/business-rules.md` PH-05 — the contract is the
promotion. No additional process or guidance lesson emerged from the
evidence.

## Follow-up Work

None.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`).
