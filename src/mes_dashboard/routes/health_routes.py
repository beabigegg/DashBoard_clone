# -*- coding: utf-8 -*-
"""Health check endpoints for MES Dashboard.

Provides /health endpoint for monitoring service status.
"""

from __future__ import annotations

import logging
from flask import Blueprint, jsonify

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
    """Get current cache status.

    Returns:
        Dict with cache status information.
    """
    return {
        'enabled': REDIS_ENABLED,
        'sys_date': get_cached_sys_date(),
        'updated_at': get_cache_updated_at()
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

    response = {
        'status': status,
        'services': services,
        'cache': get_cache_status()
    }

    if errors:
        response['errors'] = errors
    if warnings:
        response['warnings'] = warnings

    return jsonify(response), http_code
