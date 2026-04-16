## Why

`try_acquire_lock()` in [src/mes_dashboard/core/redis_client.py:205-237](src/mes_dashboard/core/redis_client.py#L205) is **fail-open**: when Redis is unavailable or any exception occurs during acquisition, it logs a warning and returns `True`, letting the caller proceed *without* the lock. Nine call sites depend on this function — and every one of them protects an expensive operation:

| Call site | TTL | What duplicate execution costs |
|---|---|---|
| `cache_updater.wip_cache_update` | 120s | full `DW_MES_LOT_V` table scan |
| `realtime_equipment_cache` | 120s | full equipment status scan + Redis tree rewrite |
| `yield_alert_dataset_cache` (single-flight) | 300s | multi-minute Oracle query + parquet spool conflict |
| `anomaly_detection_scheduler` | 600s | 10+ minute batch compute |
| `cache_updater.resource_cache` | 300s | resource representation rebuild |
| `cache_updater.filter_cache` (×2) | varies | container/reason filter rebuild |
| `scrap_reason_exclusion_cache` | varies | scrap reason refresh |
| `query_spool_store.cleanup_expired_spool` | varies | filesystem scan + delete races |
| `spool_warmup_scheduler` (leader election) | 120s | redundant warmup enqueue |

Net effect: when Redis is the thing under stress (network blip, eviction backpressure, restart), every protected operation **amplifies load on Oracle and the filesystem instead of pausing**. This is the opposite of what a lock should do — it converts a Redis incident into an Oracle incident. The current behaviour is undocumented in the function's docstring and there is **zero test coverage** for the fail-open code path (`tests/test_distributed_lock.py` only exercises the happy path and skips when Redis is unavailable).

The user has explicitly decided to fix this and is the architectural decision-maker for the policy choice.

## What Changes

- **BREAKING** `try_acquire_lock()` gains a required keyword-only `fail_mode` parameter. Calling it without `fail_mode` raises `TypeError`. Three values:
  - `fail_mode="closed"` — Redis unavailable / exception → return `False`. Caller must treat the protected operation as "don't run now". Use this for **cache refresh** patterns where stale data is acceptable until next refresh tick.
  - `fail_mode="raise"` — Redis unavailable / exception → raise `LockUnavailableError` (new exception in `core/exceptions.py`, added by `query-tool-error-contract` change). Use this for **leader-election** patterns where running without exclusivity is a correctness bug.
  - `fail_mode="open"` — current behaviour: log warning and return `True`. Use this **only** for operations whose duplicate execution is genuinely cheap and idempotent. Each opt-in must be justified in code with a `# fail_mode=open: <reason>` comment.
- **NEW** `LockUnavailableError(MesServiceError)` exception class. (Defined in `core/exceptions.py`, which is created by the `query-tool-error-contract` change — this change depends on that one being landed first or co-merged.)
- **NEW** `with_distributed_lock(name, ttl_seconds, fail_mode)` context manager wrapping `try_acquire_lock` + `release_lock` with try/finally. New code uses the context manager; old `try_acquire_lock` calls migrate one at a time.
- **MODIFIED** all 9 existing call sites — each gains an explicit `fail_mode` argument based on the categorisation table in `design.md`. Default mapping:
  - WIP cache, equipment status cache, resource cache, filter caches, scrap reason cache → `closed` (skip refresh, serve stale)
  - yield-alert single-flight, anomaly detection batch → `closed` (caller surfaces "in progress, retry shortly" to user)
  - spool cleanup, spool warmup leader → `raise` (these are background daemons; raising stops the tick cleanly without doing damage)
- **NEW** telemetry: each fail-mode trigger increments a counter `mes.lock.fail_mode_triggered{name=<lock>,mode=<mode>}` exposed via the existing admin metrics endpoint. Operators can then alert on "fail-closed events spiking" as an early warning of Redis trouble.
- **NEW** unit test file `tests/test_lock_fail_modes.py` that fault-injects Redis unavailability via monkeypatch on `get_control_redis_client` and verifies each `fail_mode` value behaves correctly.
- **NEW** integration test (gated on real Redis) that kills the control-plane Redis connection mid-flight and asserts that `closed` callers skip and `raise` callers raise.

## Capabilities

### New Capabilities
- `distributed-lock-policy`: contract for `try_acquire_lock` / `with_distributed_lock` semantics, the three `fail_mode` values, the `LockUnavailableError` exception, and the per-callsite policy table.

### Modified Capabilities
*(none — `redis_client.py` is not currently governed by an OpenSpec capability)*

## Impact

- **Affected code**:
  - `src/mes_dashboard/core/redis_client.py` (`try_acquire_lock` signature, new `with_distributed_lock`)
  - `src/mes_dashboard/core/exceptions.py` (`LockUnavailableError`, depends on `query-tool-error-contract`)
  - 9 caller files (each gains `fail_mode` keyword)
  - `src/mes_dashboard/services/admin_metrics_service.py` or equivalent (new counter)
  - `tests/test_lock_fail_modes.py` (new), `tests/test_distributed_lock.py` (extend for real Redis chaos)
- **Behaviour changes**:
  - When Redis is unavailable, cache refreshes **stop refreshing** instead of running in parallel against Oracle. Stale data is served until Redis recovers.
  - Background daemons (spool cleanup, warmup leader) **abort the current tick** and retry on the next schedule.
  - User-facing impact: under Redis outage, dashboards may show data that is up to one refresh-cycle stale; query-tool single-flight may surface "查詢進行中" if a duplicate request races during outage. **Both are strictly better** than the current behaviour of "one Redis blip = Oracle thundering herd".
- **Deployment ordering**: this change must land **after** `query-tool-error-contract` (which creates `core/exceptions.py`). If the two are merged together, `core/exceptions.py` must be landed first within the merge.
- **Dependencies**: none added.
- **Observability**: new metric counter; admins should add an alert for `mes.lock.fail_mode_triggered > 0` over a 5-minute window as a Redis-trouble early warning.
