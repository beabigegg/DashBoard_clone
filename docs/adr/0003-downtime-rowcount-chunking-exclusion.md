# ADR 0003: Downtime Analysis Excluded from Row-Count Chunking

## Status
accepted

## Context
`downtime_analysis_service` runs two Oracle queries — `base_events.sql` (E10 status fragments from `DWH.DW_MES_RESOURCESTATUS_SHIFT`) and `job_bridge.sql` — followed by Python global reductions over the entire assembled dataset:

- `_merge_cross_shift_events` groups fragments by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)` and walks them in time order, starting a new logical event only when the gap between the prior fragment's `LASTSTATUSCHANGEDATE` and the current `OLDLASTSTATUSCHANGEDATE` exceeds 60 seconds, summing `HOURS` across the contiguous run.
- `_bridge_jobid` performs a cross-product overlap join between events and jobs (Path B: `JOB.RESOURCEID = SHIFT.HISTORYID` with temporal-overlap tiebreak).

Both are cross-row, whole-dataset operations. Row-count chunking (`ROW_NUMBER() CTE + rn BETWEEN :start AND :end`) would split a single logical event's fragments across chunk seams. Each chunk would then merge only its partial fragments, producing two half-events instead of one — silently halving reported downtime hours with no error and green tests.

## Decision
`downtime_analysis_service` is migrated onto `BatchQueryEngine.execute_plan → merge_chunks_to_spool` for path uniformity and progress tracking (BQE-07), using **whole-dataset chunking** (a single chunk spanning the entire date range) with `_merge_cross_shift_events` + `_bridge_jobid` applied as a **post-merge stage** on the assembled frame. `downtime_analysis` is **permanently excluded** from `USE_ROW_COUNT_CHUNKING`.

Any future change that enables row-count chunking for downtime must:
1. Update this ADR to `superseded`
2. Update BQE-07 in `contracts/business/business-rules.md`
3. Add a chunk-seam fixture test proving no cross-shift event is split across chunk boundaries

## Consequences
- The downtime migration (BQE-07) gains `execute_plan` progress tracking and a single spool-write path, but **not** the per-chunk row-uniformity memory benefit the six other services get.
- The downtime paged ROW_NUMBER() SQL file is **NOT** created — one fewer SQL file to maintain.
- `base_events.sql`'s current ORDER BY (`HISTORYID, OLDSTATUSNAME, OLDREASONNAME, OLDLASTSTATUSCHANGEDATE`, the merge-grouping sort) must be reconciled with the BQE-03 downtime spool sort key (`OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC`) during implementation.
- If a very large date range exceeds memory, the documented fallback is HISTORYID-aligned partitioning, which remains seam-safe because merge keys never cross a HISTORYID boundary.
