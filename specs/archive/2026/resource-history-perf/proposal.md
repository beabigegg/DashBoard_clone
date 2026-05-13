# Proposal — resource-history-perf

## Architecture Summary

This change improves resource-history performance by (1) extending Redis TTL from 2 h to 86 400 s for immutable historical chunks (end_date < today − 2 days), (2) adding a startup pre-warm that seeds the last N months of 31-day chunks into Redis via the existing `batch_query_engine` + `spool_warmup_scheduler` pipeline, and (3) exposing a `GET /api/resource/history/query/progress` endpoint that reads the per-query `batch:resource_history:<hash>:meta` HSET already written by `_update_progress()` in `batch_query_engine`, surfacing it as a structured JSON progress payload to the frontend polling loop.

## Affected Components

| component | file path | nature of change |
|---|---|---|
| resource_history_service.py | src/mes_dashboard/services/resource_history_service.py | add `prewarm_last_n_months()`, TTL bifurcation logic (historical vs recent) |
| spool_warmup_scheduler.py | src/mes_dashboard/core/spool_warmup_scheduler.py | add `_warmup_resource_history_job` function; register in `_WARMUP_JOBS` |
| resource_history_routes.py | src/mes_dashboard/routes/resource_history_routes.py | add `GET /api/resource/history/query/progress` endpoint |
| resource-history/App.vue | frontend/src/resource-history/App.vue | add progress polling composable, progress bar component |
| env-contract.md | contracts/env/env-contract.md | add `RESOURCE_HISTORY_HISTORICAL_TTL`, `RESOURCE_HISTORY_PREWARM_MONTHS` |
| api-contract.md + api-inventory.md | contracts/api/ | register new progress endpoint + response shape |
| data-shape-contract.md | contracts/data/data-shape-contract.md | add progress response payload shape |

## Key Decisions

### Decision 1: Pre-warm launch strategy

**Chosen: option (b) — background thread via `init_warmup_scheduler`, registering a new RQ job in `_WARMUP_JOBS`.**

`spool_warmup_scheduler.py` already implements the required pattern: `init_warmup_scheduler()` is called from `app.py` after the app factory returns, spawns a daemon thread, and uses a Redis leader lock (`try_acquire_lock`) so only one gunicorn worker enqueues jobs. The warmup work runs in an RQ worker process (not in the gunicorn request-handling process), so gunicorn worker timeout (30 s) is never at risk regardless of Oracle latency.

Implementation: add `_warmup_resource_history_job()` to `spool_warmup_scheduler.py` and append `("warmup-resource-history", _warmup_resource_history_job)` to `_WARMUP_JOBS`. The job calls `resource_history_service.prewarm_last_n_months()` which iterates `RESOURCE_HISTORY_PREWARM_MONTHS` × 31-day windows via `decompose_by_time_range`, skipping any chunk whose Redis key already exists (`skip_cached=True` in `execute_plan`) to make re-warm idempotent (AC-8). Oracle unreachability is caught in the job function's try/except and logged as a warning (AC-4); the job must never raise an unhandled exception.

Option (a) is rejected because a synchronous `create_app()` call with Oracle queries violates AC-4 and risks gunicorn boot failure. Option (c) is redundant — `init_warmup_scheduler` already provides the deferred RQ enqueue pattern.

### Decision 2: Redis memory budget

**Recommended default: `RESOURCE_HISTORY_PREWARM_MONTHS=3`.**

Measured spool sizes for a single 31-day resource_history query:
- `resource_dataset` chunk: ~182 KB (Parquet compressed)
- `resource_oee` chunk: ~58 KB (Parquet compressed)
- Per-chunk Redis payload: ~240 KB total

For 3 months (3 chunks per dataset tier, two tiers per date window):
- ~3 × 2 × 240 KB = ~1.4 MB Redis footprint for all pre-warmed resource-history chunks

The production Redis budget is 768 MB (`REDIS_MAXMEMORY=768mb` in `.env.example`); minimum deployment is 512 MB. A 1.4 MB pre-warm addition is well under 0.3% of either budget and safe at the default of 3 months.

Historical chunk TTL is set to `RESOURCE_HISTORY_HISTORICAL_TTL` (default 86 400 s). The `allkeys-lru` eviction policy means Redis can reclaim these keys under memory pressure without requiring explicit cleanup. Do not set `RESOURCE_HISTORY_PREWARM_MONTHS` above 6 without profiling the production Oracle query time — the warmup RQ job timeout is 1800 s and 6 months × 31-day chunks may approach that limit.

### Decision 3: query_id lifecycle for progress endpoint

**Reuse `batch_query_engine`'s existing HSET progress infrastructure.**

`batch_query_engine._update_progress()` already writes `batch:<prefix>:<query_hash>:meta` as a Redis HSET with fields `total`, `completed`, `failed`, `pct`, `status` on every chunk completion. `get_batch_progress(cache_prefix, query_hash)` reads it back.

**query_id generation:** At batch dispatch time in `resource_history_service`, call `compute_query_hash(params)` with the canonical query parameters (start_date, end_date, granularity, filter set). Return this hash to the client as `query_id` in the initial `POST /api/resource/history/query` response alongside the normal spool URL. The client then polls `GET /api/resource/history/query/progress?query_id=<hash>`.

**Redis key pattern:** `batch:resource_history:<query_hash>:meta` (HSET). The `cache_prefix` passed to `execute_plan` must be `"resource_history"` so the key pattern is consistent with the progress endpoint's lookup.

**Progress updates:** No changes to `batch_query_engine.py` are required. `execute_plan` already calls `_update_progress` after each chunk. `status` transitions: `running` → `completed` (all chunks succeeded) or `partial` (some failed) or `failed` (all failed).

**Progress endpoint response shape** (data-shape-contract):
```json
{ "query_id": "<hash>", "total_chunks": 3, "completed_chunks": 2,
  "percent": 66.7, "status": "running" }
```
Map `batch_query_engine` field names: `total` → `total_chunks`, `completed` → `completed_chunks`, `pct` → `percent`, `status` → `status`. Map `completed`/`partial` to `"done"` in the API response (AC-5 specifies `running | done | error`); `failed` maps to `"error"`.

**HTTP semantics:** Return 400 if `query_id` is absent. Return 404 if the Redis HSET key does not exist (expired or never created). The key TTL is inherited from `chunk_ttl` in `execute_plan` (default 900 s); historical pre-warm chunks use `RESOURCE_HISTORY_HISTORICAL_TTL` (86 400 s). The progress meta key expires with the same TTL as the last chunk written. No explicit delete-on-done is needed — TTL-based expiry is sufficient (AC-7 is enforced client-side when `status = done | error`).

**Auth:** Same LDAP decorator (`@require_login`) as all other resource-history routes.

## Rejected Alternatives

- **Synchronous pre-warm in `create_app()`**: Blocked by Oracle latency risk and gunicorn timeout (AC-4).
- **Separate UUID `query_id` generated per HTTP request**: Unnecessary — `compute_query_hash(params)` already produces a stable, deterministic key that enables cache reuse across concurrent users querying the same range.
- **Storing progress in a separate Redis key outside `batch_query_engine`**: Redundant — `get_batch_progress` already provides the required read interface; duplicating the write path would create state divergence.
- **`RESOURCE_HISTORY_PREWARM_MONTHS > 3` as default**: Oracle warmup for 6 months approaches the 1800 s RQ job timeout and would inflate Redis by ~2.8 MB with marginal UX benefit (users rarely query > 3 months on this page).

## Migration / Rollback Strategy

All changes are additive. No existing Redis key patterns are modified. Setting `WARMUP_SCHEDULER_ENABLED=false` disables pre-warm without any other side effects. Setting `RESOURCE_HISTORY_HISTORICAL_TTL=7200` reverts historical chunks to the current 2 h TTL. The progress endpoint returning 404 for unknown `query_id` is safe — the frontend must treat 404 as "query not yet started or expired" and fall back to the spinner-only UX. No database migrations are required.
