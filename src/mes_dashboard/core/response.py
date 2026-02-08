# -*- coding: utf-8 -*-
"""Standard API response format utilities for MES Dashboard.

Provides consistent response envelope for all API endpoints.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from flask import jsonify, request

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
        response["meta"] = meta
    else:
        # Add default metadata
        response["meta"] = {
            "timestamp": datetime.now().isoformat(),
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
