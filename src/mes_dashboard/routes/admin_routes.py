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

from flask import Blueprint, current_app, g, jsonify, render_template, request, send_from_directory

from mes_dashboard.core.permissions import admin_required
from mes_dashboard.core.response import error_response, TOO_MANY_REQUESTS
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
    """Performance monitoring dashboard (Vue SPA)."""
    dist_dir = os.path.join(current_app.static_folder or "", "dist")
    return send_from_directory(dist_dir, "admin-performance.html")


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

    return jsonify({
        "success": True,
        "data": {
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
        }
    })


@admin_bp.route("/api/metrics", methods=["GET"])
@admin_required
def api_metrics():
    """API: Get performance metrics for dashboard."""
    from mes_dashboard.core.metrics import get_metrics_summary, get_query_metrics

    summary = get_metrics_summary()
    metrics = get_query_metrics()

    return jsonify({
        "success": True,
        "data": {
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
        }
    })


@admin_bp.route("/api/logs", methods=["GET"])
@admin_required
def api_logs():
    """API: Get recent logs from SQLite log store."""
    from mes_dashboard.core.log_store import get_log_store, LOG_STORE_ENABLED

    if not LOG_STORE_ENABLED:
        return jsonify({
            "success": True,
            "data": {
                "logs": [],
                "enabled": False,
                "total": 0
            }
        })

    # Query parameters
    level = request.args.get("level")
    q = request.args.get("q")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    since = request.args.get("since")

    log_store = get_log_store()

    # Get total count for pagination
    total = log_store.count_logs(level=level, q=q, since=since)

    # Get paginated logs
    logs = log_store.query_logs(
        level=level,
        q=q,
        limit=min(limit, 100),  # Cap at 100 per page
        offset=offset,
        since=since
    )

    return jsonify({
        "success": True,
        "data": {
            "logs": logs,
            "count": len(logs),
            "total": total,
            "enabled": True,
            "stats": log_store.get_stats()
        }
    })


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
                    "reject_dataset", "meta", "lock", "scrap_exclusion",
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

    # ---- Pareto materialization telemetry ----
    pareto_materialization = None
    try:
        from mes_dashboard.services.reject_pareto_materialized import get_telemetry
        pareto_materialization = get_telemetry()
    except Exception as exc:
        logger.warning("Failed to collect pareto materialization telemetry: %s", exc)
        pareto_materialization = {"error": str(exc)}

    return jsonify({
        "success": True,
        "data": {
            "redis": redis_detail,
            "process_caches": process_caches,
            "route_cache": route_cache,
            "db_pool": db_pool,
            "direct_connections": direct_connections,
            "pareto_materialization": pareto_materialization,
        },
    })


@admin_bp.route("/api/performance-history", methods=["GET"])
@admin_required
def api_performance_history():
    """API: Get historical metrics snapshots for trend charts."""
    from mes_dashboard.core.metrics_history import get_metrics_history_store

    minutes = request.args.get("minutes", 30, type=int)
    minutes = max(1, min(minutes, 180))
    store = get_metrics_history_store()
    snapshots = store.query_snapshots(minutes=minutes)
    return jsonify({
        "success": True,
        "data": {
            "snapshots": snapshots,
            "count": len(snapshots),
        },
    })


@admin_bp.route("/api/logs/cleanup", methods=["POST"])
@admin_required
def api_logs_cleanup():
    """API: Manually trigger log cleanup.

    Supports optional parameters:
    - older_than_days: Delete logs older than N days (default: use configured retention)
    - keep_count: Keep only the most recent N logs (optional)
    """
    from mes_dashboard.core.log_store import get_log_store, LOG_STORE_ENABLED

    if not LOG_STORE_ENABLED:
        return jsonify({
            "success": False,
            "error": "Log store is disabled"
        }), 400

    log_store = get_log_store()

    # Get current stats before cleanup
    stats_before = log_store.get_stats()

    # Perform cleanup
    deleted = log_store.cleanup_old_logs()

    # Get stats after cleanup
    stats_after = log_store.get_stats()

    user = getattr(g, "username", "unknown")
    logger.info(f"Log cleanup triggered by {user}: deleted {deleted} entries")

    return jsonify({
        "success": True,
        "data": {
            "deleted": deleted,
            "before": {
                "count": stats_before.get("count", 0),
                "size_bytes": stats_before.get("size_bytes", 0)
            },
            "after": {
                "count": stats_after.get("count", 0),
                "size_bytes": stats_after.get("size_bytes", 0)
            }
        }
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

    return jsonify({
        "success": True,
        "data": {
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
        }
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
            process.create_time()
        ).isoformat()
    except ImportError:
        # psutil not installed, try /proc on Linux
        try:
            stat_path = f"/proc/{os.getpid()}/stat"
            with open(stat_path) as f:
                stat = f.read().split()
                # Field 22 is starttime in clock ticks since boot
                # This is a simplified fallback
                pass
        except Exception:
            pass
    except Exception:
        pass

    return jsonify({
        "success": True,
        "data": {
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
        }
    })


# ============================================================
# Page Management Routes
# ============================================================

@admin_bp.route("/pages")
@admin_required
def pages():
    """Page management interface."""
    return render_template("admin/pages.html")


@admin_bp.route("/api/pages", methods=["GET"])
@admin_required
def api_get_pages():
    """API: Get all page configurations."""
    return jsonify({"success": True, "pages": get_all_pages()})


@admin_bp.route("/api/drawers", methods=["GET"])
@admin_required
def api_get_drawers():
    """API: Get all drawer configurations."""
    return jsonify({"success": True, "drawers": get_all_drawers()})


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
        return jsonify({"success": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to create drawer")
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({"success": True, "drawer": drawer}), 201


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
        return jsonify({"success": False, "error": "No drawer fields to update"}), 400

    try:
        drawer = update_drawer(drawer_id, **updates)
    except DrawerNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except DrawerConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to update drawer %s", drawer_id)
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({"success": True, "drawer": drawer})


@admin_bp.route("/api/drawers/<drawer_id>", methods=["DELETE"])
@admin_required
def api_delete_drawer(drawer_id: str):
    """API: Delete a drawer if no pages are assigned to it."""
    try:
        delete_drawer(drawer_id)
    except DrawerNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except DrawerConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Failed to delete drawer %s", drawer_id)
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({"success": True})


@admin_bp.route("/api/pages/<path:route>", methods=["PUT"])
@admin_required
def api_update_page(route: str):
    """API: Update page status/name/drawer assignment/order."""
    data = request.get_json(silent=True) or {}
    updatable_fields = {"status", "name", "drawer_id", "order"}
    if not any(field in data for field in updatable_fields):
        return jsonify({"success": False, "error": "No page fields to update"}), 400

    # Ensure route starts with /
    if not route.startswith("/"):
        route = "/" + route

    status = data.get("status")
    if "status" in data and status not in ("released", "dev"):
        return jsonify({"success": False, "error": "Invalid status"}), 400
    if "status" not in data:
        status = get_page_status(route)
        if status is None:
            return jsonify({
                "success": False,
                "error": "Status is required for unregistered pages",
            }), 400

    update_kwargs: dict[str, Any] = {}
    if "name" in data:
        update_kwargs["name"] = data.get("name")
    if "drawer_id" in data:
        update_kwargs["drawer_id"] = data.get("drawer_id")
    if "order" in data:
        update_kwargs["order"] = data.get("order")

    try:
        set_page_status(route, status, **update_kwargs)
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
