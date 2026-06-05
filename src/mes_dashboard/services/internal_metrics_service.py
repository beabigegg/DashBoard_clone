# -*- coding: utf-8 -*-
"""Internal metrics service for the soak-workload observability probe.

Produces a single JSON-serializable snapshot containing seven metric
categories.  Consumed exclusively by the `/internal/metrics` route under
the three-layer gate defined in openspec harden-real-infra-test-coverage
spec 3.1.  Never reachable from a production deploy.

Each collector is independently wrapped in ``try/except`` — one broken
collector MUST NOT take the whole snapshot down, because this endpoint
drives soak assertions and is the primary leak-detection probe.  On
collector failure the category returns ``{"error": "<str>"}`` so the
caller sees the shape without the field silently disappearing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("mes_dashboard.internal_metrics_service")


# ---------------------------------------------------------------------------
# 1) DB pool
# ---------------------------------------------------------------------------

def _collect_pool() -> Dict[str, Any]:
    """SQLAlchemy pool checkout/checkin/size/overflow counts.

    Uses the existing ``get_pool_status()`` helper as source of truth so
    the numbers match what /health/deep reports and the soak assertions
    can rely on a consistent vocabulary.
    """
    try:
        from mes_dashboard.core.database import get_pool_status
        status = get_pool_status()
    except Exception as exc:  # engine not built yet / testing mode
        return {"error": f"pool_unavailable: {exc}"}

    # engine_id: identity of the SQLAlchemy engine object in this worker.
    # Used by GunicornHarness-based fork-safety tests (AC-2) to assert that
    # each forked worker holds a distinct engine pool after post_fork dispose.
    try:
        from mes_dashboard.core import database as _db_module
        engine_id = id(getattr(_db_module, "_ENGINE", None))
    except Exception:
        engine_id = None

    return {
        # Explicit checkout / checkin naming matches the soak scenario
        # "pool.checkout - pool.checkin" assertion vocabulary.
        "checkout": int(status.get("checked_out", 0)),
        "checkin": int(status.get("checked_in", 0)),
        "size": int(status.get("size", 0)),
        "overflow": int(status.get("overflow", 0)),
        "max_capacity": int(status.get("max_capacity", 0)),
        "saturation": float(status.get("saturation", 0.0)),
        "slow_query_active": int(status.get("slow_query_active", 0)),
        "slow_query_waiting": int(status.get("slow_query_waiting", 0)),
        "engine_id": engine_id,
    }


# ---------------------------------------------------------------------------
# 2) DuckDB temp-file footprint
# ---------------------------------------------------------------------------

def _collect_duckdb() -> Dict[str, Any]:
    """Scan DuckDB spill directory for total byte count + file count.

    DuckDB writes spill files into ``DUCKDB_TEMP_DIR`` when the
    in-memory connection exceeds ``DUCKDB_MEMORY_LIMIT``.  When
    ``DUCKDB_TEMP_DIR`` is empty DuckDB falls back to the OS temp dir
    and we can't scope the scan without collecting unrelated files —
    in that case we report ``{enabled: False}`` rather than scanning
    an unbounded tree.
    """
    try:
        from mes_dashboard.core.duckdb_runtime import DUCKDB_TEMP_DIR
    except Exception as exc:
        return {"error": f"duckdb_import_failed: {exc}"}

    if not DUCKDB_TEMP_DIR:
        return {"enabled": False, "temp_bytes": 0, "file_count": 0}

    temp_dir = Path(DUCKDB_TEMP_DIR)
    if not temp_dir.exists():
        return {"enabled": True, "temp_bytes": 0, "file_count": 0, "temp_dir": str(temp_dir)}

    total_bytes = 0
    file_count = 0
    try:
        for root, _dirs, files in os.walk(temp_dir):
            for name in files:
                try:
                    total_bytes += os.stat(os.path.join(root, name)).st_size
                    file_count += 1
                except OSError:
                    # File can disappear mid-scan under DuckDB churn;
                    # skip rather than fail the snapshot.
                    continue
    except OSError as exc:
        return {"error": f"duckdb_scan_failed: {exc}"}

    return {
        "enabled": True,
        "temp_bytes": int(total_bytes),
        "file_count": int(file_count),
        "temp_dir": str(temp_dir),
    }


# ---------------------------------------------------------------------------
# 3) Redis key counts by namespace prefix
# ---------------------------------------------------------------------------

_REDIS_NAMESPACE_PREFIXES = (
    "data",
    "route_cache",
    "equipment_status",
    "reject_dataset",
    "hold_dataset",
    "yield_alert_dataset",
    "meta",
    "lock",
    "scrap_exclusion",
)


def _collect_redis() -> Dict[str, Any]:
    """Per-namespace Redis key counts via SCAN.

    Mirrors the scan pattern in admin_routes._collect_redis_namespace_memory
    so operators see the same vocabulary in soak traces and admin dash.
    """
    try:
        from mes_dashboard.core.redis_client import (
            get_redis_client,
            REDIS_ENABLED,
            REDIS_KEY_PREFIX,
        )
    except Exception as exc:
        return {"error": f"redis_import_failed: {exc}"}

    if not REDIS_ENABLED:
        return {"enabled": False, "key_count": 0, "by_namespace": {}}

    client = get_redis_client()
    if client is None:
        return {"enabled": True, "error": "redis_client_unavailable"}

    # pool_id: identity of the Redis connection pool object in this worker.
    # Used by GunicornHarness-based fork-safety tests (AC-3) to assert that
    # each forked worker holds a distinct Redis pool after post_fork close_redis.
    try:
        pool_id = id(client.connection_pool)
    except Exception:
        pool_id = None

    by_ns: Dict[str, int] = {}
    total = 0
    for ns in _REDIS_NAMESPACE_PREFIXES:
        pattern = f"{REDIS_KEY_PREFIX}:{ns}*"
        try:
            cursor = 0
            count = 0
            # Hard cap on iterations to avoid runaway scans on a pathological
            # keyspace (SCAN's cursor can loop in degenerate cases).
            for _ in range(1000):
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=200)
                count += len(keys)
                if cursor == 0:
                    break
            by_ns[ns] = count
            total += count
        except Exception as exc:
            by_ns[ns] = -1
            logger.debug("internal_metrics: redis scan %s failed: %s", ns, exc)

    return {"enabled": True, "key_count": int(total), "by_namespace": by_ns, "pool_id": pool_id}


# ---------------------------------------------------------------------------
# 4) Query spool disk usage
# ---------------------------------------------------------------------------

def _collect_spool() -> Dict[str, Any]:
    """Scan QUERY_SPOOL_DIR for total bytes + file count."""
    try:
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
    except Exception as exc:
        return {"error": f"spool_import_failed: {exc}"}

    spool_root = Path(QUERY_SPOOL_DIR)
    if not spool_root.exists():
        return {
            "enabled": True,
            "total_bytes": 0,
            "file_count": 0,
            "spool_dir": str(spool_root),
        }

    total_bytes = 0
    file_count = 0
    by_namespace: Dict[str, Dict[str, int]] = {}
    try:
        for entry in os.scandir(spool_root):
            if not entry.is_dir(follow_symlinks=False):
                continue
            ns_name = entry.name
            ns_bytes = 0
            ns_count = 0
            try:
                for item in os.scandir(entry.path):
                    if item.is_file(follow_symlinks=False):
                        try:
                            ns_bytes += item.stat().st_size
                            ns_count += 1
                        except OSError:
                            continue
            except OSError as exc:
                by_namespace[ns_name] = {"error_code": 1, "message": str(exc)[:120]}
                continue
            by_namespace[ns_name] = {"total_bytes": ns_bytes, "file_count": ns_count}
            total_bytes += ns_bytes
            file_count += ns_count
    except OSError as exc:
        return {"error": f"spool_scan_failed: {exc}"}

    return {
        "enabled": True,
        "total_bytes": int(total_bytes),
        "file_count": int(file_count),
        "spool_dir": str(spool_root),
        "by_namespace": by_namespace,
    }


# ---------------------------------------------------------------------------
# 5) Worker RSS bytes (this process only)
# ---------------------------------------------------------------------------

def _collect_worker_rss() -> Dict[str, Any]:
    """Return RSS bytes for the current worker PID.

    Each gunicorn worker serves its own metrics snapshot; the soak probe
    is expected to enumerate ``/internal/metrics`` across all workers by
    hitting the server N times and grouping by PID.  We therefore only
    report *this* process here; cross-worker aggregation is the caller's
    responsibility and avoids scraping /proc trees from inside Flask.
    """
    try:
        import psutil  # type: ignore
    except ImportError:
        return {"error": "psutil_missing"}

    pid = os.getpid()
    try:
        proc = psutil.Process(pid)
        rss = int(proc.memory_info().rss)
    except Exception as exc:
        return {"error": f"psutil_read_failed: {exc}", "pid": pid}

    return {"pid": pid, "rss_bytes": rss}


# ---------------------------------------------------------------------------
# 6) Circuit breaker state + counters
# ---------------------------------------------------------------------------

def _collect_circuit_breaker() -> Dict[str, Any]:
    """Return the global DB circuit breaker status snapshot."""
    try:
        from mes_dashboard.core.circuit_breaker import get_circuit_breaker_status
        status = get_circuit_breaker_status()
    except Exception as exc:
        return {"error": f"circuit_breaker_read_failed: {exc}"}

    # last_failure_time / open_until may be floats (epoch seconds) or
    # None; both are JSON-safe.  Keep the shape as-is.
    return dict(status)


# ---------------------------------------------------------------------------
# 7) RQ queue depth per queue
# ---------------------------------------------------------------------------

_RQ_REGISTRY_KEYS = ("started", "failed", "finished", "deferred")


def _collect_rq() -> Dict[str, Any]:
    """Per-queue pending / started / failed / finished / deferred counts.

    Unlike rq_monitor_service.get_rq_queue_details() (which only reports
    depth/started/failed), this collector also reads finished_job_registry
    and deferred_job_registry because the soak scenario asserts *queue
    depth growth*, not just active work.  "No resource leak but backlog
    creeps upward" is invisible without observing all five registries.
    """
    from mes_dashboard.services.rq_monitor_service import _QUEUE_NAMES, _check_rq_installed

    if not _check_rq_installed():
        return {"enabled": False, "by_queue": {}}

    try:
        from mes_dashboard.core.redis_client import get_redis_client
    except Exception as exc:
        return {"error": f"rq_redis_client_import_failed: {exc}"}

    conn = get_redis_client()
    if conn is None:
        return {"enabled": True, "by_queue": {}, "error": "redis_unavailable"}

    try:
        from rq import Queue  # type: ignore
    except ImportError:
        return {"enabled": False, "by_queue": {}}

    by_queue: Dict[str, Dict[str, int]] = {}
    for qname in _QUEUE_NAMES:
        entry: Dict[str, int] = {
            "pending": 0,
            "started": 0,
            "failed": 0,
            "finished": 0,
            "deferred": 0,
        }
        try:
            q = Queue(qname, connection=conn)
            entry["pending"] = int(len(q))
            for reg_key in _RQ_REGISTRY_KEYS:
                registry = getattr(q, f"{reg_key}_job_registry", None)
                if registry is None:
                    continue
                try:
                    entry[reg_key] = int(registry.count)
                except Exception:
                    # count is usually a property that hits Redis; tolerate
                    # a transient read error without losing the whole row.
                    continue
        except Exception as exc:
            logger.debug("internal_metrics: rq queue %s read failed: %s", qname, exc)
            entry["error_message"] = str(exc)[:120]  # keep JSON-safe
        by_queue[qname] = entry

    return {"enabled": True, "by_queue": by_queue}


# ---------------------------------------------------------------------------
# 8) Active thread names (this worker only)
# ---------------------------------------------------------------------------

def _collect_threads() -> Dict[str, Any]:
    """Return sorted list of thread names alive in the current worker process.

    Used by GunicornHarness-based fork-safety tests (AC-5) to assert that
    every expected background thread (cache_updater, equipment-status-sync,
    metrics-history-collector, worker-rss-guard, query-spool-cleanup,
    anomaly-detection-scheduler, etc.) was started by post_fork.

    Thread names are the ``name=`` kwarg set at threading.Thread creation time
    by each subsystem; this collector enumerates them verbatim so tests can
    match by substring.
    """
    import threading
    return {"names": sorted(t.name for t in threading.enumerate())}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_internal_metrics() -> Dict[str, Any]:
    """Build the eight-category metrics snapshot.

    Keys (stable contract consumed by `/internal/metrics` and by the
    soak probe): ``pool``, ``duckdb``, ``redis``, ``spool``,
    ``worker_rss``, ``circuit_breaker``, ``rq``, ``threads``.

    The ``threads`` category was added for GunicornHarness fork-safety
    tests (AC-5): it lists all thread names alive in this worker process
    so integration tests can assert the expected per-worker background
    threads (cache_updater, equipment-sync, etc.) are running post-fork.
    """
    return {
        "pool": _collect_pool(),
        "duckdb": _collect_duckdb(),
        "redis": _collect_redis(),
        "spool": _collect_spool(),
        "worker_rss": _collect_worker_rss(),
        "circuit_breaker": _collect_circuit_breaker(),
        "rq": _collect_rq(),
        "threads": _collect_threads(),
    }


__all__ = ["collect_internal_metrics"]
