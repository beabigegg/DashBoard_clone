# -*- coding: utf-8 -*-
"""Admin routes for page management and performance monitoring."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, g, jsonify, render_template, request

from mes_dashboard.core.permissions import admin_required
from mes_dashboard.core.response import error_response, TOO_MANY_REQUESTS
from mes_dashboard.services.page_registry import get_all_pages, set_page_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
logger = logging.getLogger("mes_dashboard.admin")

# ============================================================
# Worker Restart Configuration
# ============================================================

RESTART_FLAG_PATH = os.getenv(
    "WATCHDOG_RESTART_FLAG",
    "/tmp/mes_dashboard_restart.flag"
)
RESTART_STATE_PATH = os.getenv(
    "WATCHDOG_STATE_FILE",
    "/tmp/mes_dashboard_restart_state.json"
)
RESTART_COOLDOWN_SECONDS = int(os.getenv("WORKER_RESTART_COOLDOWN", "60"))

# Track last restart request time (in-memory for this worker)
_last_restart_request: float = 0.0


# ============================================================
# Performance Monitoring Routes
# ============================================================

@admin_bp.route("/performance")
@admin_required
def performance():
    """Performance monitoring dashboard."""
    return render_template("admin/performance.html")


@admin_bp.route("/api/system-status", methods=["GET"])
@admin_required
def api_system_status():
    """API: Get system status for performance dashboard."""
    from mes_dashboard.core.redis_client import redis_available, REDIS_ENABLED
    from mes_dashboard.core.circuit_breaker import get_circuit_breaker_status
    from mes_dashboard.routes.health_routes import check_database, check_redis

    # Database status
    db_status, db_error = check_database()

    # Redis status
    redis_status = 'disabled'
    if REDIS_ENABLED:
        redis_status, _ = check_redis()

    # Circuit breaker status
    circuit_breaker = get_circuit_breaker_status()

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
    state_path = Path(RESTART_STATE_PATH)
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except (json.JSONDecodeError, IOError):
        return {}


def _check_restart_cooldown() -> tuple[bool, float]:
    """Check if restart is in cooldown.

    Returns:
        Tuple of (is_in_cooldown, remaining_seconds).
    """
    global _last_restart_request

    # Check in-memory cooldown first
    now = time.time()
    elapsed = now - _last_restart_request
    if elapsed < RESTART_COOLDOWN_SECONDS:
        return True, RESTART_COOLDOWN_SECONDS - elapsed

    # Check file-based state (for cross-worker coordination)
    state = _get_restart_state()
    last_restart = state.get("last_restart", {})
    requested_at = last_restart.get("requested_at")

    if requested_at:
        try:
            request_time = datetime.fromisoformat(requested_at).timestamp()
            elapsed = now - request_time
            if elapsed < RESTART_COOLDOWN_SECONDS:
                return True, RESTART_COOLDOWN_SECONDS - elapsed
        except (ValueError, TypeError):
            pass

    return False, 0.0


@admin_bp.route("/api/worker/restart", methods=["POST"])
@admin_required
def api_worker_restart():
    """API: Request worker restart.

    Writes a restart flag file that the watchdog process monitors.
    Enforces a 60-second cooldown between restart requests.
    """
    global _last_restart_request

    # Check cooldown
    in_cooldown, remaining = _check_restart_cooldown()
    if in_cooldown:
        return error_response(
            TOO_MANY_REQUESTS,
            f"Restart in cooldown. Please wait {int(remaining)} seconds.",
            status_code=429
        )

    # Get request metadata
    user = getattr(g, "username", "unknown")
    ip = request.remote_addr or "unknown"
    timestamp = datetime.now().isoformat()

    # Write restart flag file
    flag_path = Path(RESTART_FLAG_PATH)
    flag_data = {
        "user": user,
        "ip": ip,
        "timestamp": timestamp,
        "worker_pid": os.getpid()
    }

    try:
        flag_path.write_text(json.dumps(flag_data))
    except IOError as e:
        logger.error(f"Failed to write restart flag: {e}")
        return error_response(
            "RESTART_FAILED",
            f"Failed to request restart: {e}",
            status_code=500
        )

    # Update in-memory cooldown
    _last_restart_request = time.time()

    logger.info(
        f"Worker restart requested by {user} from {ip}"
    )

    return jsonify({
        "success": True,
        "data": {
            "message": "Restart requested. Workers will reload shortly.",
            "requested_by": user,
            "requested_at": timestamp
        }
    })


@admin_bp.route("/api/worker/status", methods=["GET"])
@admin_required
def api_worker_status():
    """API: Get worker status and restart information."""
    # Check cooldown
    in_cooldown, remaining = _check_restart_cooldown()

    # Get last restart info
    state = _get_restart_state()
    last_restart = state.get("last_restart", {})

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
            "cooldown": {
                "active": in_cooldown,
                "remaining_seconds": int(remaining) if in_cooldown else 0
            },
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


@admin_bp.route("/api/pages/<path:route>", methods=["PUT"])
@admin_required
def api_update_page(route: str):
    """API: Update page status."""
    data = request.get_json()
    status = data.get("status")
    name = data.get("name")

    if status not in ("released", "dev"):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    # Ensure route starts with /
    if not route.startswith("/"):
        route = "/" + route

    try:
        set_page_status(route, status, name)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
