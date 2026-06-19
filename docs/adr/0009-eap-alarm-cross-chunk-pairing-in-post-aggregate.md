# ADR 0009: EAP ALARM SET/CLEAR pairing runs in post_aggregate, not per-chunk

## Status
proposed

## Context
The eap-alarm POC migration (`eap-alarm-unified-job-poc`) places `EapAlarmJob` on the
`BaseChunkedDuckDBJob` template with `chunk_strategy = TIME` and
`requires_cross_chunk_reduction = False`. Time-chunking is safe at the row level: each
`DWH.EAP_EVENT` row is independent and index-driven by `LAST_UPDATE_TIME`. However the
business output is NOT row-level — `_PAIR_SQL` joins each alarm SET to its later CLEAR
on `(EQP_ID, ALARM_ID)` and computes `DURATION_SECONDS`. A SET in one daily chunk and
its CLEAR in the next chunk are a single logical occurrence. This is the exact
failure class ADR-0003 names: a cross-row reduction that a naive per-chunk reduction
would silently split (here: producing an unpaired SET with `ALARM_END=NULL` plus a
dropped orphan CLEAR — halving paired durations with green tests).

The base class exposes two fan-out paths selected by `requires_cross_chunk_reduction`:
`True` routes every chunk through a shared job-temp DuckDB under a writer lock before a
single `post_aggregate` GROUP BY; `False` writes per-chunk parquets with no shared
writer. The naming invites the wrong inference that `False` means "no cross-row
reduction exists" — which is untrue for eap-alarm.

## Decision
eap-alarm uses `requires_cross_chunk_reduction = False`, but this selects only the
lightweight multi-parquet fan-out (no shared writer-lock DuckDB). The cross-row SET/CLEAR
pairing reduction MUST run in `post_aggregate`, which reads ALL chunk parquets together
(`read_parquet` over the job's chunk fileset) and applies `_PAIR_SQL` over the assembled
event set — exactly as the legacy single-DuckDB path did over the full result. Pairing is
NEVER performed per-chunk.

Equivalently: the `requires_cross_chunk_reduction` flag governs the WRITE topology
(shared DuckDB vs multi-parquet), not whether a cross-row reduction is logically present.
For eap-alarm the reduction is present and is deferred wholesale to post_aggregate.

Any future change that moves pairing into per-chunk processing, or that filters/drops
events at chunk boundaries before pairing, must:
1. Update this ADR to `superseded`.
2. Add a chunk-seam fixture proving a SET in chunk N pairs with a CLEAR in chunk N+1.
3. Re-confirm the AC-1 full-row-set parity test still holds.

## Consequences
- AC-2 (no duplicated / no missing rows across chunk boundaries) is satisfied only as
  long as `post_aggregate` globs the complete chunk set; a partial glob silently breaks
  pairing. This is the load-bearing invariant of the POC.
- `post_aggregate` peak memory is bounded by DuckDB on-disk spill, not by the chunk
  count — the parallelism benefit (AC-3) comes from concurrent Oracle fetch, not from
  reducing the pairing input.
- The eap-alarm `False` path is NOT a clean template for domains whose reduction is
  per-chunk-safe; later migrations must classify their reduction at design time
  (ADR-0003) rather than copy this flag value.
- Because pairing stays in `post_aggregate` and the spool schema is unchanged
  (ADR-0008), no `_SCHEMA_VERSION` bump and no parquet cleanup are needed on rollback.
