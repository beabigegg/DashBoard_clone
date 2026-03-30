# Proposal: Overnight Error Log Fixes

**Change:** `overnight-error-log-fixes`
**Date:** 2026-03-30
**Status:** proposed

## Context

An overnight run (2026-03-29 17:03 ~ 2026-03-30 07:15) produced 2107 log lines. Analysis revealed 5 distinct issues ranging from a code bug to operational noise. This change addresses all actionable items found.

## Issues

### Issue 1 — Broken Import: `_get_resource_lookup` (Bug)

**Severity: High — functionality broken**

`resource_history_sql_runtime.py:534` and `resource_history_routes.py:74` import `_get_resource_lookup` from `resource_dataset_cache`, but this function no longer exists (likely renamed/removed during recent refactoring). This causes:

- `resource_history_sql_runtime` fails to load dimension data
- Cascading failure: `apply_view` returns `None` → spool seed ERROR for `resource_dataset`

```
17:05:48 [WARNING] cannot import name '_get_resource_lookup' from resource_dataset_cache
17:05:48 [ERROR]   apply_view returned None for query_id=06ce813a
```

Appeared 2 times then stopped (resource_history wasn't triggered again overnight).

**Fix:** Restore the export or update all import sites to the new name.

**Files:**
- `src/mes_dashboard/services/resource_dataset_cache.py` — source of truth
- `src/mes_dashboard/services/resource_history_sql_runtime.py:534` — consumer
- `src/mes_dashboard/routes/resource_history_routes.py:74` — consumer
- `tests/e2e/test_resource_history_e2e.py` — 3 `@patch` references

---

### Issue 2 — Worker Timeout + SIGSEGV (Stability)

**Severity: Medium — service auto-recovered, but SIGSEGV signals memory corruption**

```
01:57:18  CRITICAL  WORKER TIMEOUT (pid:98516)
           → threading._shutdown deadlock during DB engine dispose
01:58:12  WARNING   Worker (pid:121745) was sent SIGSEGV!
           → replacement worker also crashed (native extension issue)
01:58:13  INFO      Booting worker with pid: 121824  (third worker survived)
```

**Timeline:** Worker 98516 was doing DB engine dispose → background threads (keep-alive, cache_updater) held connections → `threading._shutdown` deadlocked → gunicorn killed it after `graceful_timeout=120s`. The replacement worker then got SIGSEGV (likely cx_Oracle or DuckDB C extension state corruption after fork).

**Fix:** Ensure `dispose_engine()` signals background threads to stop _before_ disposing the SQLAlchemy engine. Add a shutdown event that keep-alive and cache_updater threads check.

**Files:**
- `src/mes_dashboard/core/database.py` — `dispose_engine()` function
- `gunicorn.conf.py` — review `graceful_timeout` (currently 120s)

---

### Issue 3 — Slow Query False Alarms from `realtime_equipment_cache` (Noise)

**Severity: Low — pure noise, no actual problem**

170 out of 198 slow query warnings came from `realtime_equipment_cache`, which runs every 5 minutes and consistently takes 1.5–2.5s. The hardcoded threshold in `database.py` is `1.0s` (line 832).

This floods the log and buries real issues.

**Fix:** Make the slow query threshold configurable per-caller, or exempt known periodic background tasks. The simplest approach: raise the threshold in `read_sql_df` from 1.0s to 3.0s for the general path, since the `metrics.py` SLOW_QUERY_THRESHOLD (env-configurable, default 5.0s in production) already catches genuinely slow queries separately.

**Files:**
- `src/mes_dashboard/core/database.py:832` — hardcoded `1.0` threshold

---

### Issue 4 — Startup Spool Seed Race Condition (Low Priority)

**Severity: Low — self-healing, no data loss**

Two gunicorn workers boot simultaneously and both attempt spool seed. The `single_flight` lock correctly rejects the second worker:

```
17:05:00 [ERROR] yield_alert_dataset: single_flight_timeout: 查詢已有另一個 worker 正在執行
```

This is **working as designed** — the lock prevents duplicate work. However, the ERROR log level is misleading; this is an expected contention scenario during startup.

**Fix:** Downgrade the log level from ERROR to WARNING (or INFO) when the rejection reason is `single_flight_timeout` during bootstrap.

**Files:**
- `src/mes_dashboard/services/anomaly_detection_scheduler.py` (or wherever spool seed catches the timeout)

---

### Issue 5 — Cold Start Slow Queries (No Fix Needed)

**Severity: Info — expected behavior**

```
17:05:09  container_filter_cache:refresh     71.7s  (Oracle plan cache cold)
17:05:20  yield iter                         52.5s  (479K rows, first load)
```

These only appeared once at startup and are normal Oracle cold-start behavior. No action required — documenting for awareness only.

---

## Scope

| # | Issue | Action | Priority |
|---|-------|--------|----------|
| 1 | `_get_resource_lookup` ImportError | Fix broken import | **P0** |
| 2 | Worker SIGSEGV / timeout | Add graceful shutdown for background threads | **P1** |
| 3 | Slow query false alarms (170/night) | Raise threshold or per-caller config | **P2** |
| 4 | Spool seed ERROR on startup | Downgrade log level to WARNING | **P2** |
| 5 | Cold start slow queries | No fix — document only | — |

## Out of Scope

- OEE KPI work (separate change: `resource-history-oee-kpi`)
- Redis cache miss optimization (17 misses overnight — acceptable)
- Gunicorn worker count tuning
