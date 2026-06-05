# Design: gunicorn-preload-workers

## Summary
Today every gunicorn worker independently runs the full startup fleet (engine/Redis pool
creation, all background threads, and four single-run Oracle prewarm tasks) because
`create_app()` is executed once per worker and `preload_app` is unset (False). With 2 workers
this duplicates every Oracle prewarm N times, and the ad-hoc cross-worker guards
(`refresh_cache(force=True)` version bypass, the `O_EXCL` DuckDB lock that never releases on
process death) either fail to dedupe or deadlock. This change introduces an explicit
**init-phase contract**: enable `preload_app = True` so `create_app()` runs once in the
gunicorn master, run all single-run data prewarm there, and add a `post_fork(server, worker)`
hook that re-initializes every fork-unsafe resource (DB engine pools, Redis pools, SQLite
handles) and starts all background threads per worker. The boundary is enforced in
`gunicorn.conf.py` + `app.py`; the broken dedupe guards become unnecessary on the master path.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| gunicorn config | `gunicorn.conf.py` | set `preload_app = True`; add `post_fork(server, worker)` hook calling per-worker reinit; keep `on_starting`/`worker_exit` |
| app factory | `src/mes_dashboard/app.py` | split startup block (~642-667): single-run prewarm stays in `create_app()` (master under preload); background-thread starts move behind a `post_fork`-invoked helper |
| DB engine pools | `src/mes_dashboard/core/database.py` | no engine-creation change; `dispose_engine()` (already exists, L497) is the post_fork primitive that drops inherited pools so workers re-create lazily |
| Redis pools | `src/mes_dashboard/core/redis_client.py` | no client change; `close_redis()` (already exists, L179) is the post_fork primitive that drops inherited `_REDIS_CLIENT`/`_REDIS_CONTROL_CLIENT` |
| SQLite stores | `core/log_store.py`, `core/login_session_store.py`, `core/metrics_history.py` | reopen handles in post_fork helper (inherited sqlite3 connections are not fork-safe) |
| resource_cache dedupe | `src/mes_dashboard/core/cache_updater.py` | `_check_resource_update` no longer needed on master path; remove `force=True` Oracle re-fetch when Redis already holds the target version (Decision 3) |
| DuckDB prewarm lock | `src/mes_dashboard/services/resource_history_duckdb_cache.py` | remove `O_EXCL` cross-worker lock from the master path; run prewarm synchronously pre-fork (Decision 4) |
| downtime/material prewarm | `services/downtime_analysis_cache.py`, `services/material_consumption_service.py` | invoked once on master; thread-launch wrappers retained but no longer multi-worker-raced |
| env contract | `contracts/env/env-contract.md` | no change (see Decision 5) |
| CI gate contract | `contracts/ci/ci-gate-contract.md` | add a multi-worker "prewarm-runs-once" / fork-safety assertion gate |

## Key Decisions

- **D1 — Init-phase contract (pre-fork once vs post-fork per-worker).** Single-run Oracle data
  loads (downtime_analysis, material_consumption, resource_history DuckDB, resource_cache
  initial load) run **once in the master pre-fork**; workers inherit the on-disk DuckDB/spool
  files and the warm Redis snapshot via copy-on-write. Everything that holds a live OS handle
  or a thread runs **post-fork per worker**: DB engine pools, Redis pools, SQLite handles, and
  the entire background-thread fleet (cache_updater, realtime_equipment, scrap_reason_exclusion,
  query_spool cleanup, anomaly scheduler, metrics_history, worker_memory_guard, keep-alive,
  sync_worker). Rationale: threads do not survive `fork()` and pooled sockets are shared/corrupt
  if inherited. Rejected alternative: keep per-worker prewarm and rely on cross-worker locks —
  rejected because that is the failing status quo (duplicate Oracle load + lock deadlock).

- **D2 — Pre-fork hook placement: `preload_app = True` + `post_fork` (Option C).** Rejected
  `on_starting`/`when_ready` (Options A/B): both run before `create_app()` is imported/loaded, so
  config and DB engine are not available and prewarm could not run there. With `preload_app =
  True`, gunicorn imports and calls `create_app()` in the master, giving prewarm a fully
  initialized app context exactly once. `post_fork` then hands each worker a clean slate.

- **D3 — resource_cache version-compare fix (as-built).** The `force=True` bypass was fixed by
  adding a population guard directly inside `refresh_cache()` (`resource_cache.py:824-833`): when
  `force=True` AND `redis_version == oracle_version` AND `_redis_data_available()` is True, the
  Oracle fetch is skipped and a debug log is emitted. This is equivalent to routing through
  `init_cache()` (original design intent) but safer: it handles the case where the periodic worker
  loop also calls `refresh_cache(force=True)` via `_check_resource_update`. Design originally
  rejected this approach; implementation chose it because it covers more call-sites with a single
  guard. The outcome (no redundant Oracle fetch when Redis is current) is identical.

- **D4 — DuckDB prewarm lock fix (as-built).** The `os.O_CREAT | os.O_EXCL` sentinel was replaced
  with `fcntl.flock(LOCK_EX | LOCK_NB)` (`resource_history_duckdb_cache.py:56-91`). The
  `fcntl.flock` approach auto-releases when the holding process dies (kernel releases it), which
  eliminates the 90s peer-wait timeout deadlock regardless of whether prewarm runs in master or
  per-worker. Design originally preferred full lock removal (Option B, "remove from master path");
  implementation used `fcntl.flock` (Option A) because: (a) the 90s peer-wait loop
  (`start_duckdb_prewarm:316-322`) is retained for compatibility with the non-`preload_app` dev
  path (`flask run`), and (b) `fcntl.flock` makes the lock safe for any future concurrent writer
  without further changes. The `_LOCK_FD: list = [None]` container holds the open fd to prevent
  GC from releasing the lock prematurely.

- **D5 — No new env var.** `preload_app = True` is a Python value in `gunicorn.conf.py`, not an
  env var, and rollback is a one-line revert (D6). A `PRELOAD_APP` toggle was considered for
  zero-edit rollback but rejected: the existing `GUNICORN_WORKERS` knob already lets ops fall
  back to `workers=1` (which makes the pre/post-fork split a no-op) without a code change, and an
  always-true flag adds a contract surface with no operational benefit. **`env-contract.md`
  requires no update.** (Note: `GUNICORN_WORKERS` is read in `gunicorn.conf.py:7` but is not
  currently documented in `env-contract.md`; documenting it is out of scope for this change.)

- **D6 — Rollback.** Revert `preload_app = True` → `False` (and the `post_fork` hook) in
  `gunicorn.conf.py`; `create_app()` then resumes per-worker startup exactly as today. No spool
  parquet schema change and no DuckDB schema change occur, so **no parquet/DuckDB cleanup** is
  required on rollback. No database migration.

## Migration / Rollback
Deploy is a config + factory-split change only; no data migration. Pre-warmed artifacts
(`tmp/resource_history.duckdb`, downtime/material spool parquet, resource_cache Redis snapshot)
are schema-compatible across this change, so a redeploy reuses existing files. Forward cutover:
ship `preload_app = True` + `post_fork`; verify in `error.log` that each prewarm logs exactly
once and that no "version changed: X -> X" / "timed out waiting for peer worker" lines appear.
Rollback: single-line revert of `preload_app` (see D6); workers self-heal because engine/Redis
pools and threads are (re)created lazily on first request regardless of fork mode.

## Open Risks
- **Master-held connections leak into workers if dispose is incomplete.** Any pool/handle the
  master opens during prewarm that is not dropped in `post_fork` becomes a shared, corrupt FD.
  Mitigation: `post_fork` must call `dispose_engine()` (all three engines) **and** `close_redis()`
  **and** reopen SQLite handles; covered by a multi-worker integration gate.
- **Orphan threads in the master.** If any background thread is accidentally started during
  master `create_app()`, it runs only in the master and never in workers (silently degraded
  sync). Mitigation: the startup-block split must keep every `start_*`/`init_*` thread launch
  strictly on the post-fork path; assert "no sync thread alive in master".
- **Master prewarm lengthens boot before first worker accepts traffic.** Single-run is faster
  overall, but the master now blocks on ~25s DuckDB + 8s material load before fork. Acceptable
  vs. today's duplicated load; if boot-time SLA is tight, prewarm can be made async-on-master in
  a follow-up without changing the fork contract.
- **SIGTERM/reload semantics.** With `preload_app`, gunicorn reloads re-run master `create_app()`;
  confirm graceful reload does not double-prewarm or leave a stale DuckDB `.tmp`.
