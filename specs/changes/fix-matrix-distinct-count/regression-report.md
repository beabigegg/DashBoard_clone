# Regression Report — fix-matrix-distinct-count

## Scope

Verify the matrix distinct-count fix does not regress (a) leaf equipment×month
grain (AC-6), (b) node shape (AC-5), and (c) untouched surfaces — detail table,
main/count query, cross-filter cache, workcenter-group mapping/sort order.

## AC-6 — Leaf (equipment × month) counts unchanged

- The leaf grain was already correct (the sum bug only affected ancestors). Under
  Option C the leaf node's `_containers` set is populated from the same distinct
  `(wc, spec, eqp, month, container)` tuples — `len(set)` at the leaf equals the
  prior `COUNT(DISTINCT CONTAINERNAME) GROUP BY (wc,spec,eqp,month)` because no
  rollup is involved at the leaf.
- Direct evidence: `test_equipment_leaf_count_unchanged` asserts leaf
  `count == 3` and `month_counts == {"2026-01": 2, "2026-02": 1}`;
  `test_overlapping_month_buckets` asserts leaf `month_counts == {"2026-01": 1,
  "2026-02": 2}` and `count == 2`. Both match pre-fix expected leaf behavior.
- Contract: data-shape §3.5 explicitly states the equipment leaf grain "is unchanged".
- Verdict: leaf grain not regressed.

## AC-5 — Node shape unchanged

- `_build_matrix_tree` nodes carry transient `_containers` / `_month_containers`
  keys, but `_flatten` `pop()`s both and emits exactly `{label, level, count,
  month_counts, children}` (equipment node also keeps `equipment_name`) —
  verified at source.
- Direct evidence: `test_node_shape_unchanged` asserts the exact key-set at all
  three levels; `test_month_columns_and_levels_preserved` confirms `level` enum
  values and `month_columns` sort order preserved.
- `ProductionMatrix.vue` reads `count` / `month_counts` per node (CER-002
  resolved); node shape unchanged so no frontend edit. data-shape §3.5 pins the
  shape as fixed.
- Verdict: node shape not regressed.

## Regression Scope — Untouched Surfaces

| surface | status | evidence |
|---|---|---|
| Detail table (`compute_detail_page`, `_pandas_detail_page`) | untouched | functions unchanged in the diff; `test_production_history_routes.py` + detail-page tests in the 97-pass sweep all green |
| Main / count query (`main_query.sql`, `count_query.sql`, `_build_filter_where`) | untouched | matrix SQL is inline; `sql/production_history/` not edited; main/count query tests pass |
| Cross-filter cache (`compute_filter_options`) | untouched | function unchanged; `container_filter_cache` not in scope; filter-options tests pass |
| Workcenter-group mapping (`get_workcenter_group`) & sort order | unaffected | `_build_matrix_tree` still calls `get_workcenter_group` for label resolution and `wc_order`; tree sort logic byte-identical to pre-fix. Option C was chosen so canonical-group dedup happens naturally in the same node's set. |
| CSV export (`stream_export`) | untouched | function unchanged; export tests pass |

## Behavioral Output Change (Intended)

Parent (`workcenter`, `spec`) `count` and `month_counts` will now be **LOWER**
than before for any wc/spec where a LOT spans multiple children — e.g. one LOT
across 3 specs previously showed workcenter count=3, now shows 1.

- This is the **intended fix**, not a regression — the exact bug reported in
  change-request.md and the success criterion of AC-1/AC-2/AC-3.
- Consumer impact: `ProductionMatrix.vue` reads `count` / `month_counts` as
  display integers per node — lower integers render identically; no consumer
  logic branches on the magnitude or on parent==Σchildren. Node shape unchanged,
  so no frontend break.
- Disjoint-lot guard `test_distinct_containers_still_additive_when_disjoint`
  confirms the fix does not *under*-count: disjoint containers across specs still
  roll up to the true distinct total.

## Verdict

**no-regression** — leaf grain (AC-6) and node shape (AC-5) verified unchanged by
direct tests and contract; detail table, main/count query, cross-filter cache,
and workcenter-group mapping/sort are untouched in the diff and covered green by
the 97-test sweep. The lower parent counts are the intended correctness fix with
no consumer break.
