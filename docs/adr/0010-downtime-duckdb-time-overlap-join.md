# ADR 0010: Downtime JOBID bridge uses a DuckDB RANGE JOIN + window function (not ASOF), under requires_cross_chunk_reduction=True

## Status
proposed

## Context
`downtime_analysis_service._bridge_jobid` Path B is the system's highest OOM risk point:
`pd.merge(events_b, jobs_b, how='left')` is a RESOURCEID × time-overlap N×M Cartesian
pre-join with no chunk protection (ADR-0003 permanently excludes row-count chunking for
downtime because cross-shift merge walks fragments by `HISTORYID` and would split a
logical event across a row seam).

The migration (`downtime-duckdb-join-migration`) moves Path B's join into DuckDB inside a
`DowntimeJob(BaseChunkedDuckDBJob)` so the candidate explosion spills to disk and never
enters Python heap. Two design choices here are non-obvious and silently reversible:

1. **JOIN shape.** Each event has `(HISTORYID, event_start, event_end)`; each job has
   `(RESOURCEID, CREATEDATE, eff_end = COMPLETEDATE ?? LASTCLOCKOFFDATE)`. The legacy
   logic keeps jobs overlapping the event interval, picks the winner by *largest overlap
   seconds* (tiebreak `CREATEDATE ASC, JOBID ASC`), and sets `match_ambiguous=True` when
   the runner-up overlap is ≥ 80% of the winner's. A naive reading invites a DuckDB ASOF
   JOIN ("find the job active at the event time").

2. **Reduction-flag topology.** The eap-alarm precedent (ADR-0009 / BJ-01) established
   `requires_cross_chunk_reduction=False` with multi-parquet glob, and BJ-01 explicitly
   warns that `True` "unnecessarily forces single-chunk execution and defeats parallelism."
   Copying that value to downtime would be the wrong inference.

## Decision
1. **Use an inequality RANGE JOIN + window function, NOT ASOF JOIN.** ASOF JOIN matches the
   single nearest key on ONE inequality; it cannot express the two-sided interval-overlap
   predicate, cannot rank candidates by overlap *magnitude*, and cannot evaluate the 80%
   runner-up ambiguity test — all of which require the full per-event candidate set. The
   bridge SQL is:
   `JOIN ON base.HISTORYID = job.RESOURCEID AND job.eff_end > base.event_start AND
   job.CREATEDATE < base.event_end`, then `overlap_s = epoch(LEAST(event_end, eff_end) -
   GREATEST(event_start, CREATEDATE))`, then
   `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY overlap_s DESC, CREATEDATE, JOBID)`
   to select the winner, with a rn=2 self-compare (or `LEAD`) feeding `match_ambiguous =
   runner_overlap >= 0.8 * winner_overlap AND winner_overlap > 0`. Only Path B moves to
   SQL; Path A (direct JOBID equi-join) and the orphan anti-join stay simple.

2. **Use `requires_cross_chunk_reduction=True` with per-RESOURCEID `SINGLE` chunking.**
   Unlike eap-alarm's single homogeneous event stream, downtime's bridge is a JOIN across
   TWO distinct Oracle datasets (`base_events` HISTORYID vs `job_data` RESOURCEID) that
   must be co-resident to join. The `True` topology (one shared job-temp DuckDB holding
   `base_raw` + `job_raw`, reduced once in `post_aggregate`) is the correct home; the
   `False` multi-parquet-glob topology cannot cleanly express a two-table JOIN. Parallelism
   is retained at the RESOURCEID-group level (independent machines fetched concurrently),
   satisfying ADR-0003's "可按 group key 分組" without splitting a HISTORYID across a seam.
   BJ-01's "defeats parallelism" warning does not apply because the fan-out is over groups,
   not collapsed to one chunk.

Any future change that switches the bridge to ASOF JOIN, drops the overlap-magnitude
ranking or the 80% ambiguity flag, or flips the reduction flag to `False`, MUST:
1. Update this ADR to `superseded`.
2. Add/keep a parity fixture with two jobs overlapping one event across the 80% boundary
   proving identical `match_source` / `match_ambiguous` vs legacy `_bridge_jobid`.
3. Re-confirm the AC-3 full-row-set parity test (flag-on ≡ flag-off) still holds.

## Consequences
- OOM elimination comes from DuckDB on-disk spill of the inequality-JOIN candidate set;
  it is NOT a smaller join. A single high-volume RESOURCEID still produces a large
  candidate set — the stress test must exercise that worst case (design R2).
- The 80% ambiguity semantics and overlap-magnitude tiebreak are now encoded in SQL window
  logic, not pandas; the parity test (row-set equality on `(event_id, job_id,
  match_source)`) is the load-bearing acceptance gate.
- The deliberate `True` flag diverges from the ADR-0009 eap-alarm precedent on purpose;
  BJ-01 remains correct — its warning targets single-dataset row/time-chunkable domains,
  not two-dataset JOINs. This ADR records the boundary so the divergence is not "fixed"
  back to `False` by pattern-matching.
- Spool schema and key are unchanged (non-goal); no `_SCHEMA_VERSION` bump and no parquet
  cleanup on rollback (flag flip + RQ restart only).
