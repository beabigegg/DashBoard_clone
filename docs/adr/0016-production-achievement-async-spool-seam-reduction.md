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

## Extension (production-achievement-overhaul)

Added by change `production-achievement-overhaul` (2026-07-14). This section extends
(does not supersede) the original decision above — the original ADR-0016 principle
("server ships a coarse-but-not-final-grain spool + inline dimension maps; ALL
business rollup happens client-side in DuckDB-WASM") is preserved and extended one
level further, not reversed.

### What changed at the spool-write layer

- The Oracle SELECT/GROUP BY grain widens from 3 dimensions (`output_date, shift_code,
  SPECNAME`) to 4 (`output_date, shift_code, SPECNAME, PACKAGE_LF`) — see
  business-rules.md PA-09, data-shape-contract.md §3.28.1. `post_aggregate`'s
  re-aggregating `GROUP BY`/`SUM` (this ADR's original Decision) is otherwise
  unchanged in shape — the same seam-safety argument applies verbatim, just
  carrying one more grouping column through.
- `_PA_SPOOL_SCHEMA_VERSION` bumps `1` → `2` (parquet schema break, self-healing
  by key-mismatch; optional `rm -f tmp/query_spool/production_achievement/*.parquet`
  fast-forward — cache-spool-patterns.md).

### What changed at the client-side rollup layer (full current join chain)

The original ADR-0016 Decision described a single client-side rollup stage:
SPECNAME-grain spool `INNER JOIN spec_workcenter_map` (PA-06) `LEFT JOIN targets_map`
(PA-07). `production-achievement-overhaul` extends this to a two-stage pipeline so a
future reader sees the FULL current chain, not just the original single stage:

1. **Stage 1 — `pa_rollup_raw`**: identical INNER JOIN to the original ADR-0016
   SPECNAME→raw-`workcenter_group` join (`spec_workcenter_map`, PA-06), except
   `PACKAGE_LF` is now carried through the `GROUP BY` instead of being dropped
   (there was nothing to carry before this change — SPECNAME-grain had no
   PACKAGE_LF dimension).
2. **Stage 2 — `pa_rollup`** (redefined in place): `pa_rollup_raw` **INNER JOIN**
   `workcenter_merge_map` (business-rules.md PA-10, D2 — explicit-inclusion/
   exclude-by-absence: a raw `workcenter_group` with no row is DROPPED, mirroring
   how an unmapped SPECNAME was already dropped by PA-06's INNER JOIN — same join
   *kind*, one hop further) **LEFT JOIN** `package_lf_map` (business-rules.md
   PA-09, D1 — sparse/fallback-to-self: `COALESCE(merged_group, raw_package_lf,
   '(未分類)')`, the opposite default from `workcenter_merge_map`, applied via
   LEFT JOIN specifically because absence must NOT drop the row).
3. **Downstream** (unchanged locus, new consumers): `computeDailyView`/
   `computeCumulativeView` (business-rules.md PA-12/PA-13) further `LEFT JOIN
   daily_plan_map` (business-rules.md PA-11) on `(workcenter_group,
   package_lf_group)` — same "missing row ⇒ null denominator, never a synthesized
   zero" principle PA-07 already established for `targets_map`.

None of PA-06/PA-07's own grouping key, formula, or null-semantics change — this
extension adds dimensions and joins beside them, it does not redefine PA-06/PA-07's
existing behavior (business-rules.md PA-06 is separately amended in this change only
to add a one-sentence forward-reference to this two-stage pipeline; PA-07's
`targets_map` join is completely untouched by this change and continues to operate
at the merged-workcenter_group grain exactly as before).

### D6 — closing-chunk fix is a fetch-completeness fix, not a rollup-locus change

The N-shift-tail closing-chunk fix (business-rules.md PA-15) widens `pre_query()`'s
TIME-chunk boundaries so the Oracle fetch phase captures rows this ADR's
`post_aggregate` re-aggregation was always ABLE to combine correctly, but that a
date-only `:chunk_end_excl` bind previously never fetched at all. This is a
correction to what data REACHES `post_aggregate`, not a change to `post_aggregate`'s
aggregation logic, its cross-chunk-seam safety argument, or the rollup LOCUS (still
100% client-side, per this ADR's original Decision). A future reader should not
confuse D6 with a rollup-relocation decision — no computation moved between server
and browser as a result of D6.

### Consequences of this extension

- The client-side DuckDB-WASM SQL surface grows from one rollup query to a
  two-stage pipeline plus two additional downstream joins (daily/cumulative view
  computation) — all still governed by this ADR's original "no server-side Python
  computes this on the request path" principle.
- `build_achievement_rows()` (server-side, test-only) remains the golden reference
  for the ORIGINAL PA-06/PA-07 grain only; it is NOT extended to cover
  PACKAGE_LF/workcenter-merge/daily-plan rollup — the dual-tier parity gate for
  this change's new joins uses a separate pure-JS `rollupAndJoin()` mirror plus a
  DuckDB (real package, not WASM) golden-reference fixture, per this change's
  test-plan.md.
- Reversal of the two-stage pipeline back to a single stage, or moving
  PACKAGE_LF/workcenter-merge rollup to the server, must update this ADR to
  `superseded` and re-justify — same reversal discipline as the original
  Decision's closing sentence.
