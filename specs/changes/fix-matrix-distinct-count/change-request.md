# Change Request

## Original Request

Fix the Production History Workcenter × Equipment Matrix aggregation bug: parent-level counts are wrong because they sum children's distinct counts instead of independently counting distinct LOT IDs.

Root cause confirmed: in `src/mes_dashboard/services/production_history_sql_runtime.py`, `compute_matrix_view` runs `COUNT(DISTINCT CONTAINERNAME)` grouped by `(wc, spec, eqp_id, month)` — correct at the leaf grain — but `_build_matrix_tree` then **sums** those leaf counts up the hierarchy (`eqp_node["count"] += count`; `spec_node["count"] += count`; `wc_node["count"] += count`) and likewise for `month_counts`. Distinct counts are not additive: one LOT ID passing through 3 SPECs of a workcenter makes each SPEC group `lot_count=1`, and the workcenter sums them to 3 when it should be `COUNT(DISTINCT CONTAINERNAME)` re-evaluated at the workcenter level = 1. The same over-count happens at the spec level (one LOT across 2 equipment) and in every level's `month_counts`. The pandas fallback `_pandas_matrix_view` shares the flaw because it feeds the same `_build_matrix_tree`.

Desired behavior: workcenter-level and spec-level `count` and `month_counts` must be `COUNT(DISTINCT CONTAINERNAME)` independently evaluated at that grain — not the sum of children. Cleanest implementation is a single DuckDB `GROUP BY GROUPING SETS` query emitting `COUNT(DISTINCT CONTAINERNAME)` for all six grain combinations (eqp×month, eqp-total, spec×month, spec-total, wc×month, wc-total), with `_build_matrix_tree` assigning each level's count from the matching grouping-set row instead of accumulating; the pandas fallback must produce the same multi-grain result.

This touches the data-shape contract (matrix `COUNT(DISTINCT CONTAINERNAME)` semantics) and business rule PH-02.

## Business / User Goal

The matrix is the engineers' top-level summary view; an inflated workcenter count
makes it untrustworthy. A LOT ID that passes through multiple specs/equipment must
be counted once per node, exactly as a distinct-count implies.

## Non-goals

- No change to the leaf (equipment × month) grain, which is already correct.
- No change to the detail table, the main query, the cross-filter cache, or the wildcard/identifier query modes.
- No change to workcenter-group mapping or sort order.
- No change to the matrix tree shape returned to the frontend (same `{label, level, count, month_counts, children}` node structure).

## Constraints

- Both code paths must be fixed and produce identical results: the DuckDB SQL path (`compute_matrix_view`) and the pandas fallback (`_pandas_matrix_view`).
- The frontend `ProductionMatrix.vue` consumes `count` / `month_counts` per node — the node shape must not change, only the values must become correct.
- Must work in both host and Docker (no hardcoded paths).

## Known Context

- Bug located at `production_history_sql_runtime.py` `compute_matrix_view` (~lines 287-303) and `_build_matrix_tree` (~lines 311-394); pandas fallback `_pandas_matrix_view` (~line 458).
- Row source is raw LOTWIPHISTORY partial track-out rows (per change `prod-history-detail-raw-rows`), so distinct-count on `CONTAINERNAME` is the established lot-count semantic (PH-02).
- DuckDB supports `GROUP BY GROUPING SETS` / `ROLLUP`.

## Open Questions

- (for spec-architect) GROUPING SETS single-query vs. per-level queries vs. raw-rows + Python distinct-set — pick the approach with the best correctness/perf/maintainability balance.

## Requested Delivery Date / Priority

User-reported correctness bug in a shipped feature. Normal priority.
