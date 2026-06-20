# Design: wip-rq-worker-chunks-cleanup

## Summary
Two independent changes ship together. **Part B** implements the missing `execute_wip_detail_job` RQ worker and registers the `"wip-detail"` job type so WIP detail queries at/above the L3 row threshold (200,000) — already routed by `wip_routes.api_detail` — actually run async instead of falling through to sync via the `(None, "Unknown job type")` stub. **Part C** deletes the deprecated, zero-caller `merge_chunks()` function from `batch_query_engine.py` (its surviving sibling `merge_chunks_to_spool()` and the shared exception classes stay). The two parts meet only at the service boundary in name (`merge_chunks*`); Part B does not call `merge_chunks` (the WIP detail path is a paged Oracle query, not a chunked-merge path), so there is no functional coupling — they are bundled purely for review economy.

The architecturally non-obvious point is the **result-delivery model**: the existing async contract returns `query_id` → spool parquet (`/api/spool/<namespace>/<query_id>.parquet`), but `wip_service.get_wip_detail()` returns a paged dict with no spool and no `query_id`. The WIP worker must therefore materialize a parquet spool under a **new `wip_dataset` namespace** so the 202→poll→fetch contract holds and AC-7 (identical row schema) is satisfiable.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| WIP detail worker (new) | `src/mes_dashboard/services/wip_query_job_service.py` (new) | new `execute_wip_detail_job`; `heavy_query_slot` wiring; module-level `register_job_type("wip-detail", ...)` |
| WIP detail service | `src/mes_dashboard/services/wip_service.py` | add spool-materializing primary-query helper (`execute_primary_query`-style) the worker calls; sync paged path unchanged |
| Route (no change expected) | `src/mes_dashboard/routes/wip_routes.py` | routing + 202 shape already present; only the misleading "not registered" comment (L367-370) is removed |
| Job-type registration site | `src/mes_dashboard/app.py` (~L893-896) | add `import …wip_query_job_service  # noqa: F401` so registration fires at app-factory time |
| Spool namespace whitelist | `src/mes_dashboard/routes/spool_routes.py` (`_ALLOWED_NAMESPACES`) | add `"wip_dataset"` |
| Dead-code removal | `src/mes_dashboard/services/batch_query_engine.py` | delete `merge_chunks()` (def + docstring import ref L22/L29); KEEP `merge_chunks_to_spool`, `MergeChunksMaxRowsExceeded`, `ChunkSchemaMismatch` |
| merge_chunks tests | `tests/test_batch_query_engine.py` | delete `merge_chunks` (non-spool) test cases incl. deprecation-warning test; spool tests untouched |
| Deploy unit (new) | `deploy/mes-dashboard-wip-worker.service` (new) | systemd unit running `rq worker $WIP_WORKER_QUEUE` |
| Env contract | `contracts/env/env-contract.md`, `env.schema.json`, `.env.example` | only `WIP_WORKER_QUEUE` / timeout/ttl tuning vars (NOT a routing flag — see D1) |
| Registry count test | `tests/test_job_registry.py` | bump registered-job-type count by 1 |

## Key Decisions

**D1 — No new routing flag.** WIP async routing today is gated solely by `is_async_available()` (Redis + live worker) + `classify_query_cost(domain="wip", row_count≥L3)` in `wip_routes.py`; there is no `WIP_USE_RQ` / `WIP_ASYNC_ENABLED` flag, and none exists in `env-contract.md`. Registering the worker is itself the activation; no new routing flag is introduced → rejected adding `WIP_DETAIL_USE_RQ`: it would duplicate the `is_async_available()` gate and create a flag-parity drift risk (CLAUDE.md §Worker Feature-Flag Env-Var Parity). Only operational tuning vars (`WIP_WORKER_QUEUE`, timeout/ttl) are added.

**D2 — Slot placement.** `heavy_query_slot(f"wip-detail:{job_id}")` wraps ONLY the Oracle phase inside the worker, between progress milestones 15 and 90, mirroring `execute_hold_history_query_job`. WIP detail is a single primary query (not a base+OEE fan-out like resource), so one slot per job; no `ThreadPoolExecutor` doubling. The slot is acquired inside the worker, never at request/enqueue time (ADR 0011) — this is the AC-4 guarantee (no Oracle connection at request time for async-routed queries).

**D3 — Canonical spool.** WIP detail has NO canonical/superset spool today (sync path returns a paged dict). This change introduces a per-query result spool (namespace `wip_dataset`, key = canonical hash of the filter set) written by the worker via `merge_chunks_to_spool`-style write or direct parquet write, then `register_spool_file`. Spool write and `complete_job(query_id=…)` stay OUTSIDE the slot (single-acquire, post-Oracle), matching the hold pattern. There is no warmup-superset reuse — document explicitly: each distinct filter set is its own spool key.

**D4 — merge_chunks blast radius (confirmed safe).** `grep` confirms the deprecated bare `merge_chunks` (NOT `merge_chunks_to_spool`) lives only in `batch_query_engine.py` (def L632; docstring-only refs L22/L29) and `tests/test_batch_query_engine.py`. Zero production callers. The change-request's "merge_chunks in WIP service" framing is inaccurate — it is not in `wip_service.py` at all. The shared exception classes `MergeChunksMaxRowsExceeded` (used by `merge_chunks_to_spool` L836/853) and `ChunkSchemaMismatch` (used at L873) must NOT be deleted.

**D5 — Type-B progress milestones.** Coarse brackets per hold pattern: `5` starting → `15` querying Oracle → `90` finalizing (spool write) → `100` complete, emitted via `update_job_progress`. The WIP primary-query helper is wrapped unmodified (no `progress_callback` injection).

**D6 — Registration site.** Module-level `register_job_type(JobTypeConfig(job_type="wip-detail", …, always_async=False))` at the bottom of `wip_query_job_service.py`, and an explicit import added to `app.py` (~L893-896) alongside `downtime/hold/resource` so it fires at app-factory time (gunicorn needs the registry for `queue_name`). The worker process resolves `worker_fn` by dotted path at execute time, so no extra worker-side import is required.

## Rejected Alternatives
- **Storing the paged dict in Redis job metadata instead of a spool** — rejected: breaks the uniform `query_id`→spool retrieval contract every other async domain uses; would force a WIP-specific frontend fetch branch and lose AC-7 schema-parity provability against a parquet artifact.
- **Splitting Part C into a separate PR** — rejected: `merge_chunks` removal is a deterministic zero-caller delete with its own tests; bundling adds no risk coupling (D4) and avoids a second full Tier-review cycle for a trivial deletion.
- **`nullcontext()` flag-guard around the slot** — N/A here: the sibling pattern (`heavy_query_slot(...) if FLAG else nullcontext()`) exists to keep a flag-off path byte-identical. Since D1 introduces no routing flag, the slot is unconditional inside the worker; flag-off identity is instead guaranteed at the route by `is_async_available()` falling through to the untouched sync path.

## Migration / Rollback
- **Flag-off-equivalent default:** until `wip_query_job_service` is imported in `app.py`, `enqueue_job_dynamic("wip-detail")` returns `(None, "Unknown job type")` and the route fail-opens to sync — the new worker is inert. Activation = the import line + deployed worker unit + Redis/workers up.
- **Rollback Part B:** remove the `app.py` import line (job type vanishes from the registry → route fail-opens to sync) and stop/disable the systemd unit. The `wip_dataset` namespace entry and worker module can remain dormant. No data migration; spools are TTL-bounded transient parquet.
- **Rollback Part C:** none needed — `merge_chunks` is zero-caller dead code; git history preserves it.

## Open Risks
- **DBA headroom:** new Oracle-bound worker adds to the `HEAVY_QUERY_MAX_CONCURRENT` budget; confirm session quota (per ADR 0011 / service-patterns checklist) before flag-equivalent promotion — owned by stress-soak-report.md.
- **Spool schema parity (AC-7):** the worker spool columns must exactly match the sync paged dict's `lots` row schema, including the summary/count fields the sync path computes separately — backend-engineer must reconcile (sync path returns summary + paged lots in one dict; spool can only carry the row set, so the route's async-result assembly must recompute or carry summary). Flagged for implementation-planner.
- **`wip_dataset` namespace + test parity:** per CLAUDE.md, add the namespace to `_ALLOWED_NAMESPACES` AND parametrize its spool-route test in the same PR.
