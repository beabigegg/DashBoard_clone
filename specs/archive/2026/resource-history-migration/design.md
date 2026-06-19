# Design: resource-history-migration

## Summary
Today resource-history materializes two full Oracle result sets in the gunicorn
process: `export_csv()` issues `read_sql_df(detail_sql)` and `read_sql_df(oee_sql)`
back-to-back (two full reads), then computes the OEE ratio-of-SUMs and per-equipment
yield in a Python `iterrows` loop; `resource_dataset_cache.execute_primary_query`
runs the same base/OEE pair through the legacy `batch_query_engine`
(`decompose_by_time_range` + `execute_plan` + `merge_chunks_to_spool`) under a
`ThreadPoolExecutor(max_workers=2)`. This change migrates that execution onto the
unified `BaseChunkedDuckDBJob` (the eap-alarm/production/reject precedent), gated by
`RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`). The unified path streams Oracle
chunks into a job-temp DuckDB and writes the **same two spool files** (base facts +
OEE facts) the legacy path produces — front-end view endpoints and spool schema are
untouched. The two source domains (RESOURCESTATUS_SHIFT vs LOTWIPHISTORY+REJECT)
have different schemas, different chunk-reduction semantics, and already land in two
separate spool namespaces; that asymmetry is the crux of the topology decision below.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Unified base-facts job | `src/mes_dashboard/workers/resource_history_base_worker.py` (new) | `BaseChunkedDuckDBJob`, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=False` |
| Unified OEE-facts job | `src/mes_dashboard/workers/resource_history_oee_worker.py` (new) | `BaseChunkedDuckDBJob`, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=True` |
| Dataset cache execution | `src/mes_dashboard/services/resource_dataset_cache.py` | flag-gated swap of `execute_plan`/`merge_chunks_to_spool` for unified enqueue; remove direct full-read sync path under flag |
| CSV export | `src/mes_dashboard/services/resource_history_service.py` (`export_csv`) | two full reads + `iterrows` → read from unified spool outputs; OEE SUM done in DuckDB |
| Enqueue / dispatch | `src/mes_dashboard/services/resource_query_job_service.py`, `async_query_job_service.py` | register two job types; route flag dispatch (off→legacy, on→unified) |
| SQL chunk templates | `src/mes_dashboard/sql/resource_history/` | parametrize `base_facts.sql` / `oee_facts.sql` per-chunk date binds (existing binds reused) |
| Env / business / data contracts | `contracts/env/*`, `contracts/business/business-rules.md`, `contracts/data/data-shape-contract.md` | add flag default-pin, ASYNC-09, spool-schema-UNCHANGED assertion |

## Key Design Decision: Job Topology
**Chosen: TWO separate jobs** — a `requires_cross_chunk_reduction=False` base-facts
job and a `requires_cross_chunk_reduction=True` OEE-facts job — NOT one True job whose
`post_aggregate` emits both views.

Rationale:
- The two outputs read **disjoint Oracle source tables** with **different grain and
  schema** (base = per-`HISTORYID`/day status hours from `RESOURCESTATUS_SHIFT`; OEE =
  per-`EQUIPMENTID`/`SHIFT_DATE` trackout+NG from `LOTWIPHISTORY`⋈`LOTREJECTHISTORY`).
  A single `raw` table cannot hold both without a union/discriminator hack that would
  pollute the spool schema and break AC-6.
- They already persist to **two separate spool namespaces** (`_REDIS_NAMESPACE`,
  `_OEE_REDIS_NAMESPACE`). Two jobs map 1:1 onto the existing spool topology, so
  **spool-schema-UNCHANGED (AC-6) holds by construction** — each job's
  `post_aggregate` COPYs exactly the legacy column set to the legacy path.
- They have **different chunk-reduction requirements** (see next section). Forcing one
  class to carry both a `False` (multi-parquet append) and a `True` (job-temp DuckDB
  GROUP BY) path would require the base class's `run()` template to branch internally —
  it does not, and must not (template-method is fixed).
- The OEE job needs a **wider Oracle window** than the base job (±30-day reject window),
  so their chunk plans differ; two `pre_query` implementations keep each plan honest.

**base+OEE parallelism is preserved, and elevated.** The legacy
`ThreadPoolExecutor(max_workers=2)` ran the two engines concurrently in-process. Under
the unified path the two jobs are **enqueued as two RQ jobs** that run in worker
processes; within each job, `BaseChunkedDuckDBJob._fan_out_reduction` /
`_fan_out_append` already fan chunks out across `max_parallel` threads. So inter-query
parallelism moves from in-process threads to the worker queue, and intra-query chunk
parallelism is added on top — AC-5's "positive reference" is superseded by a strictly
stronger model, not lost. The route enqueues both and awaits both spools before
streaming CSV.

## `requires_cross_chunk_reduction` Decision
- **Base-facts job → `False`.** `base_facts.sql` is `GROUP BY HISTORYID, TRUNC(TXNDATE)`.
  Each shift row belongs to exactly one calendar day, so when `ChunkStrategy.TIME`
  splits on **whole-day boundaries** no `(HISTORYID, day)` group is ever split across a
  chunk seam (the ADR-0003 hazard). Each chunk's parquet is independently correct;
  `_fan_out_append` + multi-parquet merge yields byte-equivalent aggregates. No
  job-temp DuckDB needed.
- **OEE-facts job → `True`.** Availability and yield are **ratio-of-SUMs per equipment
  across the whole range**: `export_csv` re-groups `oee_df` by `EQUIPMENTID`
  (across all `SHIFT_DATE`) and computes `yield = ΣTRACKOUT / (ΣTRACKOUT + ΣNG)`, then
  `Availability = (ΣPRD+ΣSBY+ΣEGT)/(ΣPRD+ΣSBY+ΣEGT+ΣSDT+ΣUDT+ΣNST)`. These cross-date
  sums span chunk boundaries, and the NG side carries a ±30-day reject window whose
  matches can land in a different chunk than the producing trackout. Per-chunk
  pre-aggregation followed by naive concat would under/double-count at seams (the exact
  ADR-0003 failure mode). Therefore OEE chunks `INSERT INTO raw` in a job-temp DuckDB
  and `post_aggregate` runs the final `GROUP BY EQUIPMENTID` + ratio there, COPYing the
  per-equipment result to the OEE spool. Parity to legacy single-pass is asserted
  ≤1e-6 (AC-3): identical SUM operands, identical division, done in DuckDB instead of
  pandas.

Because topology is two jobs, **no single `post_aggregate` produces both views** — each
job owns one spool. The CSV stitch (base hours × per-equipment yield → `oee_pct`) stays
a thin post-spool join, now expressible as a DuckDB SQL join over the two parquet spools
instead of the `iterrows` loop (AC-4), with no in-memory full materialization (AC-2).

## Chunk Strategy
- **`ChunkStrategy.TIME` is correct** for both jobs: both queries are date-bounded
  (`TXNDATE`/`TRACKOUTTIMESTAMP` BETWEEN binds) and `decompose_by_time_range` is already
  the production decomposition for resource-history. Whole-day chunk boundaries are the
  seam-safety guarantee for the base job.
- **`RESOURCEID`/`EQUIPMENTID` is NOT the chunk key.** Unlike downtime (ADR-0003) and
  hold future-hold, the cross-row reduction here is a plain ratio-of-SUMs with no
  time-ordered walk or cross-shift event merge — time chunking is safe *as long as the
  reduction is deferred to `post_aggregate`* (which the `True` flag guarantees). Group-key
  partitioning would only be needed if a single equipment's data exceeded worker memory,
  which DuckDB on-disk spill already covers; it remains the documented fallback, not the
  default.

## Migration / Rollback Strategy
Ship behind `RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`, restart-required). With
the flag off the legacy `batch_query_engine` path and `export_csv` full-read path are
untouched and all existing tests pass (AC-1). With the flag on, the route enqueues the
two unified jobs and the sync-fallback pandas SELECT is removed from the unified path;
when no worker is available the request returns **503** (AC-7), matching the prior P2
async pattern. Rollback is flipping the flag back to `off` — no schema change, no data
migration, spool format unchanged so any spool written by either path is readable by the
other. Per cache-spool patterns, no parquet `_SCHEMA_VERSION` bump is needed because the
spool columns are identical to legacy; the rollback runbook need not purge spool.

## Open Risks
- OEE ±30-day reject window: each OEE chunk's `build_chunk_sql` must extend its reject
  sub-window by ±30d around the chunk's production dates, or boundary NG is lost. This is
  the single highest-risk correctness item — data-boundary test must assert seam parity.
- `_APPROVED_CALLERS` in `test_query_cost_policy.py` must list both new job callers, or
  the cost-policy gate fails (AC-8).
- Two RQ jobs per export doubles queue traffic; acceptable while flag-gated, but revisit
  the deferred stress/soak budget before enabling the flag in production.
