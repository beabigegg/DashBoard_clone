# -*- coding: utf-8 -*-
"""Health check endpoints for MES Dashboard.

Provides /health endpoint for monitoring service status.
"""

from __future__ import annotations

import logging
from flask import Blueprint, jsonify, make_response

from mes_dashboard.core.database import get_engine
from mes_dashboard.core.redis_client import (
    get_redis_client,
    redis_available,
    REDIS_ENABLED
)
from mes_dashboard.core.cache import (
    get_cached_sys_date,
    get_cache_updated_at
)
from sqlalchemy import text

logger = logging.getLogger('mes_dashboard.health')

health_bp = Blueprint('health', __name__)


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
    return {
        'enabled': REDIS_ENABLED,
        'sys_date': get_cached_sys_date(),
        'updated_at': get_cache_updated_at()
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
    db_status, db_error = check_database()
    redis_status, redis_error = check_redis()

    services = {
        'database': db_status,
        'redis': redis_status
    }

    errors = []
    warnings = []

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
    else:
        status = 'healthy'
        http_code = 200

    # Check resource cache status
    resource_cache = get_resource_cache_status()
    if resource_cache.get('enabled') and not resource_cache.get('loaded'):
        warnings.append("Resource cache not loaded")

    # Check equipment status cache
    equipment_status_cache = get_equipment_status_cache_status()
    if equipment_status_cache.get('enabled') and not equipment_status_cache.get('loaded'):
        warnings.append("Equipment status cache not loaded")

    # Check workcenter mapping
    workcenter_mapping = get_workcenter_mapping_status()

    response = {
        'status': status,
        'services': services,
        'cache': get_cache_status(),
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
