# -*- coding: utf-8 -*-
"""Health check endpoints for MES Dashboard.

Provides /health and /health/deep endpoints for monitoring service status.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, make_response

from mes_dashboard.core.database import (
    get_engine,
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
)
from sqlalchemy import text

logger = logging.getLogger('mes_dashboard.health')

health_bp = Blueprint('health', __name__)

# ============================================================
# Warning Thresholds
# ============================================================

DB_LATENCY_WARNING_MS = 100  # Database latency > 100ms is slow
CACHE_STALE_MINUTES = 2  # Cache update > 2 minutes is stale


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


def check_database() -> tuple[str, str | None]:
    """Check database connectivity.

    Returns:
        Tuple of (status, error_message).
        status is 'ok' or 'error'.
    """
    try:
        engine = get_engine()
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
        'updated_at': get_cache_updated_at()
    }
    try:
        from mes_dashboard.services.wip_service import get_wip_search_index_status
        status['derived_search_index'] = get_wip_search_index_status()
    except Exception:
        status['derived_search_index'] = {}
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


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint.

    Returns:
        - 200 OK: All services healthy or degraded (Redis down but DB ok)
        - 503 Service Unavailable: Database unhealthy
    """
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
    recommendation = build_recovery_recommendation(
        degraded_reason=degraded_reason,
        pool_saturation=pool_saturation,
        circuit_state=circuit_breaker.get('state'),
        restart_churn_exceeded=False,
        cooldown_active=False,
    )

    # Check equipment status cache
    equipment_status_cache = get_equipment_status_cache_status()
    if equipment_status_cache.get('enabled') and not equipment_status_cache.get('loaded'):
        warnings.append("Equipment status cache not loaded")

    # Check workcenter mapping
    workcenter_mapping = get_workcenter_mapping_status()

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
            'recovery_recommendation': recommendation,
        },
        'cache': get_cache_status(),
        'route_cache': route_cache,
        'resource_cache': resource_cache,
        'equipment_status_cache': equipment_status_cache,
        'workcenter_mapping': workcenter_mapping,
    }

    if errors:
        response['errors'] = errors
    if warnings:
        response['warnings'] = warnings

    # Add no-cache headers to prevent browser caching
    resp = make_response(jsonify(response), http_code)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


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

    # Require admin authentication - redirect to login for consistency
    if not is_admin_logged_in():
        return redirect(url_for("auth.login", next=request.url))

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
        restart_churn_exceeded=False,
        cooldown_active=False,
    )

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

    response = {
        'status': status,
        'degraded_reason': degraded_reason,
        'resilience': {
            'thresholds': thresholds,
            'recovery_recommendation': recommendation,
        },
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
                'sys_date': cache_status.get('sys_date')
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
        }
    }

    if warnings:
        response['warnings'] = warnings

    # Add no-cache headers
    resp = make_response(jsonify(response), http_code)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp
