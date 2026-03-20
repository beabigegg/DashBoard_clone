# -*- coding: utf-8 -*-
"""Health check endpoints for MES Dashboard.

Provides /health and /health/deep endpoints for monitoring service status.

CONTRACT EXCEPTION — DO NOT ENVELOPE
-------------------------------------
Endpoints in this module (/health, /health/deep, /health/frontend-shell) are
classified as `health-exception` in the API contract unification governance.
They intentionally maintain a top-level response structure (not wrapped in
`{ success, data, meta }`) because:
  - External monitoring systems and the portal-shell health UI depend on the
    stable top-level fields (e.g. `status`, `services`, `checks`).
  - Wrapping into success_response() would break these consumers silently.

Do NOT apply success_response() or error_response() to these routes.
This exception is permanent unless a coordinated migration with all consumers
is planned and executed under a separate change.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, current_app, jsonify, make_response

from mes_dashboard.core.database import (
    get_health_engine,
    get_pool_runtime_config,
    get_pool_status,
)
from mes_dashboard.core.redis_client import (
    get_redis_client,
    redis_available,
    REDIS_ENABLED
)
from mes_dashboard.core.cache import (
    get_cached_sys_date,
    get_cache_updated_at
)
from mes_dashboard.core.resilience import (
    build_recovery_recommendation,
    get_resilience_thresholds,
    summarize_restart_history,
)
from mes_dashboard.core.runtime_contract import build_runtime_contract_diagnostics
from mes_dashboard.core.worker_recovery_policy import (
    evaluate_worker_recovery_state,
    extract_last_requested_at,
    extract_restart_history,
    get_worker_recovery_policy_config,
    load_restart_state,
)
from sqlalchemy import text

logger = logging.getLogger('mes_dashboard.health')

health_bp = Blueprint('health', __name__)

# ============================================================
# Warning Thresholds
# ============================================================

DB_LATENCY_WARNING_MS = 100  # Database latency > 100ms is slow
CACHE_STALE_MINUTES = 2  # Cache update > 2 minutes is stale
HEALTH_MEMO_TTL_SECONDS = int(os.getenv("HEALTH_MEMO_TTL_SECONDS", "5"))

_HEALTH_MEMO_LOCK = threading.Lock()
_HEALTH_MEMO: dict[str, dict | None] = {
    "health": None,
    "deep": None,
}


def _health_memo_enabled() -> bool:
    if HEALTH_MEMO_TTL_SECONDS <= 0:
        return False
    if current_app.testing or bool(current_app.config.get("TESTING")):
        return False
    return True


def _get_health_memo(cache_key: str) -> tuple[dict, int] | None:
    if not _health_memo_enabled():
        return None
    now = time.time()
    with _HEALTH_MEMO_LOCK:
        entry = _HEALTH_MEMO.get(cache_key)
        if not entry:
            return None
        if now - float(entry.get("ts", 0.0)) > HEALTH_MEMO_TTL_SECONDS:
            _HEALTH_MEMO[cache_key] = None
            return None
        return entry["payload"], int(entry["status"])


def _set_health_memo(cache_key: str, payload: dict, status_code: int) -> None:
    if not _health_memo_enabled():
        return
    with _HEALTH_MEMO_LOCK:
        _HEALTH_MEMO[cache_key] = {
            "ts": time.time(),
            "payload": payload,
            "status": int(status_code),
        }


def _build_health_response(payload: dict, status_code: int):
    """Build JSON response with explicit no-cache headers."""
    resp = make_response(jsonify(payload), status_code)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _reset_health_memo_for_tests() -> None:
    with _HEALTH_MEMO_LOCK:
        _HEALTH_MEMO["health"] = None
        _HEALTH_MEMO["deep"] = None


def _classify_degraded_reason(
    db_status: str,
    redis_status: str,
    route_cache_degraded: bool,
    circuit_breaker_state: str | None = None,
    pool_saturation: float | None = None,
) -> str | None:
    if db_status == 'error':
        return 'database_unreachable'
    if circuit_breaker_state == 'OPEN':
        return 'circuit_breaker_open'
    if pool_saturation is not None and pool_saturation >= 1.0:
        return 'db_pool_saturated'
    if redis_status == 'error':
        return 'redis_unavailable'
    if route_cache_degraded:
        return 'route_cache_degraded'
    return None


def _build_resilience_alerts(
    *,
    pool_saturation: float | None,
    circuit_state: str | None,
    route_cache_degraded: bool,
    restart_churn_exceeded: bool,
    restart_blocked: bool,
    thresholds: dict,
) -> dict:
    saturation = float(pool_saturation or 0.0)
    warning = float(thresholds.get("pool_saturation_warning", 0.9))
    critical = float(thresholds.get("pool_saturation_critical", 1.0))
    return {
        "pool_warning": saturation >= warning,
        "pool_critical": saturation >= critical,
        "circuit_open": circuit_state == "OPEN",
        "route_cache_degraded": bool(route_cache_degraded),
        "restart_churn_exceeded": bool(restart_churn_exceeded),
        "restart_blocked": bool(restart_blocked),
    }


def get_worker_recovery_status() -> dict:
    """Build worker recovery policy status for health/admin telemetry."""
    state = load_restart_state()
    history = extract_restart_history(state)
    policy_state = evaluate_worker_recovery_state(
        history,
        last_requested_at=extract_last_requested_at(state),
    )
    churn = summarize_restart_history(
        history,
        window_seconds=int(policy_state.get("window_seconds") or 600),
        threshold=int(policy_state.get("churn_threshold") or 3),
    )
    return {
        "policy_state": policy_state,
        "restart_churn": churn,
        "policy_config": get_worker_recovery_policy_config(),
    }


def check_database() -> tuple[str, str | None]:
    """Check database connectivity.

    Returns:
        Tuple of (status, error_message).
        status is 'ok' or 'error'.
    """
    try:
        engine = get_health_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM DUAL"))
        return 'ok', None
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return 'error', str(e)


def check_redis() -> tuple[str, str | None]:
    """Check Redis connectivity.

    Returns:
        Tuple of (status, error_message).
        status is 'ok', 'error', or 'disabled'.
    """
    if not REDIS_ENABLED:
        return 'disabled', None

    try:
        client = get_redis_client()
        if client is None:
            return 'error', 'Failed to get Redis client'

        client.ping()
        return 'ok', None
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return 'error', str(e)


def get_cache_status() -> dict:
    """Get current WIP cache status.

    Returns:
        Dict with WIP cache status information.
    """
    status = {
        'enabled': REDIS_ENABLED,
        'sys_date': get_cached_sys_date(),
        'updated_at': get_cache_updated_at(),
        'derived_search_index': {},
        'derived_frame_snapshot': {},
        'index_metrics': {},
        'memory': {},
    }
    try:
        from mes_dashboard.services.wip_service import get_wip_search_index_status
        derived = get_wip_search_index_status()
        status['derived_search_index'] = derived.get('derived_search_index', {})
        status['derived_frame_snapshot'] = derived.get('derived_frame_snapshot', {})
        status['index_metrics'] = derived.get('metrics', {})
        status['memory'] = derived.get('memory', {})
    except Exception:
        pass
    return status


def get_route_cache_status() -> dict:
    """Get route-cache telemetry for operational diagnostics."""
    from flask import current_app

    cache_backend = current_app.extensions.get("cache")
    if cache_backend is None:
        return {
            'mode': 'none',
            'degraded': False,
            'available': False,
        }

    telemetry_fn = getattr(cache_backend, "telemetry", None)
    if callable(telemetry_fn):
        telemetry = telemetry_fn()
        telemetry['available'] = True
        return telemetry

    return {
        'mode': cache_backend.__class__.__name__,
        'degraded': False,
        'available': True,
    }


def get_resource_cache_status() -> dict:
    """Get current resource cache status.

    Returns:
        Dict with resource cache status information.
    """
    from mes_dashboard.services.resource_cache import (
        get_cache_status as get_res_cache_status,
        RESOURCE_CACHE_ENABLED,
    )

    if not RESOURCE_CACHE_ENABLED:
        return {'enabled': False}

    return get_res_cache_status()


def get_equipment_status_cache_status() -> dict:
    """Get current realtime equipment status cache status.

    Returns:
        Dict with equipment status cache information.
    """
    from flask import current_app
    from mes_dashboard.services.realtime_equipment_cache import (
        get_equipment_status_cache_status as get_eq_cache_status,
    )

    enabled = current_app.config.get('REALTIME_EQUIPMENT_CACHE_ENABLED', True)
    if not enabled:
        return {'enabled': False}

    return get_eq_cache_status()


def get_workcenter_mapping_status() -> dict:
    """Get current workcenter mapping cache status.

    Returns:
        Dict with workcenter mapping cache information.
    """
    from mes_dashboard.services.filter_cache import get_cache_status

    status = get_cache_status()
    return {
        'loaded': status.get('loaded', False),
        'workcenter_count': status.get('workcenter_mapping_count', 0),
        'group_count': status.get('workcenter_groups_count', 0),
    }


def get_portal_shell_asset_status() -> dict:
    """Validate portal-shell HTML/CSS/JS asset availability and references."""
    dist_dir = Path(current_app.static_folder or "") / "dist"
    top_level_html = dist_dir / "portal-shell.html"
    nested_html = dist_dir / "src" / "portal-shell" / "index.html"
    js_file = dist_dir / "portal-shell.js"
    shell_css_file = dist_dir / "portal-shell.css"
    tailwind_css_file = dist_dir / "tailwind.css"

    html_file: Path | None = None
    if top_level_html.exists():
        html_file = top_level_html
    elif nested_html.exists():
        html_file = nested_html

    checks = {
        "portal_shell_html": {
            "exists": html_file is not None,
            "path": str(html_file) if html_file is not None else None,
            "source": "top-level" if html_file == top_level_html else "nested" if html_file == nested_html else None,
        },
        "portal_shell_js": {
            "exists": js_file.exists(),
            "path": str(js_file),
        },
        "portal_shell_css": {
            "exists": shell_css_file.exists(),
            "path": str(shell_css_file),
        },
        "tailwind_css": {
            "exists": tailwind_css_file.exists(),
            "path": str(tailwind_css_file),
        },
        "html_references": {
            "portal_shell_js": False,
            "portal_shell_css": False,
            "tailwind_css": False,
        },
    }

    errors: list[str] = []
    warnings: list[str] = []

    if html_file is None:
        errors.append("portal-shell HTML not found (portal-shell.html or src/portal-shell/index.html)")
    else:
        try:
            html_content = html_file.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"failed to read shell html: {exc}")
        else:
            checks["html_references"]["portal_shell_js"] = "/static/dist/portal-shell.js" in html_content
            checks["html_references"]["portal_shell_css"] = "/static/dist/portal-shell.css" in html_content
            checks["html_references"]["tailwind_css"] = "/static/dist/tailwind.css" in html_content

            if not checks["html_references"]["portal_shell_js"]:
                errors.append("shell html missing reference: /static/dist/portal-shell.js")
            if not checks["html_references"]["portal_shell_css"]:
                errors.append("shell html missing reference: /static/dist/portal-shell.css")
            if not checks["html_references"]["tailwind_css"]:
                errors.append("shell html missing reference: /static/dist/tailwind.css")

    if not checks["portal_shell_js"]["exists"]:
        errors.append("asset missing: static/dist/portal-shell.js")
    if not checks["portal_shell_css"]["exists"]:
        errors.append("asset missing: static/dist/portal-shell.css")
    if not checks["tailwind_css"]["exists"]:
        errors.append("asset missing: static/dist/tailwind.css")

    if checks["portal_shell_html"]["source"] == "nested":
        warnings.append("using nested shell html source (dist/src/portal-shell/index.html)")

    healthy = len(errors) == 0
    return {
        "status": "healthy" if healthy else "unhealthy",
        "route": "/portal-shell",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "http_code": 200 if healthy else 503,
    }


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint.

    Returns:
        - 200 OK: All services healthy or degraded (Redis down but DB ok)
        - 503 Service Unavailable: Database unhealthy
    """
    cached = _get_health_memo("health")
    if cached is not None:
        payload, status_code = cached
        return _build_health_response(payload, status_code)

    from mes_dashboard.core.circuit_breaker import get_circuit_breaker_status

    db_status, db_error = check_database()
    redis_status, redis_error = check_redis()
    circuit_breaker = get_circuit_breaker_status()

    services = {
        'database': db_status,
        'redis': redis_status
    }
    route_cache = get_route_cache_status()
    pool_runtime = get_pool_runtime_config()
    try:
        pool_status = get_pool_status()
    except Exception:
        pool_status = None

    errors = []
    warnings = []
    pool_saturation = (pool_status or {}).get('saturation')
    degraded_reason = _classify_degraded_reason(
        db_status=db_status,
        redis_status=redis_status,
        route_cache_degraded=bool(route_cache.get('degraded')),
        circuit_breaker_state=circuit_breaker.get('state'),
        pool_saturation=pool_saturation,
    )

    # Determine overall status
    if db_status == 'error':
        status = 'unhealthy'
        http_code = 503
        if db_error:
            errors.append(f"Database connection failed: {db_error}")
    elif redis_status == 'error':
        # Redis down is degraded, not unhealthy (fallback available)
        status = 'degraded'
        http_code = 200
        warnings.append("Redis unavailable, running in fallback mode")
    elif circuit_breaker.get('state') == 'OPEN':
        status = 'degraded'
        http_code = 200
        warnings.append("Circuit breaker is OPEN")
    else:
        status = 'healthy'
        http_code = 200

    # Check resource cache status
    resource_cache = get_resource_cache_status()
    if resource_cache.get('enabled') and not resource_cache.get('loaded'):
        warnings.append("Resource cache not loaded")

    if route_cache.get('degraded'):
        warnings.append("Route cache is running in degraded L1-only mode")

    if pool_status is not None:
        saturation = pool_saturation if pool_saturation is not None else 0.0
        if saturation >= 0.9:
            warnings.append(f"Database pool saturation is high ({saturation:.0%})")

    thresholds = get_resilience_thresholds()
    worker_recovery = get_worker_recovery_status()
    policy_state = worker_recovery.get("policy_state", {})
    restart_churn = worker_recovery.get("restart_churn", {})
    recommendation = build_recovery_recommendation(
        degraded_reason=degraded_reason,
        pool_saturation=pool_saturation,
        circuit_state=circuit_breaker.get('state'),
        restart_churn_exceeded=bool(restart_churn.get("exceeded")),
        cooldown_active=bool(policy_state.get("cooldown")),
    )
    alerts = _build_resilience_alerts(
        pool_saturation=pool_saturation,
        circuit_state=circuit_breaker.get("state"),
        route_cache_degraded=bool(route_cache.get("degraded")),
        restart_churn_exceeded=bool(restart_churn.get("exceeded")),
        restart_blocked=bool(policy_state.get("blocked")),
        thresholds=thresholds,
    )
    runtime_contract = build_runtime_contract_diagnostics(strict=False)

    # Check worker memory pressure
    system_memory: dict = {}
    try:
        from mes_dashboard.core.worker_memory_guard import get_memory_guard_telemetry
        mem_guard = get_memory_guard_telemetry()
        if mem_guard and mem_guard.get("enabled"):
            mem_level = mem_guard.get("level", "normal")
            mem_pct = mem_guard.get("rss_pct", 0)
            if mem_level == "evict" or mem_level == "restart":
                warnings.append(f"Worker 記憶體壓力偏高（{mem_pct:.0f}%），已自動清空快取")
                status = "degraded"
            elif mem_level == "warn":
                warnings.append(f"Worker 記憶體使用偏高（{mem_pct:.0f}%）")
    except Exception:
        pass

    try:
        import psutil
        vm = psutil.virtual_memory()
        sys_used_pct = vm.percent
        sys_pressure = "critical" if sys_used_pct > 90 else ("high" if sys_used_pct > 80 else "normal")
        system_memory = {
            "total_mb": round(vm.total / (1024 * 1024), 0),
            "available_mb": round(vm.available / (1024 * 1024), 0),
            "used_pct": round(sys_used_pct, 1),
            "pressure": sys_pressure,
        }
    except Exception as exc:
        system_memory = {"error": str(exc)}

    # Check equipment status cache
    equipment_status_cache = get_equipment_status_cache_status()
    if equipment_status_cache.get('enabled') and not equipment_status_cache.get('loaded'):
        warnings.append("Equipment status cache not loaded")

    # Check workcenter mapping
    workcenter_mapping = get_workcenter_mapping_status()

    # Async workers (RQ) status — on-demand, no daemon
    async_workers: dict = {}
    try:
        from mes_dashboard.services.rq_monitor_service import get_rq_monitor_summary
        async_workers = get_rq_monitor_summary()
        ws = async_workers.get("workers", {}).get("summary", {})
        if ws.get("total", 0) == 0 and async_workers.get("rq_available") is False:
            warnings.append("RQ Worker 離線，非同步查詢不可用")
    except Exception:
        pass

    response = {
        'status': status,
        'services': services,
        'degraded_reason': degraded_reason,
        'circuit_breaker': circuit_breaker,
        'database_pool': {
            'runtime': pool_runtime,
            'state': pool_status,
        },
        'resilience': {
            'thresholds': thresholds,
            'alerts': alerts,
            'policy_state': {
                'state': policy_state.get("state"),
                'allowed': policy_state.get("allowed"),
                'cooldown': policy_state.get("cooldown"),
                'blocked': policy_state.get("blocked"),
                'cooldown_remaining_seconds': policy_state.get("cooldown_remaining_seconds"),
            },
            'restart_churn': restart_churn,
            'recovery_recommendation': recommendation,
        },
        'runtime_contract': runtime_contract,
        'cache': get_cache_status(),
        'route_cache': route_cache,
        'resource_cache': resource_cache,
        'equipment_status_cache': equipment_status_cache,
        'workcenter_mapping': workcenter_mapping,
        'system_memory': system_memory,
        'async_workers': async_workers,
    }

    if errors:
        response['errors'] = errors
    if warnings:
        response['warnings'] = warnings

    _set_health_memo("health", response, http_code)
    return _build_health_response(response, http_code)


@health_bp.route('/health/deep', methods=['GET'])
def deep_health_check():
    """Deep health check endpoint with detailed metrics.

    Requires admin authentication.

    Returns:
        - 200 OK with detailed health information
        - 503 if database is unhealthy
    """
    from mes_dashboard.core.permissions import is_admin_logged_in
    from mes_dashboard.core.circuit_breaker import get_circuit_breaker_status
    from mes_dashboard.core.metrics import get_metrics_summary
    from flask import redirect, url_for, request

    # Require admin authentication - return JSON error for API consistency
    if not is_admin_logged_in():
        from flask import jsonify
        return jsonify({"error": "請先登入管理員帳號", "login_required": True}), 401

    cached = _get_health_memo("deep")
    if cached is not None:
        payload, status_code = cached
        return _build_health_response(payload, status_code)

    # Check database with latency measurement
    db_start = time.time()
    db_status, db_error = check_database()
    db_latency_ms = round((time.time() - db_start) * 1000, 2)

    # Check Redis with latency measurement
    redis_latency_ms = None
    if REDIS_ENABLED:
        redis_start = time.time()
        redis_status, redis_error = check_redis()
        redis_latency_ms = round((time.time() - redis_start) * 1000, 2)
    else:
        redis_status = 'disabled'

    # Get circuit breaker status
    circuit_breaker = get_circuit_breaker_status()
    pool_runtime = get_pool_runtime_config()

    # Get performance metrics
    metrics = get_metrics_summary()

    # Get cache freshness
    cache_status = get_cache_status()
    route_cache = get_route_cache_status()
    cache_updated_at = cache_status.get('updated_at')
    cache_is_stale = False
    if cache_updated_at:
        try:
            updated_time = datetime.fromisoformat(cache_updated_at)
            cache_is_stale = datetime.now() - updated_time > timedelta(minutes=CACHE_STALE_MINUTES)
        except (ValueError, TypeError):
            pass

    # Get connection pool status
    try:
        pool_status = get_pool_status()
    except Exception:
        pool_status = None

    # Determine overall status with thresholds
    warnings = []
    status = 'healthy'
    http_code = 200

    if db_status == 'error':
        status = 'unhealthy'
        http_code = 503
    elif circuit_breaker.get('state') == 'OPEN':
        status = 'degraded'
        warnings.append("Circuit breaker is OPEN")
    elif redis_status == 'error':
        status = 'degraded'
        warnings.append("Redis unavailable")

    if route_cache.get('degraded'):
        status = 'degraded'
        warnings.append("Route cache degraded (L1-only fallback)")

    pool_saturation = (pool_status or {}).get('saturation')
    if pool_saturation is not None and pool_saturation >= 0.9:
        warnings.append(f"Database pool saturation is high ({pool_saturation:.0%})")

    thresholds = get_resilience_thresholds()
    worker_recovery = get_worker_recovery_status()
    policy_state = worker_recovery.get("policy_state", {})
    restart_churn = worker_recovery.get("restart_churn", {})
    degraded_reason = _classify_degraded_reason(
        db_status=db_status,
        redis_status=redis_status,
        route_cache_degraded=bool(route_cache.get('degraded')),
        circuit_breaker_state=circuit_breaker.get('state'),
        pool_saturation=pool_saturation,
    )
    recommendation = build_recovery_recommendation(
        degraded_reason=degraded_reason,
        pool_saturation=pool_saturation,
        circuit_state=circuit_breaker.get('state'),
        restart_churn_exceeded=bool(restart_churn.get("exceeded")),
        cooldown_active=bool(policy_state.get("cooldown")),
    )
    alerts = _build_resilience_alerts(
        pool_saturation=pool_saturation,
        circuit_state=circuit_breaker.get("state"),
        route_cache_degraded=bool(route_cache.get("degraded")),
        restart_churn_exceeded=bool(restart_churn.get("exceeded")),
        restart_blocked=bool(policy_state.get("blocked")),
        thresholds=thresholds,
    )
    runtime_contract = build_runtime_contract_diagnostics(strict=False)

    # Check latency thresholds
    db_latency_status = 'healthy'
    if db_latency_ms > DB_LATENCY_WARNING_MS:
        db_latency_status = 'slow'
        warnings.append(f"Database latency is slow ({db_latency_ms}ms)")

    # Check cache staleness
    cache_freshness = 'fresh'
    if cache_is_stale:
        cache_freshness = 'stale'
        warnings.append("Cache data may be stale")

    deep_system_memory: dict = {}
    try:
        import psutil
        vm = psutil.virtual_memory()
        sys_used_pct = vm.percent
        sys_pressure = "critical" if sys_used_pct > 90 else ("high" if sys_used_pct > 80 else "normal")
        deep_system_memory = {
            "total_mb": round(vm.total / (1024 * 1024), 0),
            "available_mb": round(vm.available / (1024 * 1024), 0),
            "used_pct": round(sys_used_pct, 1),
            "pressure": sys_pressure,
        }
    except Exception as exc:
        deep_system_memory = {"error": str(exc)}

    # Async workers (RQ) status
    deep_async_workers: dict = {}
    try:
        from mes_dashboard.services.rq_monitor_service import get_rq_monitor_summary
        deep_async_workers = get_rq_monitor_summary()
        dw_summary = deep_async_workers.get("workers", {}).get("summary", {})
        if dw_summary.get("total", 0) == 0 and deep_async_workers.get("rq_available") is False:
            warnings.append("RQ Worker 離線，非同步查詢不可用")
    except Exception:
        pass

    response = {
        'status': status,
        'degraded_reason': degraded_reason,
        'resilience': {
            'thresholds': thresholds,
            'alerts': alerts,
            'policy_state': {
                'state': policy_state.get("state"),
                'allowed': policy_state.get("allowed"),
                'cooldown': policy_state.get("cooldown"),
                'blocked': policy_state.get("blocked"),
                'cooldown_remaining_seconds': policy_state.get("cooldown_remaining_seconds"),
            },
            'restart_churn': restart_churn,
            'recovery_recommendation': recommendation,
        },
        'runtime_contract': runtime_contract,
        'checks': {
            'database': {
                'status': db_latency_status if db_status == 'ok' else 'error',
                'latency_ms': db_latency_ms,
                'pool': pool_status,
                'pool_runtime': pool_runtime,
            },
            'redis': {
                'status': 'healthy' if redis_status == 'ok' else redis_status,
                'latency_ms': redis_latency_ms
            },
            'circuit_breaker': circuit_breaker,
            'cache': {
                'freshness': cache_freshness,
                'updated_at': cache_updated_at,
                'sys_date': cache_status.get('sys_date'),
                'index_metrics': cache_status.get('index_metrics', {}),
                'memory': cache_status.get('memory', {}),
            },
            'route_cache': route_cache
        },
        'metrics': {
            'query_p50_ms': metrics.get('p50_ms'),
            'query_p95_ms': metrics.get('p95_ms'),
            'query_p99_ms': metrics.get('p99_ms'),
            'query_count': metrics.get('count'),
            'slow_query_count': metrics.get('slow_count'),
            'slow_query_rate': metrics.get('slow_rate'),
            'worker_pid': metrics.get('worker_pid')
        },
        'system_memory': deep_system_memory,
        'async_workers': deep_async_workers,
    }

    if warnings:
        response['warnings'] = warnings

    _set_health_memo("deep", response, http_code)
    return _build_health_response(response, http_code)


@health_bp.route('/health/frontend-shell', methods=['GET'])
def frontend_shell_health_check():
    """Frontend shell health endpoint for CSS/JS rendering readiness."""
    result = get_portal_shell_asset_status()
    http_code = int(result.pop("http_code", 500))
    errors = list(result.get("errors", []))
    warnings = list(result.get("warnings", []))
    summary = {
        "status": result.get("status", "unhealthy"),
        "route": result.get("route", "/portal-shell"),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    detail = {
        "checks": result.get("checks", {}),
        "errors": errors,
        "warnings": warnings,
    }
    response = {
        **result,
        "summary": summary,
        "detail": detail,
    }
    return _build_health_response(response, http_code)
