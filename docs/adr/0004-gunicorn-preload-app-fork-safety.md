# ADR 0004: Gunicorn preload_app + post_fork Init-Phase Contract for Fork Safety

## Status
accepted

## Context
Gunicorn runs with `worker_class = "gthread"` and `GUNICORN_WORKERS` ≥ 2, with
`preload_app` unset (effectively `False`). Each worker therefore imports and calls
`create_app()` independently, and the startup block in `app.py` (~lines 642-667) runs in full
inside every worker. That block mixes two fundamentally different kinds of work:

1. **Single-run Oracle data prewarm** — `start_duckdb_prewarm()` (resource-history DuckDB),
   `start_downtime_prewarm()`, `start_parts_cache_warmup()` (material_consumption), and the
   resource_cache initial load via `cache_updater._check_resource_update(force=True)`. These
   should execute once per host.
2. **Per-worker live resources** — the SQLAlchemy `QueuePool` engines
   (`database.py` `_ENGINE`/`_HEALTH_ENGINE`/`_SLOW_ENGINE`), the Redis connection pools
   (`redis_client.py` `_REDIS_CLIENT`/`_REDIS_CONTROL_CLIENT`), SQLite handles (log_store,
   login_session_store, metrics_history), and ~9 background threads. These are per-process.

Because the split was implicit, the 2026-06-05 `error.log` shows every prewarm running N times:
both workers query Oracle for downtime and run 8s+ material slow-queries in parallel; the
resource_cache `refresh_cache(force=True)` path bypasses its own `redis_version ==
oracle_version` short-circuit (`resource_cache.py:820`) and re-fetches 1241 rows even when Redis
is already warm; and the resource-history DuckDB prewarm guards concurrency with an
`os.O_CREAT | os.O_EXCL` lock (`resource_history_duckdb_cache.py:47`) that does not release when
the holding process dies, so the peer worker waits the full 90s and gives up. The ad-hoc
cross-worker dedupe primitives are individually patchable but collectively indicate a missing
architectural contract about *what runs where in the fork lifecycle*.

## Decision
Adopt an explicit **init-phase contract** enforced by `gunicorn.conf.py` and `app.py`:

- Set `preload_app = True` so gunicorn loads `create_app()` **once in the master process**
  before forking. All single-run Oracle prewarm (resource-history DuckDB, downtime, material,
  resource_cache initial load via `init_cache()`'s population-checked path) runs there exactly
  once. Workers inherit the resulting on-disk DuckDB/spool files and the warm Redis snapshot via
  copy-on-write.
- Add a `post_fork(server, worker)` hook that re-initializes every fork-unsafe resource in each
  worker: call `database.dispose_engine()` and `redis_client.close_redis()` (both already exist)
  so pools are dropped and lazily re-created per worker, reopen SQLite handles, and start the
  entire background-thread fleet. No background thread may start during master `create_app()`.
- The resource-history DuckDB cross-worker lock is **replaced with `fcntl.flock(LOCK_EX|LOCK_NB)`**
  (`resource_history_duckdb_cache.py:56-91`). `fcntl.flock` auto-releases when the holding process
  dies (kernel guarantee), eliminating the 90s peer-wait timeout regardless of path. The `O_EXCL`
  sentinel that never auto-released on process death is removed. The atomic `.tmp` → final rename
  is retained for write crash-safety.
- The `resource_cache force=True` bypass is fixed by a population guard directly inside
  `refresh_cache()` (`resource_cache.py:824-833`): when `force=True` AND versions match AND Redis
  data is populated, the Oracle fetch is skipped. This is equivalent to routing through
  `init_cache()` but covers all call-sites including the periodic worker loop.

`worker=1` deployments make the pre/post-fork split a functional no-op, which is the supported
operational fallback (no `PRELOAD_APP` env flag is introduced).

Any future change that reintroduces a **concurrent** writer to the resource-history DuckDB file
(e.g. an on-request re-warm running in multiple workers) must:
1. Update this ADR to `superseded`.
2. Use `fcntl.flock(LOCK_EX | LOCK_NB)` (auto-releases on process death), **not** `os.O_EXCL`.
3. Add a test proving a dead lock-holder does not strand the peer for the full timeout.

## Consequences
Positive:
- Each Oracle prewarm runs once per host instead of once per worker — removes duplicate
  downtime queries, parallel 8s+ material slow-queries, the redundant 1241-row resource_cache
  fetch, and the 90s DuckDB lock deadlock.
- Workers boot faster (no per-worker prewarm) and share warm artifacts via COW, lowering
  aggregate startup Oracle load and memory.
- The fork lifecycle becomes a documented contract, so future startup work has an unambiguous
  home (master pre-fork for single-run data; `post_fork` for handles/threads).

Negative:
- `preload_app = True` changes the process memory model: imports and the app object are shared
  copy-on-write, and **any** live OS handle opened in the master that is not dropped in
  `post_fork` becomes a corrupt shared FD. `post_fork` correctness (dispose engines, close
  Redis, reopen SQLite, restart threads) is now load-bearing and must be regression-gated.
- The master blocks on prewarm (~25s DuckDB + ~8s material) before the first worker accepts
  traffic; acceptable versus duplicated load, and can be made async-on-master later without
  changing the fork contract.
- Gunicorn graceful reload re-runs master `create_app()`; reload paths must not double-prewarm
  or leave a stale DuckDB `.tmp`.

## Rejected Alternatives
- **Keep per-worker startup; fix each dedupe guard in place** (flock for DuckDB, population
  check inside `refresh_cache(force=True)`, distributed locks for downtime/material). Rejected:
  treats symptoms, leaves N parallel Oracle prewarms racing on every boot, and grows more
  ad-hoc cross-worker locks instead of one contract.
- **`on_starting(server)` / `when_ready(server)` for prewarm.** Rejected: both run before
  `create_app()` is loaded, so app config and the DB engine are unavailable — prewarm cannot
  execute there.
- **`PRELOAD_APP` env toggle for zero-edit rollback.** Rejected: `GUNICORN_WORKERS=1` already
  provides a code-free fallback and rollback is a one-line `preload_app` revert; an always-true
  flag adds a contract surface with no operational benefit.
- **Full `O_EXCL` lock removal (Option B — original design D4).** Considered removing the lock
  entirely since the master is the sole prewarm writer. Rejected during implementation: the 90s
  peer-wait loop in `start_duckdb_prewarm()` is retained for compatibility with the `flask run`
  dev path (no preload_app), and `fcntl.flock` auto-release makes the lock safe for both paths
  with no dead code (any future concurrent writer path also uses `fcntl.flock`).
