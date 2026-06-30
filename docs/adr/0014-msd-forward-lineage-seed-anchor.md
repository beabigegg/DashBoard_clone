# ADR 0014: MSD forward lineage spool — seed anchor at detection defect-lot, denormalized at write time

## Status
proposed

## Context
MSD forward (front-detection → downstream effect) analysis fetches downstream lineage (`children_map`) to pull descendant events, but `_attribute_forward_defects` previously kept only `cid in defect_cids`, dropping rejects of any lot that split/merged/renamed downstream. Forward also wrote no lineage spool, so `get_summary(direction="forward")` returned None and ran in-memory. To make forward lineage-correct and DuckDB-backed (matching backward), descendant downstream rejects must be re-keyed back to a stable anchor, and that anchor choice plus where the re-key is materialized are hard to reverse later (they shape the spool schema, the DuckDB summary SQL, and the meaning of the amplification KPI denominator).

Two open design forks:
1. Anchor SEED_ID on the detection defect-lot (the WB lot that received NSOP/NSOL) vs the seed/wafer root.
2. Re-key descendants to SEED_ID via a query-time events→lineage JOIN vs denormalize SEED_ID onto event rows at spool-write time.

Verified facts: the detection spool holds `LOSSREASONNAME`/`REJECTQTY`/`TRACKINQTY` keyed by the detection lot; the events spool rows carry only the descendant's own CONTAINERID with no back-pointer to the seed; `children_map` (seed→descendants) is available cheaply only inside the worker during `execute_trace_events_job`.

## Decision
1. **SEED_ID = the detection defect-lot**, which is already the BFS root of `_collect_forward_tracked_cids`. This preserves per-front-reason resolution required by the reason→station cross-tab and the amplification denominator.
2. **Denormalize SEED_ID onto the events/lineage stage rows at spool-write time** (stage under the finer SEED_ID key, pre-filtered), so the DuckDB forward summary is a single-pass GROUP BY rather than a per-read lineage JOIN. This follows the established cache-spool learning that finer-key stage spools should be saved pre-filtered.
3. Lineage spool schema is minimal `(SEED_ID, DESCENDANT_ID)` including a self-edge `(seed, seed)` so the seed's own intermediate-station events are attributed.

## Consequences
- The amplification KPI (`downstream_rate ÷ detection_rate`) is a within-flagged-cohort front→downstream ratio anchored per detection lot; it is NOT a flagged-vs-clean lift and must be documented as such in business-rules.
- Adding the SEED_ID column is a parquet-schema change → `_SCHEMA_VERSION` bump + `rm` of stale `msd-events/*_lineage.parquet` in the rollback runbook.
- Reversing the anchor to a wafer root later would smear detection lots into one node and break reason→station attribution — a silent analytical regression, hence this ADR.
- Write-time denormalization means a `children_map` resolution error degrades to self-edges-only; attribution still works for un-split lots and the summary is not silently empty.
- The in-memory forward summary path is retired; `get_summary(direction="forward")` runs on DuckDB. Rollback = revert that branch to `return None` while the in-memory builder still exists (remove it only one release after the DuckDB path is proven).
