# Design: Overnight Error Log Fixes

## Context

Overnight run (2026-03-29 17:03 ~ 2026-03-30 07:15) surfaced 4 actionable issues. All verified directly in source code — no agent summaries used.

**Current state of each issue:**

1. **Broken import** — `_get_resource_lookup` and `_get_workcenter_mapping` were removed from `resource_dataset_cache.py` during Phase 5/6 refactoring. Two consumers (`resource_history_sql_runtime.py:534`, `resource_history_routes.py:74`) still import them. The functions' responsibilities now live in:
   - `resource_history_service._build_resource_lookup(resources)` — takes a resources list, returns `{historyid: info}` dict
   - `filter_cache.get_workcenter_mapping()` — returns `{workcentername: {group, sequence}}` dict

2. **Worker SIGSEGV** — `dispose_engine()` (database.py:497) calls `stop_keepalive()` then disposes engines. But `cache_updater` thread is not signalled — it can hold DB connections during dispose, causing `threading._shutdown` deadlock. Gunicorn kills the worker → replacement gets SIGSEGV from corrupted C extension state.

3. **Slow query noise** — `database.py:832` uses hardcoded `1.0s` threshold. `realtime_equipment_cache` runs every 5 min at ~2s → 170 false warnings/night. Separate `metrics.py` already has env-configurable `SLOW_QUERY_THRESHOLD` (default 1.0, production typically 5.0).

4. **Spool seed log level** — `anomaly_detection_scheduler.py:165` logs `single_flight_timeout` as ERROR. This is expected contention during multi-worker startup.

## Goals / Non-Goals

**Goals:**
- Restore resource history dimension data injection (fix broken import)
- Eliminate worker SIGSEGV risk during shutdown
- Reduce log noise from known-slow periodic queries
- Correct log severity for expected startup contention

**Non-Goals:**
- Refactoring resource_history's dimension data architecture (just fix the import)
- Overhauling gunicorn worker management
- Making slow query thresholds per-caller configurable (unnecessary complexity for now)
- Fixing cold-start Oracle slow queries (expected, one-time)

## Decisions

### D1: Fix broken import by re-exporting thin wrappers

**Decision:** Add two thin wrapper functions in `resource_dataset_cache.py` that delegate to the canonical sources:
- `_get_resource_lookup()` → calls `resource_history_service._get_filtered_resources()` + `_build_resource_lookup()` with no filters (returns all resources)
- `_get_workcenter_mapping()` → re-exports `filter_cache.get_workcenter_mapping()`

**Why not update all import sites instead?** The consumers (`sql_runtime`, `routes`, `e2e tests`) use these as parameter-less convenience functions. Changing them to call `_build_resource_lookup(resources)` directly would require them to also fetch the resources list, adding coupling. Thin wrappers keep the interface stable.

**Alternative considered:** Inline the calls at each import site. Rejected because 4+ call sites would each need to import from 2 different modules and orchestrate the resource fetch — more churn, same result.

### D2: Graceful shutdown — signal cache_updater before dispose

**Decision:** Add a module-level `threading.Event` (like the existing `_KEEPALIVE_STOP`) for `cache_updater`. In `dispose_engine()`, set this event and join the thread before disposing engines.

The pattern already exists: `_KEEPALIVE_STOP` + `stop_keepalive()` (database.py:490-494). We replicate this for `cache_updater`.

**Where does cache_updater live?** It's started in `cache_updater.py` with its own thread. The shutdown signal needs to be accessible from `dispose_engine()` in `database.py`, so either:
- (a) `cache_updater` exports a `stop()` function, called from `dispose_engine()`
- (b) A shared shutdown event in a neutral module

**Decision:** Option (a) — `cache_updater.stop_cache_updater()`, called from `dispose_engine()` before engine disposal. Mirrors the existing `stop_keepalive()` pattern.

### D3: Raise hardcoded slow query threshold from 1.0s to 3.0s

**Decision:** Change `database.py:832` from `if elapsed > 1.0` to `if elapsed > 3.0`. This eliminates the 170/night false alarms from `realtime_equipment_cache` (~2s) while still catching genuinely slow queries on the fast-query engine.

**Why not per-caller thresholds?** Over-engineering. The `read_sql_df` function (line 832) is the fast-query path. Anything over 3s on this path is genuinely noteworthy. The slow-query path (`read_sql_df_slow`) has its own separate logging. The `metrics.py` layer provides the env-configurable threshold for alerting.

**Why not use the existing `SLOW_QUERY_THRESHOLD` env var?** That variable controls the `metrics.py` alerting layer (which records to the metrics history table). The `database.py` warning is a separate, per-query log line. Coupling them would conflate two different purposes: operational alerting vs. debug logging.

### D4: Downgrade spool seed contention log from ERROR to WARNING

**Decision:** In `anomaly_detection_scheduler.py:164-165`, check if the exception message contains `single_flight_timeout`. If so, log at WARNING level instead of ERROR.

```python
except Exception as exc:
    if "single_flight_timeout" in str(exc):
        logger.warning("Spool seed contention for %s (expected during startup): %s", source_ns, exc)
    else:
        logger.error("Spool seed Oracle query failed for %s: %s", source_ns, exc)
    return False
```

**Why not INFO?** It's still a failed operation that returns `False`. WARNING is appropriate — it signals "this happened but was handled."

## Risks / Trade-offs

**[R1] Wrapper functions add indirection** → Acceptable. The wrappers are 2-3 lines each, clearly documented. The alternative (changing all call sites) carries more risk of introducing new bugs across multiple files.

**[R2] Raising threshold to 3.0s may hide real slow queries** → Mitigated. The `metrics.py` layer still catches and records them. The 3.0s threshold is only for the per-query log line on the fast-query engine. Production `SLOW_QUERY_THRESHOLD` env var controls the alerting boundary independently.

**[R3] cache_updater stop may delay shutdown** → Mitigated. Use `join(timeout=5)` like keep-alive does. If thread doesn't stop in 5s, proceed with dispose anyway.

**[R4] SIGSEGV root cause may not be thread shutdown alone** → Acknowledged. The SIGSEGV could be a DuckDB or cx_Oracle bug triggered by fork(). The graceful shutdown reduces the probability but may not eliminate it entirely. If it recurs after this fix, investigate preload_app and worker lifecycle.
