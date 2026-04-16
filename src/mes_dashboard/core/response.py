# -*- coding: utf-8 -*-
"""Standard API response format utilities for MES Dashboard.

Provides consistent response envelope for all API endpoints.

## Helper Usage Guide

### Scenario → Helper mapping

| Scenario | Helper | HTTP status |
|----------|--------|-------------|
| Query/action success | `success_response(data)` | 200 |
| Invalid param/body | `validation_error(message)` | 400 |
| Resource not found | `not_found_error(message)` | 404 |
| Rate limit exceeded | `too_many_requests_error()` | 429 |
| DB connection down | `db_connection_error(details)` | 503 |
| DB query timeout | `db_query_timeout_error(details)` | 504 |
| Circuit breaker open | `circuit_breaker_error(details)` | 503 |
| DB pool exhausted | `pool_exhausted_error(details)` | 503 |
| Cache expired | `cache_expired_error(details)` | 410 |
| Cache miss (not yet loaded) | `cache_miss_error(details)` | 400 |
| Other server error | `internal_error(details)` | 500 |

### Contract exception endpoints (DO NOT use success_response on these)
- `/health`, `/health/deep`, `/health/frontend-shell` — keep top-level payload structure
- CSV/NDJSON/file download success responses — keep streaming format
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from flask import jsonify, request


def _get_app_version() -> str:
    """Return the application version string from env or package metadata."""
    env_ver = os.getenv("APP_VERSION")
    if env_ver:
        return env_ver
    try:
        from mes_dashboard import version as _pkg_version
        return _pkg_version
    except Exception:
        return "unknown"

# ============================================================
# Standard Error Codes
# ============================================================

# Database errors
DB_CONNECTION_FAILED = "DB_CONNECTION_FAILED"
DB_QUERY_TIMEOUT = "DB_QUERY_TIMEOUT"
DB_QUERY_ERROR = "DB_QUERY_ERROR"
DB_POOL_EXHAUSTED = "DB_POOL_EXHAUSTED"

# Service errors
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"

# Client errors
VALIDATION_ERROR = "VALIDATION_ERROR"
UNAUTHORIZED = "UNAUTHORIZED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"

# Server errors
INTERNAL_ERROR = "INTERNAL_ERROR"

# Cache signals (used as flow-control error codes in cache-backed routes)
CACHE_EXPIRED = "CACHE_EXPIRED"
CACHE_MISS = "CACHE_MISS"

# Query-tool errors (service-layer typed exceptions)
QUERY_TIMEOUT = "QUERY_TIMEOUT"

# External service errors (AI / LLM API)
EXTERNAL_SERVICE_TIMEOUT = "EXTERNAL_SERVICE_TIMEOUT"
EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
CONTEXT_LIMIT_REACHED = "CONTEXT_LIMIT_REACHED"


# ============================================================
# Response Functions
# ============================================================

def success_response(
    data: Any,
    meta: Optional[Dict[str, Any]] = None,
    status_code: int = 200
):
    """Create a standardized success response.

    Args:
        data: The response data payload.
        meta: Optional metadata (timestamp, request_id, etc.).
        status_code: HTTP status code (default: 200).

    Returns:
        Flask response tuple (response, status_code).

    Example:
        >>> return success_response({"users": [...]})
        >>> return success_response({"id": 1}, meta={"cached": True})
    """
    response = {
        "success": True,
        "data": data,
    }

    # Add metadata if provided
    if meta is not None:
        merged_meta = dict(meta)
        if "timestamp" not in merged_meta:
            merged_meta["timestamp"] = datetime.now().isoformat()
        if "app_version" not in merged_meta:
            merged_meta["app_version"] = _get_app_version()
        response["meta"] = merged_meta
    else:
        response["meta"] = {
            "timestamp": datetime.now().isoformat(),
            "app_version": _get_app_version(),
        }

    return jsonify(response), status_code


def error_response(
    code: str,
    message: str,
    details: Optional[str] = None,
    status_code: int = 500,
    meta: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
):
    """Create a standardized error response.

    Args:
        code: Machine-readable error code (e.g., DB_CONNECTION_FAILED).
        message: User-friendly error message.
        details: Technical details (only shown in development mode).
        status_code: HTTP status code (default: 500).

    Returns:
        Flask response tuple (response, status_code).

    Example:
        >>> return error_response(
        ...     DB_CONNECTION_FAILED,
        ...     "資料庫連線失敗，請稍後再試",
        ...     "ORA-12541: TNS:no listener",
        ...     status_code=503
        ... )
    """
    error_obj = {
        "code": code,
        "message": message,
    }

    # Only include details in development mode
    if details and _is_development_mode():
        error_obj["details"] = details

    response_meta: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "app_version": _get_app_version(),
    }
    if meta:
        response_meta.update(meta)

    response = {
        "success": False,
        "error": error_obj,
        "meta": response_meta
    }

    resp = jsonify(response)
    if headers:
        for key, value in headers.items():
            resp.headers[key] = value
    return resp, status_code


def _is_development_mode() -> bool:
    """Check if the application is running in development mode."""
    flask_env = os.getenv("FLASK_ENV", "production")
    flask_debug = os.getenv("FLASK_DEBUG", "0")
    return flask_env == "development" or flask_debug == "1"


# ============================================================
# Convenience Functions for Common Errors
# ============================================================

def db_connection_error(details: Optional[str] = None):
    """Return a database connection error response."""
    return error_response(
        DB_CONNECTION_FAILED,
        "資料庫連線失敗，請稍後再試",
        details,
        status_code=503
    )


def db_query_timeout_error(details: Optional[str] = None):
    """Return a database query timeout error response."""
    return error_response(
        DB_QUERY_TIMEOUT,
        "資料庫查詢逾時，請稍後再試",
        details,
        status_code=504
    )


def service_unavailable_error(details: Optional[str] = None):
    """Return a service unavailable error response."""
    return error_response(
        SERVICE_UNAVAILABLE,
        "服務暫時無法使用，請稍後再試",
        details,
        status_code=503
    )


def circuit_breaker_error(
    details: Optional[str] = None,
    retry_after_seconds: int = 30,
):
    """Return a circuit breaker open error response."""
    retry_after_seconds = max(int(retry_after_seconds), 1)
    return error_response(
        CIRCUIT_BREAKER_OPEN,
        "服務暫時降級中，請稍後再試",
        details,
        status_code=503,
        meta={"retry_after_seconds": retry_after_seconds},
        headers={"Retry-After": str(retry_after_seconds)},
    )


def pool_exhausted_error(
    details: Optional[str] = None,
    retry_after_seconds: int = 5,
):
    """Return a pool exhausted error response."""
    retry_after_seconds = max(int(retry_after_seconds), 1)
    return error_response(
        DB_POOL_EXHAUSTED,
        "目前查詢流量較高，請稍後再試",
        details,
        status_code=503,
        meta={"retry_after_seconds": retry_after_seconds},
        headers={"Retry-After": str(retry_after_seconds)},
    )


def validation_error(message: str, details: Optional[str] = None):
    """Return a validation error response."""
    return error_response(
        VALIDATION_ERROR,
        message,
        details,
        status_code=400
    )


def unauthorized_error(message: str = "請先登入"):
    """Return an unauthorized error response."""
    return error_response(
        UNAUTHORIZED,
        message,
        status_code=401
    )


def forbidden_error(message: str = "權限不足"):
    """Return a forbidden error response."""
    return error_response(
        FORBIDDEN,
        message,
        status_code=403
    )


def not_found_error(message: str = "找不到請求的資源"):
    """Return a not found error response."""
    return error_response(
        NOT_FOUND,
        message,
        status_code=404
    )


def too_many_requests_error(message: str = "請求過於頻繁，請稍後再試"):
    """Return a too many requests error response."""
    return error_response(
        TOO_MANY_REQUESTS,
        message,
        status_code=429
    )


def internal_error(details: Optional[str] = None):
    """Return an internal server error response."""
    return error_response(
        INTERNAL_ERROR,
        "伺服器內部錯誤",
        details,
        status_code=500
    )


def cache_expired_error(details: Optional[str] = None):
    """Return a cache expired error response (HTTP 410).

    Use when a cache-backed endpoint detects its cached data has expired
    and cannot serve the request without a fresh load.
    """
    return error_response(
        CACHE_EXPIRED,
        "快取資料已過期，請稍後再試",
        details,
        status_code=410
    )


def cache_miss_error(details: Optional[str] = None):
    """Return a cache miss error response (HTTP 400).

    Use when a cache-backed endpoint is queried before its cache has been
    populated (e.g. initial load not yet complete).
    """
    return error_response(
        CACHE_MISS,
        "快取資料尚未就緒，請稍後再試",
        details,
        status_code=400
    )


def external_service_timeout_error(details: Optional[str] = None):
    """Return an external service timeout error response (HTTP 504)."""
    return error_response(
        EXTERNAL_SERVICE_TIMEOUT,
        "AI 服務回應逾時，請稍後再試",
        details,
        status_code=504
    )


def external_service_error(details: Optional[str] = None):
    """Return an external service error response (HTTP 502)."""
    return error_response(
        EXTERNAL_SERVICE_ERROR,
        "AI 服務暫時不可用，請稍後再試",
        details,
        status_code=502
    )


def context_limit_error(details: Optional[str] = None):
    """Return a context limit reached error response (HTTP 400)."""
    return error_response(
        CONTEXT_LIMIT_REACHED,
        "對話已達上限，請開啟新對話繼續",
        details,
        status_code=400
    )


def query_timeout_error(message: str, details: Optional[str] = None):
    """Return a query timeout error response (HTTP 504).

    Use when a service-layer ``QueryTimeoutError`` is caught — the upstream
    Oracle query exceeded its configured timeout and the user should narrow
    their search range and retry.
    """
    return error_response(
        QUERY_TIMEOUT,
        message,
        details,
        status_code=504
    )
