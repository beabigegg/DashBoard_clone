# Design: unify-duckdb-prewarm-rq

## Summary
Today, resource-history and downtime-analysis warm their DuckDB caches via daemon
threads spawned during the gunicorn master's single-run pre-fork phase
(`app.py` calls `start_duckdb_prewarm()` / `start_downtime_prewarm()`). This change
moves both prewarms onto the existing RQ warmup queue managed by
`spool_warmup_scheduler._WARMUP_JOBS`, so all heavy-query cache loads share one
observable, retryable, leader-locked mechanism. Two new RQ worker functions wrap the
existing per-service prewarm logic; the daemon-thread calls are deleted from `app.py`.
Spool freshness is realigned: per-service TTLs (`RESOURCE_HISTORY_SPOOL_TTL`,
`DOWNTIME_ANALYSIS_CACHE_TTL`, default 72000 s / 20 h) override the global
`CACHE_TTL_DATASET` without altering it, so spool metadata survives just under one day
and the next query after the daily DuckDB refresh reads fresh data instead of
rebuilding parquet every 2 h.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Warmup registry | `src/mes_dashboard/core/spool_warmup_scheduler.py` | add 2 RQ worker fns + `_WARMUP_JOBS` entries for resource-history & downtime DuckDB prewarm |
| App startup | `src/mes_dashboard/app.py:834-839` | remove `start_duckdb_prewarm()` / `start_downtime_prewarm()` single-run calls |
| Resource-history cache | `src/mes_dashboard/services/resource_history_duckdb_cache.py` | expose prewarm body as a callable RQ entry; retire daemon-thread wrapper |
| Downtime DuckDB cache | `src/mes_dashboard/services/downtime_analysis_duckdb_cache.py` | same: expose callable prewarm; retire daemon thread |
| Downtime spool cache | `src/mes_dashboard/services/downtime_analysis_cache.py:37` | `_CACHE_TTL` default → `DOWNTIME_ANALYSIS_CACHE_TTL` (72000) |
| Resource dataset cache | `src/mes_dashboard/services/resource_dataset_cache.py:37` | `_CACHE_TTL` reads `RESOURCE_HISTORY_SPOOL_TTL` (72000), no longer raw `CACHE_TTL_DATASET` |
| Env contract | `contracts/env/env-contract.md` | document 2 new TTL env vars + defaults |
| Business rules | `contracts/business/business-rules.md` | 20 h spool-freshness rule for the two services |

## Key Decisions

- **D1 — RQ job over daemon thread.** Route both prewarms through `_WARMUP_JOBS` so
  they inherit the queue's observability (RQ dashboard, job state), retry/failure-ttl,
  and the Redis leader lock that already serializes the other four datasets. Daemon
  threads are invisible to operators, cannot be retried, and each service reimplements
  its own fcntl/poll lock. *Rejected: keep daemon threads but add metrics* — still leaves
  two divergent lock implementations and no retry; does not satisfy the unification goal.

- **D2 — Wiring without breaking the existing four entries.** `_WARMUP_JOBS` is a flat
  list of `(job_id_prefix, worker_fn)` tuples; `_enqueue_warmup_jobs` iterates it. Add two
  tuples (`warmup-resource-history-duckdb`, `warmup-downtime-duckdb`) whose worker fns are
  thin wrappers that call the per-service prewarm body and log a completion line, matching
  the existing `_warmup_*_dataset_job` shape. No change to enqueue/leader-lock logic, so the
  reject/yield_alert/hold/resource_dataset entries are untouched. The
  "production-history must never appear" guard test stays green. *Rejected: a second
  DuckDB-only registry/queue* — duplicates the leader-lock and scheduler loop for no benefit.

- **D3 — Fork-safety under `preload_app=True`.** Per ADR-0004 the master loads
  `create_app()` once pre-fork; the current daemon prewarm threads are deliberately spawned
  there and rely on threads dying at `fork()`. Removing them is strictly safer: nothing
  fork-unsafe is created in the master for these two services, and `_enqueue_warmup_jobs`
  runs from `init_warmup_scheduler` in the per-worker / leader-elected path (already
  fork-safe — enqueue is a Redis write, the actual load happens in a separate RQ worker
  process). The master no longer blocks ~25 s on DuckDB load before accepting traffic.
  The real load executes in the RQ worker; the per-service fcntl lock + `loaded_at==today`
  reuse check still prevents duplicate Oracle reads if multiple workers enqueue.

- **D4 — TTL scoping without touching `CACHE_TTL_DATASET`.** Both services already derive
  a module-level `_CACHE_TTL` from `CACHE_TTL_DATASET`. Change only that derivation:
  `resource_dataset_cache._CACHE_TTL = int(os.getenv("RESOURCE_HISTORY_SPOOL_TTL", "72000"))`
  and `downtime_analysis_cache._CACHE_TTL = int(os.getenv("DOWNTIME_ANALYSIS_CACHE_TTL", "72000"))`.
  The global constant in `config/constants.py:66` (7200) and all other consumers
  (hold/reject/yield_alert) are unmodified. Because `_CACHE_TTL` is frozen at import, env
  contract pin-tests must assert the imported constant, and override tests must use
  `monkeypatch.setattr`, not `setenv`. *Rejected: bump `CACHE_TTL_DATASET` globally* —
  would silently extend hold/reject/yield_alert spool lifetimes, violating a non-goal.

## Migration / Rollback
No data migration. Parquet column schema is unchanged, so **no deploy-time parquet
cleanup is required** for either `tmp/query_spool/resource_*` or
`tmp/query_spool/downtime_*`, and DuckDB files (`tmp/resource_history.duckdb`,
`tmp/downtime_analysis.duckdb`) remain compatible. Rollback is code-only: restore the two
`start_*_prewarm()` calls in `app.py`, remove the two `_WARMUP_JOBS` entries, and revert
the two `_CACHE_TTL` derivations to `CACHE_TTL_DATASET`. The two new env vars are optional
(defaults baked in); unsetting them is harmless. First deploy requires an RQ warmup worker
to be running, or the first query for each page falls back to Oracle once (accepted) until
the next warmup cycle enqueues.

## Open Risks
- **R1 (medium):** If no RQ warmup worker is provisioned in an environment, the daily
  DuckDB refresh never runs and every page query serves from Oracle until a worker appears.
  Daemon threads previously self-started inside gunicorn; the RQ model externalizes that
  dependency. Mitigation: deployment runbook must assert a warmup worker is up; resilience
  tests cover the fallback-no-crash path.
- **R2 (low):** 20 h TTL vs a daily refresh that can drift later than 20 h after the prior
  load leaves a freshness gap where metadata has expired but the new DuckDB load has not yet
  run, forcing an Oracle rebuild. Acceptable per the accepted decisions; flagged for the
  Tier-3 nightly soak boundary check, not pre-merge.
- **R3 (low):** Leader-lock + per-service fcntl lock are now two layers; a misconfiguration
  that bypasses one could re-introduce duplicate Oracle prewarms under multi-worker. Pinned
  by the existing multi-worker integration test.
