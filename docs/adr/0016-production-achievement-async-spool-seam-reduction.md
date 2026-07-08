# ADR 0016: Production-achievement async spool — seam re-aggregation in post_aggregate + browser rollup relocation

## Status
proposed

## Context
`/api/production-achievement/report` runs the whole PA-05 qualifying query
(`sql/production_achievement.sql`) synchronously on Oracle's 55s fast pool and
now times out (DPY-4024) at 30-day windows as data grows. The fix migrates it
to the established RQ background job → DuckDB parquet spool → browser DuckDB-WASM
pattern (ADR-0007 downtime precedent), relocating PA-06 (SPECNAME→workcenter_group
rollup) and PA-07 (target join + achievement_rate) from server-side Python
(`build_achievement_rows()`) to the client.

The reference `ResourceHistoryBaseJob` uses `requires_cross_chunk_reduction=False`
with whole-day TIME chunks and a **plain-concat** `post_aggregate`
(`SELECT * FROM read_parquet(glob)`), which is safe there because its GROUP BY
key `TRUNC(TXNDATE)` aligns 1:1 with the calendar-day chunk boundary — no group
spans a seam. PA is different: `OUTPUT_DATE` (PA-03/PA-04) is a *shifted*
derivation of `TRACKOUTTIMESTAMP` — the pre-07:30 (or pre-08:00 historical) tail
attributes to the previous day. A single `(output_date, shift_code, SPECNAME)`
group therefore draws from timestamps that straddle a calendar-midnight chunk
boundary. Copying resource_history's plain-concat merge would emit **duplicate
business keys** across the seam.

## Decision
Keep `requires_cross_chunk_reduction=False` (parallel per-chunk parquet writes,
no single-writer lock), but `post_aggregate` MUST re-aggregate — a final
`GROUP BY output_date, shift_code, SPECNAME` `SUM(actual_output_qty)` over the
globbed chunk parquets, NOT a plain concat. `SUM` is associative across the
seam, so partial group fragments from adjacent chunks combine to one canonical
row per SPECNAME-grain key. Chunk boundaries stay on calendar days (no attempt
to align them to the 07:30/08:00 shift-cut). PA-06/PA-07 move fully to the
browser: the server ships only the SPECNAME-grain spool plus two inline
dimension maps (spec→workcenter_group, targets). A `_PA_SPOOL_SCHEMA_VERSION`
in the canonical spool key (date-range only; filters applied client-side)
governs schema invalidation.

## Consequences
- The heavy Oracle query leaves the request path; `/report` returns 202 + job_id.
- Correctness depends on (a) `post_aggregate` re-aggregating, not concatenating —
  a plain-concat copy of the resource_history reference is a silent-corruption
  trap that a dual-tier spool-level business-key parity gate must catch; and
  (b) browser DuckDB-WASM SQL reproducing `build_achievement_rows()` row-equivalently.
- `build_achievement_rows()` is retained as the test-only golden reference for the
  parity diff even though the request path no longer calls it.
- Targets MySQL-OPS degradation (null target/achievement_rate, never 500) is
  preserved by shipping an empty/partial targets map when OPS is off.
- Reversal (returning PA-06/PA-07 compute to the server, or switching to a
  plain-concat merge) must update this ADR to `superseded` and re-justify — it
  must not happen silently by pattern-copying another worker.
