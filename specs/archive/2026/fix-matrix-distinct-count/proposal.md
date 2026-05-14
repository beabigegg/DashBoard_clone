---
change-id: fix-matrix-distinct-count
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# Proposal: fix-matrix-distinct-count

## Architecture Summary

The matrix tree's parent (`workcenter`, `spec`) `count` / `month_counts` are wrong
because `_build_matrix_tree` SUMs non-additive leaf distinct-counts up the hierarchy.
The fix re-evaluates `COUNT(DISTINCT CONTAINERNAME)` independently at each grain.
**Chosen approach: C — single raw-rows query + Python distinct-set rollup.** Both
engines (`compute_matrix_view` DuckDB, `_pandas_matrix_view` pandas) emit the same
flat row stream — one row per `(raw_wc, spec, eqp_id, eqp_name, month, CONTAINERNAME)`
distinct tuple — and `_build_matrix_tree` accumulates a Python `set()` of
`CONTAINERNAME` at each node (and each node×month), taking `len()` at the end. This
is the only approach that correctly handles the canonical-group rollup (see Key
Decisions); node output shape is unchanged.

## Affected Components

| component | file path | nature of change |
|---|---|---|
| `compute_matrix_view` | `src/mes_dashboard/services/production_history_sql_runtime.py` (~265-308) | SQL changes from `COUNT(DISTINCT …) GROUP BY (wc,spec,eqp,month)` to `SELECT DISTINCT wc,spec,eqp_id,eqp_name,month_bucket,CONTAINERNAME` — emits raw distinct tuples, no aggregation |
| `_build_matrix_tree` | same file (~311-394) | Consumes distinct-tuple rows; each node holds a `container set` per node and per node×month; `count`/`month_counts` derived via `len()` after the walk. Sort/group logic unchanged |
| `_pandas_matrix_view` | same file (~458) | Replaces `groupby(...).nunique()` with `df[[wc,spec,eqp_id,eqp_name,month_bucket,CONTAINERNAME]].drop_duplicates()` → same row contract fed to `_build_matrix_tree` |
| Data-shape contract §3.5 | `contracts/data/data-shape-contract.md` | Already updated (distinct-count grain rule) — no further edit |
| Business rule PH-05 / PH-02 | `contracts/business/business-rules.md` | Already updated (non-additivity rule) — no further edit |

## Key Decisions and Rejected Alternatives

**Decision: Option C (raw distinct-tuple rows + Python set rollup).** The deciding
factor is the **workcenter-group mapping**. `get_workcenter_group` collapses several
raw `WORKCENTERNAME` values into one canonical group (e.g. `焊接_DB`, `焊_DB_料`,
`焊_DB` → `焊接_DB`). The grouping happens *inside* `_build_matrix_tree` on raw names.
A container that passes through two raw workcenters belonging to the same group must
count **once** at the canonical group node. Therefore the workcenter grain cannot be
pre-aggregated in SQL keyed on raw `WORKCENTERNAME` — the SQL layer has no knowledge
of the canonical mapping. Any SQL-side rollup (Options A and B) would still need a
*post-SQL* dedup at the canonical-group level, defeating the point of doing the
rollup in SQL. Carrying `CONTAINERNAME` through to `_build_matrix_tree` and letting
Python sets do all four grains (eqp, spec, wc, plus each ×month) handles raw-name →
group dedup naturally: the set lives on the canonical-group node.

**Rejected — Option A (single GROUPING SETS query).** Cleanest SQL in isolation, but
emits six grain rows keyed on *raw* `WORKCENTERNAME`. The wc-grain and wc×month rows
would be per-raw-name; merging two raw names into one group still requires summing
their distinct-counts — which is the original non-additive bug, just moved one level.
GROUPING SETS only produces correct ancestor counts when the GROUP BY keys are the
exact display hierarchy; here they are not. Also forces `_build_matrix_tree` to
consume multi-grain rows with NULL grain markers — a larger contract change for the
sink function.

**Rejected — Option B (per-level queries).** Same canonical-group flaw as A for the
workcenter level (its grain key is still raw WC). Plus 3-6 round-trips and a second
divergence surface to keep the pandas fallback in sync with. No upside over C.

**Memory assessment for Option C.** The row stream is `SELECT DISTINCT` over
`(wc, spec, eqp, month, CONTAINERNAME)` — already deduplicated, so its cardinality is
bounded by *distinct lots × distinct equipment-month cells they touch*, not by raw
LOTWIPHISTORY partial-row count. For a realistic production-history query window this
is the same order of magnitude as the current aggregated row set (one extra column,
and rows fan out only when a lot genuinely spans cells — which is exactly the data we
must keep to count correctly). The Python sets hold container-name strings keyed by
node; total retained strings ≤ the distinct-tuple row count. No streaming or chunking
needed; the existing `MemoryError` re-raise guard in `compute_matrix_view` remains the
backstop.

**`_build_matrix_tree` contract.** Signature unchanged — still
`(rows: List[Dict]) -> Dict`. Input row schema changes from
`{wc, spec, eqp_id, eqp_name, month_bucket, lot_count}` to
`{wc, spec, eqp_id, eqp_name, month_bucket, container}` (lot_count replaced by the raw
container id). Internally each node carries transient `_containers: set` and
`_month_containers: dict[str, set]`; a final pass converts these to
`count = len(_containers)` and `month_counts = {m: len(s)}` and drops the transient
keys before `_flatten`. Output node shape stays exactly
`{label, level, count, month_counts, children}` (equipment node also keeps
`equipment_name`) — AC-5.

**Dual-path convergence (AC-4).** Both paths converge by feeding `_build_matrix_tree`
the *identical row contract*: a list of distinct `(wc, spec, eqp_id, eqp_name, month,
container)` dicts. DuckDB produces it via `SELECT DISTINCT`; pandas via
`drop_duplicates()` on the same six columns. All distinct-count logic — including the
canonical-group dedup — lives solely in `_build_matrix_tree`, so there is exactly one
place where counting happens and the two engines cannot drift.

## Migration / Rollback

Pure code fix in one file, three functions. No schema change, no data migration, no
spool parquet rewrite (the spool columns consumed are unchanged — `WORKCENTERNAME`,
`SPECNAME`, `EQUIPMENTID`, `EQUIPMENTNAME`, `TRACKINTIMESTAMP`, `CONTAINERNAME` all
already present per data-shape §3.4). The data-shape §3.5 and business PH-05 contract
additions are already applied and are additive (they tighten the spec of an existing
field, no removal). Rollback is a straight `git revert` of the service-file commit;
no post-deploy cleanup, no cache invalidation. The matrix endpoint has no persisted
state — the next request recomputes from spool.

## Open Items

- None. The canonical-group dedup constraint is fully absorbed by Option C; no
  follow-up needed for backend-engineer beyond implementing the set-based rollup.
