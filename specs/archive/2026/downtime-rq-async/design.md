# Design: downtime-rq-async

## Summary
Phase 3-A adds an RQ async query path to `POST /api/downtime-analysis/query` without changing the existing synchronous behavior. The route gains a dual-path branch: short ranges (`days < DOWNTIME_ASYNC_DAY_THRESHOLD`, default 30) stay HTTP 200 sync; long ranges return HTTP 202 `{async, job_id, status_url}` when `DOWNTIME_ASYNC_ENABLED=true` and a worker is available. The async job runs a thin worker fn that wraps the already-shipped `query_downtime_dataset_raw()` (downtime_analysis_service), which writes two raw parquets (`downtime_analysis_base_events`, then `downtime_analysis_job_bridge`) for one whole-dataset BQE chunk and performs no reductions — browser DuckDB-WASM owns all cross-shift merges, job-bridge joins, and enrichment (ADR-0007). Dispatch reuses the Phase-2 registry (`enqueue_job_dynamic()` + `register_job_type()`). The worker emits ASYNC-05 milestones 5→15→60→90→100. The data path, spool namespaces, schema versioning, and DA-11 atomicity are unchanged from the sync flag-ON path; only the execution location (worker process vs request thread) differs, which is what makes the AC-3 parity guarantee tractable.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Downtime route | `src/mes_dashboard/routes/downtime_analysis_routes.py` (`api_downtime_query`, lines 141-211) | Add sync/async branch: compute day span, gate on flag + threshold + `is_async_available()`, enqueue via dynamic registry, return 202 or fall through to existing 200 sync |
| New job service | `src/mes_dashboard/services/downtime_query_job_service.py` (new) | Worker fn + `JobTypeConfig` registration; mirrors `production_history_job_service.py` |
| Raw query fn | `src/mes_dashboard/services/downtime_analysis_service.py` (`query_downtime_dataset_raw`, lines 783-986) | No change — wrapped, not modified (already writes base then job, ADR-0003/DA-11 compliant) |
| Job registry | `src/mes_dashboard/services/job_registry.py` | No change — consumed via `register_job_type()`/`enqueue_job_dynamic()` |
| App startup | `src/mes_dashboard/app.py` (factory) | Import `downtime_query_job_service` so `register_job_type(...)` runs at import |
| Worker entrypoint | `src/mes_dashboard/workers/` | New `--queues downtime-query` worker run target |
| Frontend dispatch | `frontend/src/downtime-analysis/App.vue` + `composables/` | Branch on 202 → drive `useAsyncJobPolling.ts` + `AsyncQueryProgress.vue`; on finish read `result.query_id` → load both spools |
| Deploy | `deploy/mes-dashboard-downtime-worker.service` (new), `gunicorn.conf.py` | New systemd unit modeled on existing `*-worker.service`; timeout from `DOWNTIME_JOB_TIMEOUT_SECONDS` |
| Env | `.env.example` | 4 new `DOWNTIME_*` vars with pinned defaults (per env-contract §Async Worker) |

## Key Decisions

- **D1 — Worker fn name/signature**: `execute_downtime_query_job(*, job_id, owner, **query_params)` in `downtime_query_job_service.py`; it calls the existing `query_downtime_dataset_raw(**query_params)` and on success calls `complete_job(prefix, job_id, query_id=result['query_id'])`. Rejected: calling `query_downtime_dataset_raw()` directly from the route worker plumbing without a dedicated service fn — that fn returns a full URL/taxonomy dict, not a job-protocol result, and has no progress reporting, so the registry contract (worker fn must own `update_job_progress`/`complete_job`) would be violated.

- **D2 — pct milestone mapping (extends ASYNC-05)**: 5=starting (job received, Oracle not yet issued), 15=querying (BQE in progress), 60=writing (`base_events` parquet), 90=finalizing (`job_bridge` write + atomic commit), 100=complete (`result.query_id` available). These match the front-loaded shape used by yield-alert/production-history (long Oracle phase, short finalize) and let `AsyncQueryProgress` show meaningful movement during the dominant query stage. Rejected: uniform 20/40/60/80/100 increments — would imply even cost across stages and stall visibly at the long querying phase.

- **D3 — Two-parquet atomicity (DA-11)**: The worker guarantees "both or neither" by reusing `query_downtime_dataset_raw()`'s existing write order — `store_downtime_base_events()` then `store_downtime_job_bridge()` — and only calling `complete_job()` after both return. The larger `base_events` is written first; if `job_bridge` fails, the spool read path raises (base hit + job miss → loud 500), which is the correct DA-11 failure, and the next query re-fetches both. Rejected: writing `job_bridge` first — leaves the smaller file orphaned and forces a redundant re-fetch of the larger file, and inverts the existing service's tested ordering.

- **D4 — Sync fallback conditions**: The route stays sync (HTTP 200, unchanged §3.12 flag-ON shape) when `DOWNTIME_ASYNC_ENABLED=false`, OR day span `< DOWNTIME_ASYNC_DAY_THRESHOLD`, OR `is_async_available()` is False (same availability gate Type-B routes use). Async (202) only when all three hold. Rejected: always-async regardless of worker availability — a down worker would hang every long query at 202 with no fallback, breaking the existing degradation guarantee (ASYNC-02/ASYNC-DA-01).

- **D5 — ADR-0003 compliance**: The worker fn does no chunking itself; it delegates to `query_downtime_dataset_raw()`, which uses `_decompose_date_range()` as a single whole-dataset BQE chunk and never sets `USE_ROW_COUNT_CHUNKING`. The worker must not introduce a `BatchQueryEngine` with row-count chunking (would split cross-shift events across seams and silently halve hours, DA-12/BQE-07). Rejected: re-implementing chunking inside the worker for memory headroom — explicitly forbidden by ADR-0003; the documented large-range fallback is HISTORYID-aligned partitioning, not row-count.

- **D6 — New service file vs extending existing**: Create `downtime_query_job_service.py` (matching `reject_query_job_service.py`, `yield_alert_job_service.py`, `production_history_job_service.py`) and `register_job_type(JobTypeConfig(job_type="downtime"...))` via import at app startup. Rejected: adding the worker fn to `downtime_analysis_service.py` — that module owns Oracle/DuckDB query logic, not RQ job-protocol concerns; co-locating them couples the request-path service to Redis/RQ and breaks the established per-feature job-service convention.

## Migration / Rollback
- **Soft rollback (zero downtime, no restart of running workers needed)**: set `DOWNTIME_ASYNC_ENABLED=false` → every query takes the unchanged sync path; no parquet cleanup (namespaces and schema are identical to the sync flag-ON path). A no-restart secondary lever is raising `DOWNTIME_ASYNC_DAY_THRESHOLD` to a very large value.
- **Hard rollback (remove worker)**: stop the `downtime-query` systemd unit; in-flight jobs time out at `DOWNTIME_JOB_TIMEOUT_SECONDS` (default 1800 s); the frontend retries on next query, which falls back to sync because `is_async_available()` returns False.
- **Parquet cleanup**: only required for a schema-breaking change — bump `_SCHEMA_VERSION` in `downtime_analysis_cache.py` (orphans old keys automatically) AND `rm` both raw spool dirs per data-shape §3.13 / ci-gates Compatibility Note. Not needed for flag-based rollback.
- **`DOWNTIME_BROWSER_DUCKDB` interaction**: the async path writes to the same `downtime_analysis_base_events` / `downtime_analysis_job_bridge` namespaces the flag-ON sync path uses; no conflict. Async is orthogonal to the browser-DuckDB flag — it only relocates execution, not output.

## Open Risks
- AC-3 parity (worker vs sync byte/row-identical parquets) depends on the worker process inheriting the same DuckDB-prewarm/Oracle-fallback environment as gunicorn; an env-var drift between the worker unit and gunicorn could silently change which acquisition path runs. The new systemd unit must export the identical `DOWNTIME_*` and DuckDB env set — a deploy/CI assertion.
- Worker availability detection (`is_async_available()` 60 s cache) means a worker that dies mid-window can still receive a 202 for up to 60 s before fallback engages; in-flight job then times out. Acceptable (frontend retries), but note for resilience tests.
- `register_job_type("downtime", ...)` is a module-level side effect; tests must use `importlib.reload()` after clearing the registry dict to re-run registration (`setattr` alone will not re-execute it).
