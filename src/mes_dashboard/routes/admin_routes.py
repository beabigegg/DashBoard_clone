# -*- coding: utf-8 -*-
"""Admin routes for page management and performance monitoring."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, g, make_response, redirect, request, url_for

from mes_dashboard.core.csrf import get_csrf_token
from mes_dashboard.core.permissions import admin_required
from mes_dashboard.core.response import (
    error_response,
    internal_error,
    not_found_error,
    success_response,
    validation_error,
    TOO_MANY_REQUESTS,
)
from mes_dashboard.core.resilience import (
    build_recovery_recommendation,
    get_resilience_thresholds,
    summarize_restart_history,
)
from mes_dashboard.core.runtime_contract import (
    build_runtime_contract_diagnostics,
    load_runtime_contract,
)
from mes_dashboard.core.worker_recovery_policy import (
    decide_restart_request,
    evaluate_worker_recovery_state,
    extract_last_requested_at,
    extract_restart_history,
    load_restart_state,
)
from mes_dashboard.services.page_registry import (
    DrawerConflictError,
    DrawerNotFoundError,
    create_drawer,
    delete_drawer,
    get_all_drawers,
    get_all_pages,
    get_page_status,
    set_page_status,
    update_drawer,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
logger = logging.getLogger("mes_dashboard.admin")

# ============================================================
# Worker Restart Configuration
# ============================================================

_RUNTIME_CONTRACT = load_runtime_contract()
WATCHDOG_RUNTIME_DIR = _RUNTIME_CONTRACT["watchdog_runtime_dir"]
RESTART_FLAG_PATH = _RUNTIME_CONTRACT["watchdog_restart_flag"]
RESTART_STATE_PATH = _RUNTIME_CONTRACT["watchdog_state_file"]
WATCHDOG_PID_PATH = _RUNTIME_CONTRACT["watchdog_pid_file"]
GUNICORN_BIND = _RUNTIME_CONTRACT["gunicorn_bind"]
RUNTIME_CONTRACT_VERSION = _RUNTIME_CONTRACT["version"]

# Track last restart request time (in-memory for this worker)
_last_restart_request: float = 0.0


# ============================================================
# Performance Monitoring Routes
# ============================================================

@admin_bp.route("/performance")
@admin_required
def performance():
    """Deprecated — redirect to unified dashboard."""
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """Unified admin dashboard (Vue SPA)."""
    dist_dir = os.path.join(current_app.static_folder or "", "dist")
    html_path = os.path.join(dist_dir, "admin-dashboard.html")
    csrf_meta = f'<meta name="csrf-token" content="{get_csrf_token()}">'

    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace("<meta charset", f"{csrf_meta}\n    <meta charset", 1)
        return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})

    # Test/local fallback when frontend artifacts are not copied yet.
    html = (
        "<!doctype html><html lang=\"zh-Hant\"><head>"
        f"{csrf_meta}"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Admin Dashboard</title>"
        "<link rel=\"stylesheet\" href=\"/static/dist/tailwind.css\">"
        "<link rel=\"stylesheet\" href=\"/static/dist/admin-dashboard.css\">"
        "<script type=\"module\" src=\"/static/dist/admin-dashboard.js\"></script>"
        "</head><body><div id='app'></div></body></html>"
    )
    return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})


@admin_bp.route("/api/system-status", methods=["GET"])
@admin_required
def api_system_status():
    """API: Get system status for performance dashboard."""
    from mes_dashboard.core.database import get_pool_runtime_config, get_pool_status
    from mes_dashboard.core.redis_client import REDIS_ENABLED
    from mes_dashboard.core.circuit_breaker import get_circuit_breaker_status
    from mes_dashboard.routes.health_routes import (
        check_database,
        check_redis,
        get_route_cache_status,
    )

    # Database status
    db_status, db_error = check_database()

    # Redis status
    redis_status = 'disabled'
    if REDIS_ENABLED:
        redis_status, _ = check_redis()

    # Circuit breaker status
    circuit_breaker = get_circuit_breaker_status()
    route_cache = get_route_cache_status()
    pool_runtime = get_pool_runtime_config()
    try:
        pool_state = get_pool_status()
    except Exception:
        pool_state = None
    thresholds = get_resilience_thresholds()
    restart_state = _get_restart_state()
    restart_churn = _get_restart_churn_summary(restart_state)
    policy_state = _get_restart_policy_state(restart_state)
    in_cooldown = bool(policy_state.get("cooldown"))
    remaining = int(policy_state.get("cooldown_remaining_seconds") or 0)

    degraded_reason = None
    if db_status == "error":
        degraded_reason = "database_unreachable"
    elif circuit_breaker.get("state") == "OPEN":
        degraded_reason = "circuit_breaker_open"
    elif (pool_state or {}).get("saturation", 0.0) >= 1.0:
        degraded_reason = "db_pool_saturated"
    elif redis_status == "error":
        degraded_reason = "redis_unavailable"
    elif route_cache.get("degraded"):
        degraded_reason = "route_cache_degraded"
    recommendation = build_recovery_recommendation(
        degraded_reason=degraded_reason,
        pool_saturation=(pool_state or {}).get("saturation"),
        circuit_state=circuit_breaker.get("state"),
        restart_churn_exceeded=bool(restart_churn.get("exceeded")),
        cooldown_active=in_cooldown,
    )
    alerts = _build_restart_alerts(
        pool_saturation=(pool_state or {}).get("saturation"),
        circuit_state=circuit_breaker.get("state"),
        route_cache_degraded=bool(route_cache.get("degraded")),
        policy_state=policy_state,
        thresholds=thresholds,
    )
    runtime_contract = build_runtime_contract_diagnostics(strict=False)

    # Cache status
    from mes_dashboard.routes.health_routes import (
        get_cache_status,
        get_resource_cache_status,
        get_equipment_status_cache_status
    )

    return success_response({
        "database": {
            "status": db_status,
            "error": db_error
        },
        "redis": {
            "status": redis_status,
            "enabled": REDIS_ENABLED
        },
        "circuit_breaker": circuit_breaker,
        "cache": {
            "wip": get_cache_status(),
            "resource": get_resource_cache_status(),
            "equipment": get_equipment_status_cache_status()
        },
        "runtime_resilience": {
            "degraded_reason": degraded_reason,
            "pool_runtime": pool_runtime,
            "pool_state": pool_state,
            "route_cache": route_cache,
            "thresholds": thresholds,
            "alerts": alerts,
            "restart_churn": restart_churn,
            "policy_state": {
                "state": policy_state.get("state"),
                "allowed": policy_state.get("allowed"),
                "cooldown": policy_state.get("cooldown"),
                "blocked": policy_state.get("blocked"),
                "cooldown_remaining_seconds": remaining,
            },
            "recovery_recommendation": recommendation,
            "restart_cooldown": {
                "active": in_cooldown,
                "remaining_seconds": remaining if in_cooldown else 0,
            },
        },
        "runtime_contract": runtime_contract,
        "single_port_bind": GUNICORN_BIND,
        "worker_pid": os.getpid()
    })


@admin_bp.route("/api/metrics", methods=["GET"])
@admin_required
def api_metrics():
    """API: Get performance metrics for dashboard."""
    from mes_dashboard.core.metrics import get_metrics_summary, get_query_metrics

    summary = get_metrics_summary()
    metrics = get_query_metrics()

    return success_response({
        "p50_ms": summary.get("p50_ms"),
        "p95_ms": summary.get("p95_ms"),
        "p99_ms": summary.get("p99_ms"),
        "count": summary.get("count"),
        "slow_count": summary.get("slow_count"),
        "slow_rate": summary.get("slow_rate"),
        "worker_pid": summary.get("worker_pid"),
        "collected_at": summary.get("collected_at"),
        # Include latency distribution for charts
        "latencies": metrics.get_latencies()[-100:]  # Last 100 for chart
    })


@admin_bp.route("/api/logs", methods=["GET"])
@admin_required
def api_logs():
    """API: Get recent logs. Merges SQLite (unsynced) + MySQL (historical) when enabled."""
    from mes_dashboard.core.log_store import get_log_store, LOG_STORE_ENABLED
    from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED

    if not LOG_STORE_ENABLED:
        return success_response({"logs": [], "enabled": False, "total": 0})

    level = request.args.get("level")
    q = request.args.get("q")
    limit = min(request.args.get("limit", 50, type=int), 1000)
    offset = request.args.get("offset", 0, type=int)
    since = request.args.get("since")

    log_store = get_log_store()

    if MYSQL_OPS_ENABLED:
        # --- dual-layer: SQLite (all rows) + MySQL historical ---
        # Compute authoritative combined total independently of the windowed fetch.
        sqlite_total = log_store.count_logs(level=level, q=q, since=since)
        mysql_total = _count_mysql_logs(level=level, q=q, since=since)
        total = sqlite_total + mysql_total

        # Fetch enough rows from each source to cover the requested window.
        fetch_limit = offset + limit
        sqlite_rows = log_store.query_logs_all(
            level=level, q=q, limit=fetch_limit, since=since
        )
        mysql_rows = _query_mysql_logs(level=level, q=q, since=since, limit=fetch_limit)

        # Merge sort by timestamp DESC — parse to datetime for correct cross-source ordering
        def _sort_key(r):
            ts = r.get("timestamp") or ""
            try:
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                from datetime import timezone as _tz
                return datetime.min.replace(tzinfo=_tz.utc)

        all_rows = sorted(
            sqlite_rows + mysql_rows,
            key=_sort_key,
            reverse=True,
        )
        merged = all_rows[offset: offset + limit]
    else:
        total = log_store.count_logs(level=level, q=q, since=since)
        merged = log_store.query_logs_all(
            level=level, q=q, limit=limit, offset=offset, since=since
        )

    return success_response({
        "logs": merged,
        "count": len(merged),
        "total": total,
        "enabled": True,
        "stats": log_store.get_stats(),
    })


def _query_mysql_logs(
    level=None, q=None, since=None, limit: int = 1000
) -> list:
    """Query dashboard_logs from MySQL. Returns [] on any error."""
    try:
        from mes_dashboard.core.mysql_client import get_mysql_connection
        from sqlalchemy import text

        where = "1=1"
        params: dict = {}
        if level:
            where += " AND level = :level"
            params["level"] = level.upper()
        if q:
            where += " AND message LIKE :q"
            params["q"] = f"%{q}%"
        if since:
            where += " AND timestamp >= :since"
            params["since"] = since

        sql = text(
            f"SELECT sync_id, timestamp, level, logger_name, message, "
            f"request_id, user, ip, extra FROM dashboard_logs "
            f"WHERE {where} ORDER BY timestamp DESC LIMIT :limit"
        )
        params["limit"] = limit

        with get_mysql_connection() as conn:
            result = conn.execute(sql, params)
            keys = result.keys()
            rows = []
            for row in result.fetchall():
                d = dict(zip(keys, row))
                from mes_dashboard.core.log_store import _normalize_iso_to_utc
                d['timestamp'] = _normalize_iso_to_utc(d.get('timestamp'))
                rows.append(d)
            return rows
    except Exception as exc:
        logger.error(
            "MySQL log query failed, falling back to SQLite only: %s", exc,
            exc_info=True,
        )
        return []


def _count_mysql_logs(
    level=None, q=None, since=None
) -> int:
    """Count rows in dashboard_logs matching filters. Returns 0 on any error."""
    try:
        from mes_dashboard.core.mysql_client import get_mysql_connection
        from sqlalchemy import text

        where = "1=1"
        params: dict = {}
        if level:
            where += " AND level = :level"
            params["level"] = level.upper()
        if q:
            where += " AND message LIKE :q"
            params["q"] = f"%{q}%"
        if since:
            where += " AND timestamp >= :since"
            params["since"] = since

        sql = text(f"SELECT COUNT(*) FROM dashboard_logs WHERE {where}")

        with get_mysql_connection() as conn:
            result = conn.execute(sql, params)
            row = result.fetchone()
            return int(row[0]) if row else 0
    except Exception as exc:
        logger.debug("MySQL log count failed, returning 0: %s", exc)
        return 0


def _collect_spool_disk_usage() -> list:
    """Scan spool directory and return per-namespace disk usage stats."""
    try:
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
        spool_root = Path(QUERY_SPOOL_DIR).resolve()
    except Exception as exc:
        return [{"namespace": "__root__", "error": str(exc)}]

    if not spool_root.exists():
        return []

    result = []
    try:
        entries = list(os.scandir(spool_root))
    except OSError as exc:
        return [{"namespace": "__root__", "error": str(exc)}]

    for entry in entries:
        if not entry.is_dir():
            continue
        ns = entry.name
        try:
            file_count = 0
            total_bytes = 0
            for item in os.scandir(entry.path):
                if item.is_file(follow_symlinks=False):
                    file_count += 1
                    total_bytes += item.stat().st_size
            result.append({"namespace": ns, "file_count": file_count, "total_bytes": total_bytes})
        except OSError as exc:
            result.append({"namespace": ns, "error": str(exc)})

    return result


def _collect_redis_namespace_memory(client) -> list:
    """Sample Redis MEMORY USAGE for representative keys per namespace."""
    key_prefix = None
    try:
        from mes_dashboard.core.redis_client import REDIS_KEY_PREFIX
        key_prefix = REDIS_KEY_PREFIX
    except Exception:
        key_prefix = "mes"

    namespaces = [
        ("mes_wip", f"{key_prefix}:data:parquet"),
        ("resource", f"{key_prefix}:resource:data"),
        ("equipment", f"{key_prefix}:equipment_status:data"),
        ("reject_dataset", f"{key_prefix}:reject_dataset:*"),
        ("hold_dataset", f"{key_prefix}:hold_dataset:*"),
        ("hold_today", f"{key_prefix}:hold_today:*"),
        ("yield_alert", f"{key_prefix}:yield_alert_dataset:*"),
    ]

    result = []
    for ns_name, pattern in namespaces:
        try:
            # Find a representative key
            if pattern.endswith(":*"):
                _base = pattern[:-2]
                cursor, keys = client.scan(cursor=0, match=pattern, count=5)
                sample_key = keys[0] if keys else None
            else:
                sample_key = pattern if client.exists(pattern) else None

            if sample_key is None:
                result.append({"namespace": ns_name, "sample_key": None, "estimated_bytes": None})
                continue

            # MEMORY USAGE with timeout protection via socket timeout already on client
            mem = client.execute_command("MEMORY", "USAGE", sample_key, "SAMPLES", "0")
            result.append({
                "namespace": ns_name,
                "sample_key": sample_key,
                "estimated_bytes": mem,
            })
        except Exception as exc:
            result.append({"namespace": ns_name, "error": str(exc)})

    return result


@admin_bp.route("/api/performance-detail", methods=["GET"])
@admin_required
def api_performance_detail():
    """API: Get detailed performance telemetry for admin dashboard.

    Returns redis, process_caches, route_cache, db_pool, and
    direct_connections sections in a single response.
    """
    from mes_dashboard.core.cache import get_all_process_cache_stats
    from mes_dashboard.core.database import (
        get_direct_connection_count,
        get_pool_runtime_config,
        get_pool_status,
    )
    from mes_dashboard.core.redis_client import (
        get_redis_client,
        REDIS_ENABLED,
        REDIS_KEY_PREFIX,
    )
    from mes_dashboard.routes.health_routes import get_route_cache_status

    # ---- Redis detail ----
    redis_detail = None
    if REDIS_ENABLED:
        client = get_redis_client()
        if client is not None:
            try:
                info = client.info(section="memory")
                stats_info = client.info(section="stats")
                clients_info = client.info(section="clients")

                hits = int(stats_info.get("keyspace_hits", 0))
                misses = int(stats_info.get("keyspace_misses", 0))
                total = hits + misses
                hit_rate = round(hits / total, 4) if total > 0 else 0

                # Scan key counts per namespace
                namespace_prefixes = [
                    "data", "route_cache", "equipment_status",
                    "reject_dataset", "hold_today", "meta", "lock", "scrap_exclusion",
                ]
                namespaces = []
                for ns in namespace_prefixes:
                    pattern = f"{REDIS_KEY_PREFIX}:{ns}*"
                    count = 0
                    cursor = 0
                    while True:
                        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
                        count += len(keys)
                        if cursor == 0:
                            break
                    namespaces.append({"name": ns, "key_count": count})

                redis_detail = {
                    "used_memory_human": info.get("used_memory_human", "N/A"),
                    "used_memory": info.get("used_memory", 0),
                    "peak_memory_human": info.get("used_memory_peak_human", "N/A"),
                    "peak_memory": info.get("used_memory_peak", 0),
                    "maxmemory_human": info.get("maxmemory_human", "N/A"),
                    "maxmemory": info.get("maxmemory", 0),
                    "connected_clients": clients_info.get("connected_clients", 0),
                    "hit_rate": hit_rate,
                    "keyspace_hits": hits,
                    "keyspace_misses": misses,
                    "namespaces": namespaces,
                }

                # --- Additive: evicted_keys, expired_keys (from stats section) ---
                try:
                    redis_detail["evicted_keys"] = int(stats_info.get("evicted_keys", 0))
                except Exception:
                    redis_detail["evicted_keys"] = None

                try:
                    redis_detail["expired_keys"] = int(stats_info.get("expired_keys", 0))
                except Exception:
                    redis_detail["expired_keys"] = None

                # --- Additive: mem_fragmentation_ratio (from memory section) ---
                try:
                    mem_info = client.info(section="memory")
                    redis_detail["mem_fragmentation_ratio"] = mem_info.get(
                        "mem_fragmentation_ratio"
                    )
                except Exception:
                    redis_detail["mem_fragmentation_ratio"] = None

                # --- Additive: slowlog top-5 ---
                try:
                    raw_slowlog = client.slowlog_get(5)
                    redis_detail["slowlog"] = [
                        {
                            "id": e["id"],
                            "duration_us": e["duration"],
                            "command": " ".join(str(a) for a in e["command"][:3]),
                        }
                        for e in raw_slowlog
                    ]
                except Exception:
                    redis_detail["slowlog"] = None

            except Exception as exc:
                logger.warning("Failed to collect Redis detail: %s", exc)
                redis_detail = {"error": str(exc)}

    # ---- Process caches ----
    process_caches = get_all_process_cache_stats()

    # ---- Route cache ----
    route_cache = get_route_cache_status()

    # ---- DB pool ----
    db_pool = None
    try:
        pool_status = get_pool_status()
        pool_config = get_pool_runtime_config()
        db_pool = {
            "status": pool_status,
            "config": {
                "pool_size": pool_config.get("pool_size"),
                "max_overflow": pool_config.get("max_overflow"),
                "pool_timeout": pool_config.get("pool_timeout"),
                "pool_recycle": pool_config.get("pool_recycle"),
            },
        }
    except Exception as exc:
        logger.warning("Failed to collect DB pool status: %s", exc)
        db_pool = {"error": str(exc)}

    # ---- Direct connections ----
    direct_connections = {
        "total_since_start": get_direct_connection_count(),
        "worker_pid": os.getpid(),
    }

    # ---- Worker memory guard telemetry ----
    worker_memory_guard = None
    try:
        from mes_dashboard.core.worker_memory_guard import get_memory_guard_telemetry
        worker_memory_guard = get_memory_guard_telemetry()
    except Exception as exc:
        logger.warning("Failed to collect worker memory guard telemetry: %s", exc)
        worker_memory_guard = {"error": str(exc)}

    # ---- Heavy query guard telemetry ----
    heavy_query_telemetry = None
    try:
        from mes_dashboard.core.heavy_query_telemetry import get_heavy_query_telemetry
        heavy_query_telemetry = get_heavy_query_telemetry()
    except Exception as exc:
        logger.warning("Failed to collect heavy query guard telemetry: %s", exc)
        heavy_query_telemetry = {"error": str(exc)}

    # ---- Async workers (RQ) ----
    async_workers = None
    try:
        from mes_dashboard.services.rq_monitor_service import get_rq_monitor_summary
        async_workers = get_rq_monitor_summary()
    except Exception as exc:
        logger.warning("Failed to collect RQ monitor telemetry: %s", exc)
        async_workers = {"error": str(exc)}

    # ---- Spool disk usage ----
    spool_disk_usage = _collect_spool_disk_usage()

    # ---- Redis per-namespace memory estimate ----
    redis_namespace_memory = None
    if REDIS_ENABLED:
        client_for_mem = get_redis_client()
        if client_for_mem is not None:
            try:
                redis_namespace_memory = _collect_redis_namespace_memory(client_for_mem)
            except Exception as exc:
                logger.warning("Failed to collect Redis namespace memory: %s", exc)
                redis_namespace_memory = [{"error": str(exc)}]

    # ---- DuckDB telemetry ----
    duckdb_telemetry = None
    try:
        from mes_dashboard.core.duckdb_runtime import get_duckdb_telemetry
        duckdb_telemetry = get_duckdb_telemetry()
    except Exception as exc:
        logger.warning("Failed to collect DuckDB telemetry: %s", exc)
        duckdb_telemetry = {"error": str(exc)}

    return success_response({
        "redis": redis_detail,
        "process_caches": process_caches,
        "route_cache": route_cache,
        "db_pool": db_pool,
        "direct_connections": direct_connections,
        "worker_memory_guard": worker_memory_guard,
        "heavy_query_telemetry": heavy_query_telemetry,
        "async_workers": async_workers,
        "spool_disk_usage": spool_disk_usage,
        "redis_namespace_memory": redis_namespace_memory,
        "duckdb": duckdb_telemetry,
    })


@admin_bp.route("/api/performance-history", methods=["GET"])
@admin_required
def api_performance_history():
    """API: Get historical metrics. Merges SQLite (unsynced) + MySQL (historical) when enabled."""
    from mes_dashboard.core.metrics_history import get_metrics_history_store
    from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED

    minutes = max(1, min(request.args.get("minutes", 30, type=int), 180))
    bucket_seconds = request.args.get("bucket", 30, type=int)
    store = get_metrics_history_store()

    sqlite_snapshots = store.query_snapshots_aggregated(
        minutes=minutes, bucket_seconds=bucket_seconds
    )

    if MYSQL_OPS_ENABLED:
        mysql_snapshots = _query_mysql_metrics(minutes=minutes, bucket_seconds=bucket_seconds)
        # Merge by ts ASC
        all_snaps = sorted(
            sqlite_snapshots + mysql_snapshots,
            key=lambda r: r.get("ts") or "",
        )
        # Deduplicate by ts bucket (SQLite unsynced takes precedence)
        seen: dict = {}
        for snap in all_snaps:
            ts_key = snap.get("ts")
            if ts_key not in seen:
                seen[ts_key] = snap
        snapshots = list(seen.values())
    else:
        snapshots = sqlite_snapshots

    return success_response({"snapshots": snapshots, "count": len(snapshots)})


def _query_mysql_metrics(minutes: int = 30, bucket_seconds: int = 30) -> list:
    """Query aggregated metrics from MySQL. Returns [] on any error."""
    try:
        from mes_dashboard.core.mysql_client import get_mysql_connection
        from sqlalchemy import text

        sql = text(f"""
            SELECT
                MIN(ts) AS ts,
                MAX(pool_saturation)    AS pool_saturation,
                MAX(pool_checked_out)   AS pool_checked_out,
                MAX(pool_checked_in)    AS pool_checked_in,
                MAX(pool_overflow)      AS pool_overflow,
                MAX(pool_max_capacity)  AS pool_max_capacity,
                MAX(redis_used_memory)  AS redis_used_memory,
                MAX(redis_hit_rate)     AS redis_hit_rate,
                MAX(rc_l1_hit_rate)     AS rc_l1_hit_rate,
                MAX(rc_l2_hit_rate)     AS rc_l2_hit_rate,
                MAX(rc_miss_rate)       AS rc_miss_rate,
                MAX(latency_p50_ms)     AS latency_p50_ms,
                MAX(latency_p95_ms)     AS latency_p95_ms,
                MAX(latency_p99_ms)     AS latency_p99_ms,
                SUM(latency_count)      AS latency_count,
                MAX(slow_query_active)  AS slow_query_active,
                MAX(slow_query_waiting) AS slow_query_waiting,
                MAX(worker_rss_bytes)   AS worker_rss_bytes,
                MAX(service_rss_bytes)  AS service_rss_bytes,
                MIN(system_mem_available_mb) AS system_mem_available_mb,
                MAX(system_mem_used_pct) AS system_mem_used_pct,
                MAX(rq_workers_total)   AS rq_workers_total,
                MAX(rq_workers_busy)    AS rq_workers_busy,
                MAX(rq_queue_depth)     AS rq_queue_depth,
                MAX(heavy_query_slots_active) AS heavy_query_slots_active,
                MAX(heavy_query_guard_reject_total) AS heavy_query_guard_reject_total,
                MAX(heavy_query_memory_error_total) AS heavy_query_memory_error_total,
                MAX(heavy_query_async_fallback_total) AS heavy_query_async_fallback_total,
                MAX(online_count)       AS online_count,
                COUNT(DISTINCT worker_pid) AS worker_count,
                ROUND(MAX(redis_used_memory) / 1048576.0, 2) AS redis_used_memory_mb
            FROM dashboard_metrics_snapshots
            WHERE ts >= DATE_SUB(NOW(), INTERVAL :minutes MINUTE)
            GROUP BY FLOOR(UNIX_TIMESTAMP(ts) / {bucket_seconds})
            ORDER BY MIN(ts) ASC
        """)

        with get_mysql_connection() as conn:
            result = conn.execute(sql, {"minutes": minutes})
            keys = result.keys()
            rows = []
            for row in result.fetchall():
                d = dict(zip(keys, row))
                # Convert datetime → ISO string to match SQLite format
                if hasattr(d.get("ts"), "isoformat"):
                    d["ts"] = d["ts"].strftime("%Y-%m-%d %H:%M:%S")
                rows.append(d)
            return rows
    except Exception as exc:
        logger.error(
            "MySQL metrics query failed, using SQLite only: %s", exc,
            exc_info=True,
        )
        return []


@admin_bp.route("/api/performance-history/purge", methods=["POST"])
@admin_required
def api_performance_history_purge():
    """API: Purge all historical metrics snapshots (stale data cleanup)."""
    from mes_dashboard.core.metrics_history import get_metrics_history_store

    store = get_metrics_history_store()
    deleted = store.purge()
    return success_response({"deleted": deleted})


@admin_bp.route("/api/storage-info", methods=["GET"])
@admin_required
def api_storage_info():
    """API: Return sizes of SQLite databases, log files, and archive dir."""
    base = Path(__file__).resolve().parents[3]  # project root
    logs_dir = base / "logs"
    archive_dir = logs_dir / "archive"

    def _file_info(p: Path) -> dict:
        try:
            st = p.stat()
            return {"path": str(p.relative_to(base)), "size_bytes": st.st_size}
        except OSError:
            return {"path": str(p.relative_to(base)), "size_bytes": 0}

    # SQLite databases
    sqlite_files = [_file_info(f) for f in sorted(logs_dir.glob("*.sqlite"))]

    # Active log files
    log_files = [_file_info(f) for f in sorted(logs_dir.glob("*.log"))]

    # Archive directory
    archive_files = []
    archive_total = 0
    if archive_dir.is_dir():
        for f in sorted(archive_dir.iterdir()):
            if f.is_file():
                info = _file_info(f)
                archive_files.append(info)
                archive_total += info["size_bytes"]

    total = (
        sum(f["size_bytes"] for f in sqlite_files)
        + sum(f["size_bytes"] for f in log_files)
        + archive_total
    )

    # MySQL stats (if enabled)
    mysql_stats = None
    try:
        from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
        if MYSQL_OPS_ENABLED:
            from mes_dashboard.core.mysql_client import get_mysql_connection, check_mysql_health
            from sqlalchemy import text
            healthy = check_mysql_health()
            logs_count = 0
            metrics_count = 0
            if healthy:
                with get_mysql_connection() as conn:
                    logs_count = conn.execute(
                        text("SELECT COUNT(*) FROM dashboard_logs")
                    ).scalar() or 0
                    metrics_count = conn.execute(
                        text("SELECT COUNT(*) FROM dashboard_metrics_snapshots")
                    ).scalar() or 0
            mysql_stats = {
                "enabled": True,
                "healthy": healthy,
                "dashboard_logs_rows": logs_count,
                "dashboard_metrics_snapshots_rows": metrics_count,
            }
    except Exception as exc:
        logger.warning("Failed to collect MySQL stats: %s", exc)
        mysql_stats = {"enabled": True, "healthy": False, "error": str(exc)}

    return success_response({
        "sqlite_files": sqlite_files,
        "log_files": log_files,
        "archive_files": archive_files,
        "archive_total_bytes": archive_total,
        "total_bytes": total,
        "mysql": mysql_stats,
    })


@admin_bp.route("/api/log-files/cleanup", methods=["POST"])
@admin_required
def api_log_files_cleanup():
    """API: Truncate active log files and/or purge archive directory."""
    base = Path(__file__).resolve().parents[3]
    logs_dir = base / "logs"
    archive_dir = logs_dir / "archive"

    data = request.get_json(silent=True) or {}
    targets = data.get("targets", ["archive", "logs"])  # default: both

    logger.debug("Log file cleanup: base=%s, logs_dir=%s, archive_dir=%s", base, logs_dir, archive_dir)

    cleaned = {"log_files": [], "archive_files": []}
    total_freed = 0

    # Truncate active .log files (not SQLite — those have their own cleanup)
    if "logs" in targets:
        for f in logs_dir.glob("*.log"):
            try:
                size = f.stat().st_size
                if size > 0:
                    f.write_text("")
                    cleaned["log_files"].append(str(f.name))
                    total_freed += size
            except OSError as exc:
                logger.warning("Failed to truncate %s: %s", f, exc)

    # Remove archive files
    if "archive" in targets:
        if archive_dir.is_dir():
            for f in archive_dir.iterdir():
                if f.is_file():
                    try:
                        size = f.stat().st_size
                        f.unlink()
                        cleaned["archive_files"].append(str(f.name))
                        total_freed += size
                    except OSError as exc:
                        logger.warning("Failed to remove archive file %s: %s", f, exc)

    user = getattr(g, "username", "unknown")
    logger.info(
        "Log file cleanup by %s: freed %d bytes, targets=%s",
        user, total_freed, targets,
    )

    return success_response({
        "freed_bytes": total_freed,
        "cleaned": cleaned,
    })


@admin_bp.route("/api/logs/cleanup", methods=["POST"])
@admin_required
def api_logs_cleanup():
    """API: Manually trigger log cleanup.

    Supports optional parameters:
    - older_than_days: Delete logs older than N days (default: use configured retention)
    - include_mysql: If true and MySQL enabled, also delete all MySQL dashboard_logs rows
    """
    from mes_dashboard.core.log_store import get_log_store, LOG_STORE_ENABLED

    if not LOG_STORE_ENABLED:
        return validation_error("Log store is disabled")

    data = request.get_json(silent=True) or {}
    include_mysql = data.get("include_mysql", False)
    clear_all = data.get("clear_all", False)

    log_store = get_log_store()
    stats_before = log_store.get_stats()
    deleted = log_store.clear_all_logs() if clear_all else log_store.cleanup_old_logs()
    stats_after = log_store.get_stats()

    mysql_deleted = 0
    if include_mysql:
        try:
            from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
            if MYSQL_OPS_ENABLED:
                from mes_dashboard.core.mysql_client import get_mysql_connection
                from sqlalchemy import text
                with get_mysql_connection() as conn:
                    result = conn.execute(text("DELETE FROM dashboard_logs"))
                    mysql_deleted = result.rowcount
        except Exception as exc:
            logger.warning("MySQL log cleanup failed: %s", exc)

    user = getattr(g, "username", "unknown")
    logger.info(
        "Log cleanup triggered by %s: SQLite deleted %d, MySQL deleted %d",
        user, deleted, mysql_deleted,
    )

    return success_response({
        "deleted": deleted,
        "mysql_deleted": mysql_deleted,
        "before": {
            "count": stats_before.get("count", 0),
            "size_bytes": stats_before.get("size_bytes", 0),
        },
        "after": {
            "count": stats_after.get("count", 0),
            "size_bytes": stats_after.get("size_bytes", 0),
        },
    })


# ============================================================
# Worker Restart Control Routes
# ============================================================

def _get_restart_state() -> dict:
    """Read worker restart state from file."""
    return load_restart_state(RESTART_STATE_PATH)


def _iso_from_epoch(ts: float) -> str | None:
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _check_restart_cooldown() -> tuple[bool, float]:
    """Check if restart is in cooldown.

    Returns:
        Tuple of (is_in_cooldown, remaining_seconds).
    """
    policy = _get_restart_policy_state()
    if policy.get("cooldown"):
        return True, float(policy.get("cooldown_remaining_seconds") or 0.0)
    return False, 0.0


def _get_restart_history(state: dict | None = None) -> list[dict]:
    """Return bounded restart history for admin telemetry."""
    payload = state if state is not None else _get_restart_state()
    return extract_restart_history(payload)[-20:]


def _get_restart_churn_summary(state: dict | None = None) -> dict:
    """Summarize restart churn within active resilience window."""
    history = _get_restart_history(state)
    return summarize_restart_history(history)


def _get_restart_policy_state(state: dict | None = None) -> dict[str, Any]:
    """Return effective worker restart policy state."""
    payload = state if state is not None else _get_restart_state()
    history = _get_restart_history(payload)
    last_requested = extract_last_requested_at(payload)

    in_memory_requested = _iso_from_epoch(_last_restart_request)
    if in_memory_requested:
        try:
            in_memory_dt = datetime.fromisoformat(in_memory_requested)
            persisted_dt = datetime.fromisoformat(last_requested) if last_requested else None
        except (TypeError, ValueError):
            in_memory_dt = None
            persisted_dt = None
        if in_memory_dt and (persisted_dt is None or in_memory_dt > persisted_dt):
            last_requested = in_memory_requested

    return evaluate_worker_recovery_state(
        history,
        last_requested_at=last_requested,
    )


def _build_restart_alerts(
    *,
    pool_saturation: float | None,
    circuit_state: str | None,
    route_cache_degraded: bool,
    policy_state: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    saturation = float(pool_saturation or 0.0)
    warning = float(thresholds.get("pool_saturation_warning", 0.9))
    critical = float(thresholds.get("pool_saturation_critical", 1.0))
    return {
        "pool_warning": saturation >= warning,
        "pool_critical": saturation >= critical,
        "circuit_open": circuit_state == "OPEN",
        "route_cache_degraded": bool(route_cache_degraded),
        "restart_churn_exceeded": bool(policy_state.get("churn_exceeded")),
        "restart_blocked": bool(policy_state.get("blocked")),
    }


def _log_restart_audit(event: str, payload: dict[str, Any]) -> None:
    entry = {
        "event": event,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        **payload,
    }
    logger.info("worker_restart_audit %s", json.dumps(entry, ensure_ascii=False))


@admin_bp.route("/api/worker/restart", methods=["POST"])
@admin_required
def api_worker_restart():
    """API: Request worker restart.

    Writes a restart flag file that the watchdog process monitors.
    Enforces a 60-second cooldown between restart requests.
    """
    global _last_restart_request

    payload = request.get_json(silent=True) or {}
    manual_override = bool(payload.get("manual_override"))
    override_acknowledged = bool(payload.get("override_acknowledged"))
    override_reason = str(payload.get("override_reason") or "").strip()

    # Get request metadata
    user = getattr(g, "username", "unknown")
    ip = request.remote_addr or "unknown"
    timestamp = datetime.now(tz=timezone.utc).isoformat()

    state = _get_restart_state()
    policy_state = _get_restart_policy_state(state)
    decision = decide_restart_request(
        policy_state,
        source="manual",
        manual_override=manual_override,
        override_acknowledged=override_acknowledged,
    )

    if manual_override and not override_reason:
        return error_response(
            "RESTART_OVERRIDE_REASON_REQUIRED",
            "Manual override requires non-empty override_reason for audit traceability.",
            status_code=400,
        )

    if not decision["allowed"]:
        status_code = 429 if policy_state.get("cooldown") else 409
        if status_code == 429:
            message = (
                f"Restart in cooldown. Please wait "
                f"{int(policy_state.get('cooldown_remaining_seconds') or 0)} seconds."
            )
            code = TOO_MANY_REQUESTS
        else:
            message = (
                "Restart blocked by guarded mode. "
                "Set manual_override=true and override_acknowledged=true to proceed."
            )
            code = "RESTART_POLICY_BLOCKED"
        _log_restart_audit(
            "restart_request_blocked",
            {
                "actor": user,
                "ip": ip,
                "decision": decision,
                "policy_state": policy_state,
            },
        )
        return error_response(
            code,
            message,
            status_code=status_code,
        )

    # Write restart flag file
    flag_path = Path(RESTART_FLAG_PATH)
    flag_data = {
        "user": user,
        "ip": ip,
        "timestamp": timestamp,
        "worker_pid": os.getpid(),
        "source": "manual",
        "manual_override": bool(manual_override and override_acknowledged),
        "override_acknowledged": override_acknowledged,
        "override_reason": override_reason or None,
        "policy_state": policy_state,
        "policy_decision": decision["decision"],
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
    }

    try:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = flag_path.with_suffix(flag_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(flag_data, ensure_ascii=False))
        tmp_path.replace(flag_path)
    except IOError as e:
        logger.error(f"Failed to write restart flag: {e}")
        return error_response(
            "RESTART_FAILED",
            f"Failed to request restart: {e}",
            status_code=500
        )

    # Update in-memory cooldown
    _last_restart_request = time.time()

    _log_restart_audit(
        "restart_request_accepted",
        {
            "actor": user,
            "ip": ip,
            "decision": decision,
            "policy_state": policy_state,
            "override_reason": override_reason or None,
        },
    )

    return success_response({
        "message": "Restart requested. Workers will reload shortly.",
        "requested_by": user,
        "requested_at": timestamp,
        "policy_state": {
            "state": policy_state.get("state"),
            "allowed": policy_state.get("allowed"),
            "cooldown": policy_state.get("cooldown"),
            "blocked": policy_state.get("blocked"),
            "cooldown_remaining_seconds": policy_state.get("cooldown_remaining_seconds"),
        },
        "decision": decision,
        "single_port_bind": GUNICORN_BIND,
        "watchdog": {
            "runtime_dir": WATCHDOG_RUNTIME_DIR,
            "flag_path": RESTART_FLAG_PATH,
            "pid_path": WATCHDOG_PID_PATH,
            "state_path": RESTART_STATE_PATH,
        },
    })


@admin_bp.route("/api/worker/status", methods=["GET"])
@admin_required
def api_worker_status():
    """API: Get worker status and restart information."""
    # Get last restart info
    state = _get_restart_state()
    last_restart = state.get("last_restart", {})
    history = _get_restart_history(state)
    churn = _get_restart_churn_summary(state)
    policy_state = _get_restart_policy_state(state)
    thresholds = get_resilience_thresholds()
    recommendation = build_recovery_recommendation(
        degraded_reason="db_pool_saturated" if policy_state.get("blocked") else None,
        pool_saturation=None,
        circuit_state=None,
        restart_churn_exceeded=bool(churn.get("exceeded")),
        cooldown_active=bool(policy_state.get("cooldown")),
    )
    runtime_contract = build_runtime_contract_diagnostics(strict=False)

    # Get worker start time (psutil is optional)
    worker_start_time = None
    try:
        import psutil
        process = psutil.Process(os.getpid())
        worker_start_time = datetime.fromtimestamp(
            process.create_time(), tz=timezone.utc
        ).isoformat()
    except ImportError:
        # psutil not installed, try /proc on Linux
        try:
            stat_path = f"/proc/{os.getpid()}/stat"
            with open(stat_path) as f:
                _stat = f.read().split()
                # Field 22 is starttime in clock ticks since boot
                # This is a simplified fallback
                pass
        except Exception:
            pass
    except Exception:
        pass

    return success_response({
        "worker_pid": os.getpid(),
        "worker_start_time": worker_start_time,
        "runtime_contract": {
            "version": runtime_contract["contract"]["version"],
            "validation": {
                "valid": runtime_contract["valid"],
                "errors": runtime_contract["errors"],
            },
            "single_port_bind": GUNICORN_BIND,
            "watchdog": {
                "runtime_dir": WATCHDOG_RUNTIME_DIR,
                "flag_path": RESTART_FLAG_PATH,
                "flag_exists": Path(RESTART_FLAG_PATH).exists(),
                "pid_path": WATCHDOG_PID_PATH,
                "pid_exists": Path(WATCHDOG_PID_PATH).exists(),
                "state_path": RESTART_STATE_PATH,
                "state_exists": Path(RESTART_STATE_PATH).exists(),
            },
        },
        "cooldown": {
            "active": bool(policy_state.get("cooldown")),
            "remaining_seconds": int(policy_state.get("cooldown_remaining_seconds") or 0)
        },
        "resilience": {
            "thresholds": thresholds,
            "alerts": {
                "restart_churn_exceeded": bool(churn.get("exceeded")),
                "restart_blocked": bool(policy_state.get("blocked")),
            },
            "restart_churn": churn,
            "policy_state": {
                "state": policy_state.get("state"),
                "allowed": policy_state.get("allowed"),
                "cooldown": policy_state.get("cooldown"),
                "blocked": policy_state.get("blocked"),
                "cooldown_remaining_seconds": policy_state.get("cooldown_remaining_seconds"),
                "attempts_in_window": policy_state.get("attempts_in_window"),
                "retry_budget": policy_state.get("retry_budget"),
                "churn_threshold": policy_state.get("churn_threshold"),
                "window_seconds": policy_state.get("window_seconds"),
            },
            "recovery_recommendation": recommendation,
        },
        "restart_history": history,
        "last_restart": {
            "requested_by": last_restart.get("requested_by"),
            "requested_at": last_restart.get("requested_at"),
            "requested_ip": last_restart.get("requested_ip"),
            "completed_at": last_restart.get("completed_at"),
            "success": last_restart.get("success")
        }
    })


# ============================================================
# User Usage KPI Routes
# ============================================================

@admin_bp.route("/user-usage-kpi")
@admin_required
def user_usage_kpi():
    """Deprecated — redirect to unified dashboard."""
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/api/user-usage-kpi", methods=["GET"])
@admin_required
def api_user_usage_kpi():
    """API: Get user usage KPI data."""
    from datetime import datetime, timedelta

    from mes_dashboard.services.user_usage_kpi_service import get_user_usage_kpi

    default_start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    default_end = datetime.now().strftime("%Y-%m-%d")

    start_date = request.args.get("start_date", default_start)
    end_date = request.args.get("end_date", default_end)
    department = request.args.get("department") or None

    data = get_user_usage_kpi(start_date, end_date, department)
    data["filters"] = {
        "start_date": start_date,
        "end_date": end_date,
        "department": department,
    }
    return success_response(data)


# ============================================================
# Page Management Routes
# ============================================================

@admin_bp.route("/pages")
@admin_required
def pages():
    """Page management interface (Vue SPA)."""
    dist_dir = os.path.join(current_app.static_folder or "", "dist")
    html_path = os.path.join(dist_dir, "admin-pages.html")
    csrf_meta = f'<meta name="csrf-token" content="{get_csrf_token()}">'

    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace("<meta charset", f"{csrf_meta}\n    <meta charset", 1)
        return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})

    # Test/local fallback when frontend artifacts are not yet built.
    html = (
        "<!doctype html><html lang=\"zh-Hant\"><head>"
        f"{csrf_meta}"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>頁面管理</title>"
        "<link rel=\"stylesheet\" href=\"/static/dist/tailwind.css\">"
        "<link rel=\"stylesheet\" href=\"/static/dist/admin-pages.css\">"
        "<script type=\"module\" src=\"/static/dist/admin-pages.js\"></script>"
        "</head><body><div id='app'></div></body></html>"
    )
    return make_response(html, 200, {"Content-Type": "text/html; charset=utf-8"})


@admin_bp.route("/api/pages", methods=["GET"])
@admin_required
def api_get_pages():
    """API: Get all page configurations."""
    return success_response({"pages": get_all_pages()})


@admin_bp.route("/api/drawers", methods=["GET"])
@admin_required
def api_get_drawers():
    """API: Get all drawer configurations."""
    return success_response({"drawers": get_all_drawers()})


@admin_bp.route("/api/drawers", methods=["POST"])
@admin_required
def api_create_drawer():
    """API: Create a new drawer."""
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    order = payload.get("order")
    admin_only = bool(payload.get("admin_only", False))

    try:
        drawer = create_drawer(name=name, order=order, admin_only=admin_only)
    except DrawerConflictError as exc:
        return error_response("CONFLICT", str(exc), status_code=409)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to create drawer")
        return internal_error(str(exc))

    return success_response({"drawer": drawer}, status_code=201)


@admin_bp.route("/api/drawers/<drawer_id>", methods=["PUT"])
@admin_required
def api_update_drawer(drawer_id: str):
    """API: Update drawer name/order/admin_only."""
    payload = request.get_json(silent=True) or {}
    updates: dict[str, Any] = {}

    if "name" in payload:
        updates["name"] = payload.get("name")
    if "order" in payload:
        updates["order"] = payload.get("order")
    if "admin_only" in payload:
        updates["admin_only"] = bool(payload.get("admin_only"))

    if not updates:
        return validation_error("No drawer fields to update")

    try:
        drawer = update_drawer(drawer_id, **updates)
    except DrawerNotFoundError as exc:
        return not_found_error(str(exc))
    except DrawerConflictError as exc:
        return error_response("CONFLICT", str(exc), status_code=409)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to update drawer %s", drawer_id)
        return internal_error(str(exc))

    return success_response({"drawer": drawer})


@admin_bp.route("/api/drawers/<drawer_id>", methods=["DELETE"])
@admin_required
def api_delete_drawer(drawer_id: str):
    """API: Delete a drawer if no pages are assigned to it."""
    try:
        delete_drawer(drawer_id)
    except DrawerNotFoundError as exc:
        return not_found_error(str(exc))
    except DrawerConflictError as exc:
        return error_response("CONFLICT", str(exc), status_code=409)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to delete drawer %s", drawer_id)
        return internal_error(str(exc))

    return success_response({})


@admin_bp.route("/api/pages/<path:route>", methods=["PUT"])
@admin_required
def api_update_page(route: str):
    """API: Update page status/name/drawer assignment/order."""
    data = request.get_json(silent=True) or {}
    updatable_fields = {"status", "name", "drawer_id", "order"}
    if not any(field in data for field in updatable_fields):
        return validation_error("No page fields to update")

    # Ensure route starts with /
    if not route.startswith("/"):
        route = "/" + route

    status = data.get("status")
    if "status" in data and status not in ("released", "dev"):
        return validation_error("Invalid status")
    if "status" not in data:
        status = get_page_status(route)
        if status is None:
            return validation_error("Status is required for unregistered pages")

    update_kwargs: dict[str, Any] = {}
    if "name" in data:
        update_kwargs["name"] = data.get("name")
    if "drawer_id" in data:
        update_kwargs["drawer_id"] = data.get("drawer_id")
    if "order" in data:
        update_kwargs["order"] = data.get("order")

    try:
        set_page_status(route, status, **update_kwargs)
        return success_response({})
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception as e:
        return internal_error(str(e))


@admin_bp.route("/api/analytics/recalculate", methods=["POST"])
@admin_required
def recalculate_anomaly_detection():
    """Manually trigger anomaly detection recalculation."""
    try:
        from mes_dashboard.services.anomaly_detection_scheduler import trigger_recalculation

        result = trigger_recalculation()
        return success_response(result.get("data", {}), meta=result.get("meta", {}))
    except Exception as exc:
        return internal_error(f"Anomaly recalculation failed: {exc}")
