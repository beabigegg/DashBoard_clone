# ADR 0006: DuckDB Prewarm via RQ Warmup Queue (not master daemon threads)

## Status
accepted (shipped — `start_duckdb_prewarm()` / `start_downtime_prewarm()` removed from `app.py`; both services registered in `spool_warmup_scheduler._WARMUP_JOBS`)

## Context
ADR-0004 established that single-run Oracle prewarm (resource-history DuckDB,
downtime-analysis) runs once in the gunicorn master pre-fork phase, implemented as
daemon background threads spawned during `create_app()`. This gave a code-free
fallback and relied on threads dying at `fork()`.

In practice this left two heavy-query caches outside the unified RQ warmup
mechanism (`spool_warmup_scheduler._WARMUP_JOBS`) that already manages reject,
yield-alert, hold, and resource-dataset spools with a Redis leader lock, retry,
and RQ-dashboard observability. The daemon threads are unobservable, non-retryable,
each reimplements its own fcntl/poll lock, and block the master ~25 s before the
first worker accepts traffic. Separately, these two services' spool TTL was the
global `CACHE_TTL_DATASET` (2 h), causing parquet to be rebuilt every 2 h even
though the underlying DuckDB cache only refreshes once daily.

## Decision
Move resource-history and downtime-analysis DuckDB prewarm off master daemon
threads and onto the shared RQ warmup queue by registering two new
`_WARMUP_JOBS` entries. Delete the `start_duckdb_prewarm()` /
`start_downtime_prewarm()` calls from `app.py`'s single-run master block. The
actual Oracle load now executes in a separate RQ worker process, enqueued by the
leader-elected scheduler. Realign spool freshness to the daily refresh cadence
with per-service env-var TTLs (`RESOURCE_HISTORY_SPOOL_TTL`,
`DOWNTIME_ANALYSIS_CACHE_TTL`, default 72000 s) that override — but do not
modify — the global `CACHE_TTL_DATASET`.

This narrows ADR-0004's "all single-run prewarm runs in the master" rule: for
these two services, prewarm is now an enqueue-from-worker + execute-in-RQ-worker
flow. ADR-0004's fork contract for handles/threads is otherwise unchanged.

## Consequences
- Both DuckDB prewarms are observable, retryable, and serialized by the same
  Redis leader lock as the other four datasets.
- The master no longer blocks on a ~25 s DuckDB load before serving traffic.
- New operational dependency: an RQ warmup worker must be provisioned, or the
  daily refresh never runs and queries fall back to Oracle until one appears.
  This dependency is now external to gunicorn (previously self-contained).
- Per-service `_CACHE_TTL` is frozen at import; env pin-tests must assert the
  imported constant and override tests must use `monkeypatch.setattr`.
- Future engineers must NOT re-add daemon-thread prewarm to `app.py` for these
  services, nor bump `CACHE_TTL_DATASET` to extend their TTL (it would silently
  affect hold/reject/yield_alert). Rollback is code-only and schema-compatible
  (no parquet cleanup), so reversal is cheap but must be deliberate.
