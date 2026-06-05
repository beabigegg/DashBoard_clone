# Change Request

## Original Request

Enable `preload_app = True` in gunicorn configuration and implement proper `post_fork` worker reinitialization to eliminate duplicate Oracle queries and cache prewarm tasks across multiple gunicorn workers.

## Business / User Goal

At startup with 2 gunicorn workers, every background prewarm task (downtime_analysis, material_consumption, resource_history, resource_cache) runs N times instead of once. This causes:
- N× Oracle load on each deployment/restart
- Duplicate parquet spool files written by competing workers
- `resource_history_duckdb_cache` file-lock deadlock where both workers time out and prewarm never completes
- `resource_cache` version-identical reload bug (version unchanged yet full 1241-row Oracle fetch fires again)

## Non-goals

- Not fixing slow query root causes (those are Oracle-side)
- Not changing any user-facing API or report behavior
- Not changing Redis cache architecture for L2 read-path caches (container_filter_cache, reason_filter_cache already work correctly)
- Not migrating to a different WSGI server

## Constraints

- Must not break Oracle connection pooling after fork (each worker must get fresh connections)
- Must not break SQLite file handles (log_store, metrics_history, login_sessions) after fork
- Must not break background threads (cache_updater, keep-alive, metrics, memory_guard, etc.) — all must restart per worker in post_fork
- Must not regress any existing user-facing functionality
- gunicorn.conf.py is the configuration entry point

## Known Context

From error.log analysis (2026-06-05 19:08 startup):
- 2 workers (PID 349752, 349753) both run all prewarm tasks
- downtime_analysis: both workers write independent parquet files (43902 rows each)
- material_consumption: both run 8s+ slow Oracle queries in parallel
- resource_history_duckdb_cache: file-lock mechanism partially implemented but deadlocks — both workers timeout
- container_filter_cache / reason_filter_cache: already correctly use Redis L2 (Worker 2 reads from Redis, no Oracle re-query)
- resource_cache: version comparison bug logs "version changed: X -> X" then still queries Oracle

## Open Questions

None — scope is well-defined.

## Requested Delivery Date / Priority

High — affects every deployment restart; Oracle double-load is measurable.
