# Current Behavior: query-path-c-elimination-cleanup

Regression anchor for the pre-change state. Verified against source on 2026-06-19
(code-map digest b25d37c8). Facts only.

## query_tool_routes (Path C — sync-blocking)

- All data endpoints (`/lot-history`, `/lot-associations`, `/equipment-period`,
  `/export-csv`, etc.) call `query_tool_service` functions **synchronously** under
  the `@map_service_errors` decorator (`map_service_errors`, lines 47-92).
- The service path runs slow Oracle queries (`read_sql_df_slow`, 300s timeout).
  When the timeout fires, the service raises `QueryTimeoutError`, which the
  decorator maps to `query_timeout_error()` (HTTP) at line 69-70.
- During the entire wait (up to ~300s) the **gunicorn worker is blocked** — this
  is the "假非同步" Path C: timeout-guarded but still occupying a worker.
- There is **no RQ enqueue path** and **no `*_ASYNC_DAY_THRESHOLD` env var** in
  query_tool_routes. There is no `QUERY_TOOL_USE_RQ` flag today.

## wip_routes (Path A — pure sync, no oversized protection)

- All endpoints (`/overview/summary`, `/overview/matrix`, `/detail/<workcenter>`,
  etc.) call `wip_service` functions synchronously. WIP has **no date range**;
  queries are real-time snapshots.
- `/detail` is paginated (`page_size` capped at 500, wip_routes line 300), but
  the **underlying Oracle scan is not bounded** — there is no rowcount pre-check
  and no RQ fallback. An oversized filter still blocks the worker on a full scan.
- `wip_service` has **no COUNT/rowcount estimation function** today.

## global_concurrency semaphore (current semantics: "protect sync path")

- `core/global_concurrency.py`: Redis sorted-set + Lua CAS limiter,
  `HEAVY_QUERY_MAX_CONCURRENT` (default 3), TTL 600s.
- `acquire_heavy_query_slot()` / `release_heavy_query_slot()`; **fail-open** when
  Redis is unavailable (returns True). Documented intent today is to cap
  concurrent *synchronous* heavy queries so they do not exhaust workers.
- Runtime mechanics (Lua, fail-open, TTL) are unchanged by this change; only the
  documented role and call placement are in scope.

## merge_chunks vs merge_chunks_to_spool

- `batch_query_engine.merge_chunks` (line 631) does `pd.concat(dfs)` — loads all
  chunks into the Python heap (OOM #2 per blueprint §1.4).
- `merge_chunks_to_spool` (line 764) streams chunks to a Parquet spool via
  pyarrow ParquetWriter (no full-heap concat).
- **All production callers already use `merge_chunks_to_spool`**: hold_dataset_cache,
  downtime_analysis_service, job_query_service, resource_dataset_cache,
  reject_dataset_cache, production_history_service, mid_section_defect_service.
- The only `merge_chunks` references are (a) the module docstring usage example in
  batch_query_engine.py (lines 22, 29) and (b) `tests/test_batch_query_engine.py`
  (6 occurrences). **Zero production callers.**

## The 4 ASYNC_DAY_THRESHOLD vars (each location)

| var | default | read in (route) | read in (service) | triggers |
|---|---|---|---|---|
| DOWNTIME_ASYNC_DAY_THRESHOLD | 30 | downtime_analysis_routes.py:73,247 | — | `day_span >= threshold` → async |
| HOLD_ASYNC_DAY_THRESHOLD | 90 | hold_history_routes.py:66,239 | hold_query_job_service.py:37,69 | `day_span >= threshold` / `should_enqueue` |
| RESOURCE_ASYNC_DAY_THRESHOLD | 90 | resource_history_routes.py:64,261 | resource_query_job_service.py:37,69 | `day_span >= threshold` / `should_enqueue` |
| REJECT_ASYNC_DAY_THRESHOLD | 10 | — | reject_query_job_service.py:38,76 | `days <= threshold` → sync; else async |

Note: hold and resource each read the same var name in **both** route and service
(two read sites per var). reject reads only in its service (inverted comparison:
`days <= threshold` stays sync). All 4 are pre-marked `Deprecated (removal P5)` in
env-contract.md and `_DEPRECATED_THRESHOLD_VARS` in query_cost_policy.py.
