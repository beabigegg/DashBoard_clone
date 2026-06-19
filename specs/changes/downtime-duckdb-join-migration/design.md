# Design: downtime-duckdb-join-migration

## 1. Architecture Summary
A new `DowntimeJob(BaseChunkedDuckDBJob)` replaces the highest OOM risk point in the
system: `_bridge_jobid` Path B's `pd.merge(events_b, jobs_b, how='left')` — a
RESOURCEID × time-overlap N×M Cartesian pre-join with no chunk protection (ADR-0003
excludes row chunking). The job streams the two Oracle datasets — `base_events`
(keyed by `HISTORYID`) and `job_data` (keyed by `RESOURCEID`) — as Arrow batches into
ONE shared job-temp DuckDB (tables `base_raw` + `job_raw`), then runs the cross-shift
merge and the time-overlap bridge JOIN entirely inside DuckDB (`post_aggregate`),
relying on DuckDB on-disk spill instead of Python heap. Chunking is per-RESOURCEID
group (`chunk_strategy=SINGLE` per group, `requires_cross_chunk_reduction=True`):
ADR-0003 forbids row/time chunking because cross-shift merge walks fragments by
`HISTORYID` and the bridge joins by `HISTORYID = RESOURCEID`, so chunk seams must
fall on group boundaries only. A new `DOWNTIME_USE_UNIFIED_JOB` flag (default off)
gates new-vs-legacy at the route enqueue site; legacy Path B is preserved exactly
(AC-8). Spool schema, spool key, and all view endpoints are explicit non-goals and
stay row-identical.

## 2. Affected Components
| component | file path | nature of change |
|---|---|---|
| DowntimeJob (new) | `src/mes_dashboard/workers/` (new `downtime_worker.py`) | add `DowntimeJob(BaseChunkedDuckDBJob)`; two-table fan-out; bridge JOIN in `post_aggregate` |
| Bridge SQL (new) | `src/mes_dashboard/sql/downtime_analysis/` | new DuckDB time-overlap bridge SQL + cross-shift merge SQL (replaces `_bridge_jobid` Path B pandas) |
| Service | `src/mes_dashboard/services/downtime_analysis_service.py` | keep legacy `_bridge_jobid` Path B byte-for-byte (AC-8); no edit to the legacy function body |
| Job service | `src/mes_dashboard/services/downtime_query_job_service.py` | flag-selected worker_fn dispatch (legacy `execute_downtime_query_job` vs `DowntimeJob.run`) |
| Job registry | `src/mes_dashboard/services/job_registry.py` | register `downtime-unified` job type (reuse existing queue/TTL constants) |
| DuckDB cache | `src/mes_dashboard/services/downtime_analysis_duckdb_cache.py` | none — two-table schema (`base_events`/`job_data`) already proves the JOIN model; verify-only |
| Route dispatch | `src/mes_dashboard/routes/downtime_analysis_routes.py` | read flag at enqueue; ON → unified job; OFF → unchanged legacy path |
| Feature flag | `src/mes_dashboard/core/feature_flags.py` | no edit (use `resolve_bool_flag` helper) |
| Env contract | `contracts/env/env-contract.md`, `env.schema.json`, `.env.example` | register `DOWNTIME_USE_UNIFIED_JOB` default `off`, enum-pinned (owned by contract-reviewer) |
| Business rules | `contracts/business/business-rules.md` | reference BJ-01 + new bridge-JOIN rule (owned by contract-reviewer) |

## 3. Key Design Decisions

**D1 — RESOURCEID grouping model and the reduction-flag (settled)**
- `requires_cross_chunk_reduction=True`, `chunk_strategy=SINGLE` per RESOURCEID group.
- **This is the opposite call from eap-alarm (ADR-0009 used `False`), and it is
  deliberate.** BJ-01 warns that `True` "unnecessarily forces single-chunk execution
  and defeats parallelism" — that warning applies to single-dataset, row/time-chunkable
  domains. Downtime is NOT that case: the bridge is a JOIN across TWO distinct Oracle
  datasets (`base_events` HISTORYID vs `job_data` RESOURCEID) that MUST be co-resident
  to join. The `True` topology (one shared job-temp DuckDB) is the natural home for two
  raw tables joined in `post_aggregate`; the `False` multi-parquet-glob topology assumes
  a single homogeneous event stream and cannot express a two-table JOIN cleanly.
- `pre_query` decomposes by **RESOURCEID group**, not by full single-chunk. The legacy
  Path B already pre-filters jobs to resources appearing in events (`_res_norm.isin`),
  proving each machine's events bridge only to that machine's jobs — groups are
  independent. `pre_query` resolves the candidate RESOURCEID set (the DISTINCT
  `HISTORYID` list, exactly as legacy lines 1220-1235), then emits chunks; each chunk
  carries one (or a small batch of) RESOURCEID(s) plus the date window. Parallelism is
  preserved at the GROUP-KEY level (`max_parallel` concurrent Oracle fetches), satisfying
  ADR-0003's "可按 group key 分" while never splitting a HISTORYID across a seam.
- Why not `chunk_strategy=ID_LIST` for the labelling? `SINGLE` is the correct *intra-group*
  semantic: within one RESOURCEID group the data is fetched as one query (no further
  row/time sub-chunking, which ADR-0003 forbids). The fan-out is over groups; each group
  is itself a SINGLE-strategy fetch. Recorded as such to make the ADR-0003 exclusion
  legible at the class-attr level.
- `post_aggregate(job_duckdb_path)`: receives the shared job-temp DuckDB holding
  `base_raw` + `job_raw`. It (a) runs the cross-shift 60s-gap merge over `base_raw`
  grouped by `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)`, (b) runs the time-overlap
  bridge JOIN (D2) producing the winner-per-event with `match_source`/`match_ambiguous`,
  (c) `COPY TO` the unchanged spool parquet, (d) registers the spool. The whole
  reduction runs over ALL groups together so a query spanning many machines yields one
  spool — identical output to the legacy whole-dataset bridge.

**D2 — DuckDB time-overlap JOIN strategy (settled — see ADR-0010)**
- Legacy logic: each event has `(HISTORYID, event_start, event_end)`; each job has
  `(RESOURCEID, CREATEDATE, eff_end = COMPLETEDATE ?? LASTCLOCKOFFDATE)`. The join keeps
  jobs where `eff_end > event_start AND CREATEDATE < event_end` (interval overlap), then
  picks the winner by **largest overlap seconds**, tiebreak `CREATEDATE ASC, JOBID ASC`;
  `match_ambiguous=True` when runner-up overlap ≥ 80% of winner overlap.
- **Chosen: inequality RANGE JOIN + window function, NOT ASOF JOIN.** ASOF JOIN matches
  the single nearest key on ONE inequality — it cannot express the two-sided interval
  overlap predicate, the overlap-seconds ranking, or the ambiguity runner-up comparison.
  The bridge requires the full candidate set per event to compute overlap magnitude and
  the 80% runner-up test. SQL shape:
  `JOIN ON base.HISTORYID = job.RESOURCEID AND job.eff_end > base.event_start AND
  job.CREATEDATE < base.event_end`, then `overlap_s = epoch(LEAST(event_end,eff_end)
  - GREATEST(event_start,CREATEDATE))`, then
  `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY overlap_s DESC, CREATEDATE,
  JOBID)` to pick the winner and `LEAD(overlap_s)` (or rn=2 self-compare) for the
  ambiguity flag. DuckDB optimizes the inequality JOIN to a range/IEJoin and spills to
  disk — the OOM elimination is precisely that this candidate explosion never lands in
  Python.
- Path A (direct JOBID match) and the orphan case stay simple equi-joins / anti-joins on
  the same two tables; only Path B was the Cartesian risk and only Path B moves to SQL.
- This JOIN-shape choice is reversal-sensitive (ASOF vs RANGE+window is a silent-regression
  trap) → ADR-0010.

**D3 — Feature flag + legacy coexistence**
- `DOWNTIME_USE_UNIFIED_JOB` (default off) resolved via `resolve_bool_flag` at the ROUTE
  enqueue site. Route-level gating keeps service/worker pure and makes rollback one
  chokepoint (mirrors eap-alarm D4).
- Flag OFF → exact current path: `execute_downtime_query_job` → `query_downtime_dataset`
  → `_bridge_jobid` Path B `pd.merge`. Zero change (AC-8).
- Flag ON → `DowntimeJob.run`. `_bridge_jobid` Path B is NOT deleted while the flag
  exists; AC-8 zero-regression is a standing gate until the flag is retired.

**D4 — Connection lifecycle**
- Each per-RESOURCEID-group chunk task opens its own Oracle connection inside
  `OracleArrowReader.chunk_iter`; `finally: conn.close()` lives in the reader, returning
  the connection to the pool on success or exception. Two raw tables = two `build_chunk_sql`
  kinds (`base` / `job`) per group, each its own `chunk_iter` call (same pattern as
  eap-alarm's events/detail split). The shared-writer `_writer_lock` serializes
  `chunk_to_duckdb` INSERTs into the single job-temp DuckDB. On chunk failure the base
  `_fan_out_reduction` re-raises after `as_completed`; no spool is registered because
  registration runs only after `post_aggregate` returns; the job-temp DuckDB is deleted
  in the base `finally` (D7).

**D5 — Equivalence-test strategy (AC-3, follows eap-alarm D6 template)**
- Parity assertion: same parquet **schema** AND **rowcount** AND **row-set content**
  (order-insensitive set equality on the business key `(event_id, job_id, match_source)`),
  for identical query params, between flag-on (`DowntimeJob`) and flag-off (legacy
  `_bridge_jobid`). Full row-set equality is mandatory because the overlap ranking +
  80%-ambiguity logic moves from pandas to DuckDB SQL — a count-only test would miss a
  winner-selection or ambiguity regression.
- Unit tier: mock `OracleArrowReader.chunk_iter` with fixed Arrow batches containing
  (a) two jobs overlapping one event with overlap ratio crossing the 80% boundary (pins
  `match_ambiguous`), (b) a cross-shift fragment pair straddling the 60s gap, (c) a
  Path-A JOBID hit and an orphan. Integration tier: run both worker_fns against the same
  seeded Oracle/DuckDB and diff the two spool parquets directly.

**D6 — Spool schema / non-goals**
- Spool schema is UNCHANGED (non-goal). Both paths must emit the identical enriched
  column set produced by `_enrich_events_df` (the `job_*` derived columns, `wait_min`,
  `repair_min`, etc. from `_bridge_jobid` lines 513-529). No `_SCHEMA_VERSION` / bridge
  cache-key bump — a spool written by either path is readable by the other.
- Column-set caveat (per cache-spool learning "blanket UNCHANGED is a false contract"):
  the async `query_downtime_dataset_raw` path emits TWO separate spools (base 7 cols +
  jobs 16 cols, bridged in browser DuckDB-WASM) and is OUT OF SCOPE — this migration
  targets only `query_downtime_dataset`'s in-Python `_bridge_jobid` Path B. The unified
  job's single bridged spool must match the **legacy `query_downtime_dataset` spool**
  columns, not the raw two-spool path. Both column sets are documented separately.

## 4. Migration / Rollback Strategy
- Flag OFF (default): legacy `_bridge_jobid` Path B untouched; zero migration cost; both
  paths coexist through the rollout window (AC-8 standing gate).
- Flag ON: `DowntimeJob` path active. Spool key/path/schema identical → switching the
  flag mid-flight is safe; a query enqueued under one path is served from the same warm
  spool by the other.
- Rollback runbook: set `DOWNTIME_USE_UNIFIED_JOB=off`, restart RQ workers. No parquet
  cleanup, no `_SCHEMA_VERSION` bump (schema identical). Orphan `{job_id}.duckdb` files
  under `DUCKDB_JOB_DIR/downtime/` are TTL-swept; the base `finally` deletes them on every
  completion/error so steady-state leaves none.

## 5. Open Risks / Deferred Decisions
- **R1 (high): two-table fan-out in `requires_cross_chunk_reduction=True`.** The base
  `_fan_out_reduction` + default `chunk_to_duckdb` infer ONE `raw` table from the first
  batch (`CREATE TABLE raw AS ... WHERE 1=0`). DowntimeJob needs TWO tables
  (`base_raw`/`job_raw`) keyed by chunk kind. `DowntimeJob` MUST override
  `chunk_to_duckdb` to route batches to the correct table by `chunk_params['kind']`.
  Whether to extend the base to support named target tables (reusable for future
  multi-table joins) vs override in `DowntimeJob` only is **deferred to the
  implementation-planner**; recommendation: override in `DowntimeJob` (the two-table JOIN
  is downtime-specific) and flag the base extension as future work.
- **R2 (medium): DuckDB inequality-JOIN candidate fan-out.** A machine with thousands of
  jobs and thousands of events still produces a large candidate set inside DuckDB; the
  win is on-disk spill, not a smaller join. Stress test (`test_downtime_analysis_stress`)
  must exercise the worst-case single high-volume RESOURCEID to confirm DuckDB spill
  bounds peak RSS — the per-RESOURCEID grouping does not help a single hot machine.
- **R3 (medium): cross-shift merge fidelity in SQL.** Moving `_merge_cross_shift_events`
  (60s-gap time-ordered walk) into DuckDB SQL is a behavioral reimplementation; the
  parity test (D5) MUST include a fragment pair straddling the 60s boundary in both
  directions. If a faithful SQL form proves intractable, fallback is to keep cross-shift
  merge in pandas over the (already reduced) per-group base and move ONLY the bridge JOIN
  to DuckDB — flagged for the planner.
- **R4 (low): ADR-0003 reconciliation.** `base_events.sql` ORDER BY vs the BQE-03 spool
  sort key reconciliation (ADR-0003 consequence #3) still applies; verify the unified job
  preserves the spool sort key.
- No Context Expansion Request needed — all decisions settled within Allowed Paths
  (CER-001 already covers eap-alarm references).

## ADR
An ADR is warranted: the DuckDB time-overlap bridge JOIN strategy (RANGE JOIN + window
function vs ASOF JOIN) is a non-obvious, reversal-sensitive boundary decision — a later
engineer "simplifying" to ASOF JOIN would silently drop the overlap-magnitude ranking
and the 80% ambiguity flag with green schema/count tests. Also recorded: the deliberate
`requires_cross_chunk_reduction=True` call (opposite of ADR-0009) for a two-dataset JOIN.
See `docs/adr/0010-downtime-duckdb-time-overlap-join.md`.
