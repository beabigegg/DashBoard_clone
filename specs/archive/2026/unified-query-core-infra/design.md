---
change-id: unified-query-core-infra
schema-version: 0.1.0
last-changed: 2026-06-18
---

# Design: unified-query-core-infra

## Summary

Introduce three new `core/` infrastructure modules that establish a single
"Oracle parallel chunk → pyarrow RecordBatch → DuckDB (on-disk spill) →
canonical parquet spool" pipeline, replacing the pandas-in-memory hot path that
is the root cause of every post-hoc OOM guard in path (C). `oracle_arrow_reader.py`
streams Oracle results as Arrow batches (one pooled connection per chunk, never
into Python heap); `base_chunked_duckdb_job.py` is a template-method base class
that orchestrates fan-out, DuckDB writing, post-aggregation, spool emission and
progress; `query_cost_policy.py` centralises the SYNC-vs-ASYNC routing decision
that is currently scattered across seven `*_ASYNC_DAY_THRESHOLD` env vars. The
three-module split mirrors the three concerns (I/O boundary, orchestration,
routing policy) so each is independently testable and reusable by P1–P5 domain
migrations. A template method (not ad-hoc per-worker code) is chosen because the
chunk→DuckDB→spool sequence, writer-lock discipline, connection return, and
progress brackets are invariants that every domain must obey identically — the
only domain variance lives in the abstract hooks. No domain is migrated here;
all three modules ship with zero callers until P1 (eap_alarm POC).

## Affected Components

| component | file path(s) | nature of change |
|---|---|---|
| BaseChunkedDuckDBJob | `src/mes_dashboard/core/base_chunked_duckdb_job.py` (new) | template-method base class: `run()` orchestrates pre_query → decompose → fan-out (ThreadPoolExecutor + writer_lock) → post_aggregate → spool → cleanup; abstract hooks for domains |
| QueryCostPolicy | `src/mes_dashboard/core/query_cost_policy.py` (new) | `classify_query_cost(domain, params)` 4-layer short-circuit + per-domain `CostPolicy` records |
| OracleArrowReader | `src/mes_dashboard/core/oracle_arrow_reader.py` (new) | Oracle → `pyarrow.RecordBatch` streaming; lazy per-worker session pool; one conn per `chunk_iter()`, `finally: conn.close()` |
| Env contract | `contracts/env/env-contract.md`, `.env.example.template`, `env.schema.json` | add `DUCKDB_JOB_DIR` (pinned default); deprecate (not remove) `*_ASYNC_DAY_THRESHOLD` |
| Data-shape contract | `contracts/data/data-shape-contract.md` | document Oracle → Arrow RecordBatch → DuckDB/parquet streaming boundary + chunk row-level invariants |
| CI gate contract | `contracts/ci/ci-gate-contract.md` | confirm new `core/` modules + tests covered by `backend-tests.yml` |

## Key Decisions

- **D1 — ChunkStrategy taxonomy {TIME, ID_LIST, ROW_COUNT, SINGLE}** is fixed at
  design time per ADR-0003: row-level queries use TIME or ROW_COUNT; oversized
  Oracle IN-lists use ID_LIST; cross-row aggregation (cumsum, cross-shift merge,
  hour totals) must use neither ROW_COUNT nor TIME row-splitting and falls to
  SINGLE (whole-range) or a group-key partition. ADR-0003 permanently excludes
  the downtime domain from ROW_COUNT/TIME row-chunking; the taxonomy encodes that
  exclusion as a type rather than a runtime check. → rejected: free-form
  per-domain chunkers — reason: loses the design-time seam-safety guarantee.
- **D2 — Two reduction paths keyed by `requires_cross_chunk_reduction`.** `False`
  → each chunk writes its own parquet via multi-parquet append (pyarrow
  ParquetWriter, no shared DuckDB file, zero writer contention). `True` → all
  chunks `INSERT INTO raw` a single job-temp `.duckdb` file, serialized under a
  `threading.Lock()` writer_lock; `post_aggregate` runs GROUP BY/JOIN over `raw`
  then `COPY TO` the canonical parquet. Oracle fetch (I/O-bound) is the parallel
  stage; DuckDB INSERT (C++) is fast, so serializing the write is not a bottleneck.
- **D3 — Oracle session pool is per-worker (post-fork), created lazily.** Resolves
  OQ-2. Per ADR-0004 the app runs `preload_app = True`; any OS handle opened in the
  master pre-fork becomes a corrupt shared FD across workers. The pool is therefore
  created on first access **inside the worker** (post-fork), never at module import
  time, mirroring how `database.dispose_engine()` / `redis_client.close_redis()`
  are re-initialized in the `post_fork` hook. → rejected: global module-level pool
  (see Rejected Alternatives).
- **D4 — `DUCKDB_JOB_DIR` default = `{QUERY_SPOOL_DIR}/../duckdb_jobs` (sibling dir).**
  Resolves OQ-1. `QUERY_SPOOL_DIR` default is `tmp/query_spool`; job-temp `.duckdb`
  files are transient (deleted at job end) and must be physically separated from the
  persistent canonical parquet spool so TTL/cleanup and disk accounting never
  cross. Layout: `{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb`. → rejected:
  hard-coded `/tmp/duckdb_jobs` — reason: not Docker/host-portable (see MEMORY:
  no hardcoded abs paths), and decoupling from the spool root makes co-location
  config impossible.
- **D5 — `classify_query_cost` 4-layer short-circuit, each layer independently
  testable.** L0 spool hit → SYNC; L1 always-async domain flag (trace, eap_alarm,
  msd) → ASYNC; L2 date_span ≥ day_threshold → ASYNC; L3 lightweight `COUNT(*)`
  ≥ row_threshold (default 200k) → ASYNC. Earlier layers short-circuit later ones.
  Replaces the scattered `*_ASYNC_DAY_THRESHOLD` env vars, which are **deprecated
  (warned), not removed** in this change.
- **D6 — `OracleArrowReader` streams `pyarrow.RecordBatch`.** One connection per
  `chunk_iter()` call, returned via `finally: conn.close()` (kernel-safe even on
  mid-chunk failure). Pool `min=2, max=12–15`, sized from
  `batch_query_engine._effective_parallelism()` semantics (job-level cap 3) ×
  `HEAVY_QUERY_MAX_CONCURRENT` (3) + headroom. Data never enters a pandas frame.
- **D7 — Job-temp DuckDB lifecycle.** Created at job start under `DUCKDB_JOB_DIR`,
  deleted in a `finally` on completion **or** error (releasing connection and
  file together). Crash survivors are reaped by a TTL-based orphan cron using
  `scripts/reap_orphan_jobs.py` as reference; rollback runbook lists
  `rm {DUCKDB_JOB_DIR}/*`.

## Rejected Alternatives

- **Global module-level Oracle pool** — rejected: created at import → runs in the
  gunicorn master pre-fork under `preload_app = True`; the pooled sockets become
  corrupt shared FDs across workers (ADR-0004 negative consequence). Must be lazy
  per-worker.
- **pandas DataFrame path** — rejected: re-creates the OOM root cause; every
  existing memory guard is post-hoc (checks after `pd.concat`/`pd.merge` has
  already allocated). Arrow→DuckDB keeps data off the Python heap with on-disk spill.
- **Single shared DuckDB writer for all chunk strategies** — rejected: forces
  writer-lock serialization even on `requires_cross_chunk_reduction=False` domains
  that need no cross-chunk reduction, creating an unnecessary concurrency
  bottleneck; multi-parquet append removes the shared writer entirely for those.

## Migration / Rollback

All three modules are new files with **no callers** until P1
(`eap_alarm_unified_job_poc`); shipping them changes no existing route, service,
or frontend behavior, so rollback risk in this change is zero (delete the files).
The canonical parquet spool format is unchanged, so downstream `/view` endpoints
are unaffected. The `*_ASYNC_DAY_THRESHOLD` env vars are deprecated with runtime
warnings but remain functional; P1–P5 callers migrate to `query_cost_policy`
incrementally per the env breaking-change policy (deprecate-2-minors), and the
vars are removed only in P5. Operational rollback for job-temp files:
`rm {DUCKDB_JOB_DIR}/*` plus the TTL orphan reaper.

## Open Risks

- Oracle session quota: max pool of 12–15 per worker × N workers may exceed DBA
  session budget; must be confirmed with DBA before P1 enables real fan-out.
- Pool sizing borrows the hard ceiling of 3 from `_effective_parallelism()`; if a
  future domain needs higher per-job parallelism the max must be re-derived, not
  raised ad-hoc.
- ADR-0003 seam-safety is enforced only by D1's design-time taxonomy; a domain
  mis-classified as ROW_COUNT/TIME would silently halve aggregates — P1+ must add
  a chunk-seam fixture test per cross-row-reduction domain.
