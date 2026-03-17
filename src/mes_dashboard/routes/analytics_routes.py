# -*- coding: utf-8 -*-
"""Analytics API routes — anomaly detection endpoints.

Thin route layer: parameter parsing → service invocation → response formatting.
All business logic lives in anomaly_detection_sql_runtime.py.
"""

from __future__ import annotations

import logging

from flask import Blueprint

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    not_found_error,
    success_response,
)
from mes_dashboard.services.anomaly_detection_sql_runtime import (
    _ANALYTICS_ENABLED,
    get_cached_detail,
    get_cached_summary,
)

logger = logging.getLogger("mes_dashboard.analytics_routes")

analytics_bp = Blueprint("analytics", __name__)

_ANALYTICS_RATE_LIMIT = configured_rate_limit(
    bucket="analytics-query",
    max_attempts_env="ANALYTICS_QUERY_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="ANALYTICS_QUERY_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)




@analytics_bp.route("/api/analytics/anomaly-summary", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def anomaly_summary():
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    cached = get_cached_summary()
    if cached is None:
        return success_response(
            {"total_count": 0, "severity": "ok", "breakdown": {}},
            meta={"source": "cache_miss"},
        )
    return success_response(cached.get("data", {}), meta=cached.get("meta", {}))


def _serve_cached_detail(detector_name: str):
    """Serve cached detail results for a detector from Redis."""
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    cached = get_cached_detail(detector_name)
    if cached is None:
        return success_response({"items": [], "count": 0}, meta={"source": "cache_miss"})
    return success_response(
        {"items": cached.get("items", []), "count": cached.get("count", 0)},
        meta=cached.get("meta", {}),
    )


@analytics_bp.route("/api/analytics/yield-anomalies", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def yield_anomalies():
    return _serve_cached_detail("yield")


@analytics_bp.route("/api/analytics/reject-spikes", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def reject_spikes():
    return _serve_cached_detail("reject")


@analytics_bp.route("/api/analytics/hold-outliers", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def hold_outliers():
    return _serve_cached_detail("hold")


@analytics_bp.route("/api/analytics/equipment-deviation", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def equipment_deviation():
    return _serve_cached_detail("equipment")
