# Design: resource-history-rq-async

## Summary
Add a threshold-gated async (RQ) execution path to `POST /api/resource-history/query`,
mirroring the shipped `hold-history-rq-async` (Phase 3-B) and `downtime-rq-async`
patterns. Long day-span queries return HTTP 202 + `{async, job_id, status_url}`; a
dedicated `resource-history-query` RQ worker process executes the existing
`resource_dataset_cache.execute_primary_query()` (Oracle → Parquet spool) outside
Gunicorn; the frontend polls job status via the shared `useAsyncJobPolling.ts`, reads
`query_id`, and calls `refreshView()`. Short-span queries, flag-off, and Redis-down
cases keep the existing synchronous 200 path byte-for-byte. The async path is safe to
add because it *wraps* the unchanged sync entry point (`execute_primary_query`) — it
does not re-implement query, chunking, or spool logic — so result parity is structural,
not coincidental.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| route async branch | `src/mes_dashboard/routes/resource_history_routes.py` | add 4 `RESOURCE_*` module constants + 202 dispatch branch in `api_resource_history_query` (before existing canonical/Oracle try-block); fall through to sync on any miss |
| new worker service | `src/mes_dashboard/services/resource_query_job_service.py` (create) | worker fn + `should_use_async` + `enqueue_*` + module-level `register_job_type("resource-history", ...)` |
| startup registration | `src/mes_dashboard/app.py` | add `import ...resource_query_job_service  # noqa: F401` beside existing job-service imports |
| rq monitor | `src/mes_dashboard/services/rq_monitor_service.py` | append `os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")` to `_QUEUE_NAMES` |
| worker process | `scripts/start_server.sh`, `supervisord.conf`, `deploy/` systemd unit | register `resource-history-query` worker in every topology |
| frontend polling | `frontend/src/resource-history/` | handle 202 → drive `useAsyncJobPolling.ts` (prefix `resource-history`) → `refreshView()` |
| contracts | `contracts/api/{api-contract,api-inventory}.md`, `contracts/env/env-contract.md`, `.env.example`, `contracts/CHANGELOG.md` | 202 response shape; 4 env vars; job-type registration |

## Key Decision 1 — BatchQueryEngine in the async worker
**Decision: the worker calls `resource_dataset_cache.execute_primary_query()` unmodified;
it does NOT re-implement chunking and does NOT select chunking mode.** Chunking is
already fully encapsulated inside `execute_primary_query`: the base spool follows
`_USE_ROW_COUNT_CHUNKING` (row-count or date-range), and OEE is *always* forced onto
date-range chunks (`resource_dataset_cache.py:427`) because OEE SQL is parameterized by
`chunk_start/chunk_end`. Cross-row, per-equipment reductions happen at **view time** in
`apply_view()` over the already-merged Parquet frame (post-`merge_chunks_to_spool`), not
per-chunk — so ROW_NUMBER seams never split an aggregation. This is the same post-merge
reduction pattern ADR-0003 prescribes; **ADR-0003's exclusion does NOT apply to
resource-history** and no ADR change is required (documented here for the record).
→ Rejected: re-classify resource-history under the ADR-0003 row-count-chunking exclusion
— rejected because the cross-row OEE reduction is already isolated from the chunked base
read by the date-range OEE carve-out + view-time aggregation.

## Key Decision 2 — Spool namespace
**Decision: reuse the existing `resource_dataset` namespace; create NO new namespace.**
The sync path already writes the served base spool under `_REDIS_NAMESPACE =
"resource_dataset"` and the frontend already downloads only
`/api/spool/resource_dataset/{query_id}.parquet` (`_RESOURCE_SPOOL_NAMESPACE`,
routes:40,66). OEE (`resource_oee`) is computed server-side in `apply_view` and is never
HTTP-served, so it needs no allowlist entry. `resource_dataset` is **already present** in
`spool_routes._ALLOWED_NAMESPACES` (spool_routes.py:23) — so the async path requires *no*
allowlist change. The "add namespace AND parametrize the `_ALLOWED_NAMESPACES` test in the
same PR" rule therefore reduces to: confirm with a regression assertion that
`resource_dataset` remains in the allowlist (no new entry). Because the worker reuses
`execute_primary_query`, the spool key (`_make_query_id`) and schema are identical to sync
→ `data-shape-contract.md` stays unchanged (parity assumption holds).

## New Worker Module — `resource_query_job_service.py`
Mirror `hold_query_job_service.py` exactly. Signatures:
- `should_use_async(params: dict) -> bool` — reads `RESOURCE_ASYNC_ENABLED` +
  `RESOURCE_ASYNC_DAY_THRESHOLD` at call time (so `monkeypatch.setattr` works); returns
  True when enabled and `(end-start).days >= threshold`.
- `enqueue_resource_history_query(params, owner)` → `enqueue_job_dynamic("resource-history", owner=owner, params=params)`.
- `execute_resource_history_query_job(*, job_id, owner, **query_params) -> None` — calls
  `ensure_rq_logging()`, emits coarse milestones 5→15→90→100 bracketing the call, runs
  `execute_primary_query(start_date, end_date, granularity, **filters)`, then
  `complete_job(_JOB_PREFIX, job_id, query_id=result["query_id"])`; on exception
  `complete_job(..., error=str(exc))` then re-raise.
- Module-level `register_job_type(JobTypeConfig(job_type="resource-history",
  queue_name=RESOURCE_WORKER_QUEUE, worker_fn=..., timeout_seconds=RESOURCE_JOB_TIMEOUT_SECONDS,
  ttl_seconds=RESOURCE_JOB_TTL_SECONDS, should_enqueue=should_use_async))`.
**Must NOT:** import `execute_primary_query` at module top (import inside the worker fn, as
hold does, to keep Oracle/DuckDB out of the import path); modify `execute_primary_query`
or add a `progress_callback`; perform any Oracle/Redis work at import time other than the
pure `register_job_type` registration.

## Owner-in-params requirement (regression guard)
`enqueue_job` forwards only `kwargs` to the RQ worker (`queue.enqueue(fn, kwargs=...)`,
async_query_job_service.py:182); `owner` is written to control-plane meta but is **not**
auto-injected into worker kwargs. The worker signature requires `owner=`. Therefore the
route MUST include `owner` inside the `params` dict passed to
`enqueue_job_dynamic` (e.g. `params = {**filters, "start_date", "end_date", "granularity",
"owner": owner}`), not only as the separate `enqueue_job_dynamic(owner=...)` kwarg. Pin
with an integration assertion that the enqueued payload kwargs contain `owner`.

## Worker Process Registration
Both startup paths must launch the worker (clone the hold-history blocks):
- `scripts/start_server.sh`: add `RQ_RESOURCE_WORKER_ENABLED` +
  `RQ_RESOURCE_WORKER_QUEUE="${RESOURCE_WORKER_QUEUE:-resource-history-query}"` and an
  `rq worker "${RQ_RESOURCE_WORKER_QUEUE}" ... -c mes_dashboard.rq_worker_preload` block.
- `supervisord.conf`: add `[program:worker-resource-history]` running
  `rq worker %(ENV_RESOURCE_WORKER_QUEUE)s --url %(ENV_REDIS_URL)s`.
- `deploy/`: clone `mes-dashboard-hold-history-worker.service` → resource unit with
  `RESOURCE_WORKER_QUEUE` / `RESOURCE_JOB_TIMEOUT_SECONDS` and new SyslogIdentifier.
- Env vars (module-level → restart required): `RESOURCE_ASYNC_ENABLED` (true),
  `RESOURCE_ASYNC_DAY_THRESHOLD` (90), `RESOURCE_WORKER_QUEUE` (`resource-history-query`),
  `RESOURCE_JOB_TIMEOUT_SECONDS` (1800).

## Migration / Rollback
No data migration; the spool schema and query_id keying are unchanged. **Soft rollback
without code change:** set `RESOURCE_ASYNC_ENABLED=false` and restart — `should_use_async`
returns False, every query takes the sync 200 path regardless of span; the route's
fall-through also covers `is_async_available()` False (Redis down). In-flight jobs already
enqueued continue until they finish or hit `RESOURCE_JOB_TIMEOUT_SECONDS`, then terminate
with a terminal `complete_job(error=...)` status; no new jobs are enqueued. **Hard
rollback:** stop the `resource-history-query` worker; the queue drains to timeout and the
route serves sync. No Parquet cleanup is required on rollback (reused namespace, normal
TTL eviction).

## Rejected Alternatives
- **Keep / re-implement BatchQueryEngine chunking in the worker** — rejected; the worker
  wrapping `execute_primary_query` inherits the existing chunk-mode selection, guarantees
  sync parity, and avoids a second divergent chunking implementation.
- **New dedicated spool namespace (e.g. `resource_async`)** — rejected; would fork the
  spool key space from sync, break parity, force an `_ALLOWED_NAMESPACES` + frontend URL
  change, and provide no benefit since the served namespace is identity-keyed by params.
- **Separate frontend polling component** — rejected; reuse `useAsyncJobPolling.ts` +
  existing async-progress UI (no duplicated polling implementation, per AC-4).
- **Per-chunk progress mirroring** — rejected for v1; use coarse 5→15→90→100 milestones
  (lowest risk, satisfies non-decreasing/first≤5/last==100 ordering), as hold-history did.

## Open Risks
- Worker DB pool sizing: start_server worker blocks pin `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`;
  resource queries fan out base+OEE in parallel threads — confirm the worker pool tolerates
  the in-worker `ThreadPoolExecutor(max_workers=2)` (stress-soak evidence required).
- `resource-history` runs `_USE_ROW_COUNT_CHUNKING` for base today; if a future change
  introduces a cross-row reduction *inside* the chunked base read (not view-time), the
  ADR-0003 analysis above must be re-run and the ADR potentially extended.
- `apply_view`/spool TTL: async jobs may complete near TTL expiry on very long ranges;
  verify `RESOURCE_JOB_TIMEOUT_SECONDS` < spool TTL so `/view` finds the spool.
