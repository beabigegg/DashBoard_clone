# -*- coding: utf-8 -*-
"""Analytics API routes — anomaly detection endpoints.

Thin route layer: parameter parsing → service invocation → response formatting.
All business logic lives in anomaly_detection_sql_runtime.py.
"""

from __future__ import annotations

import logging

from flask import Blueprint, request

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    not_found_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.anomaly_detection_sql_runtime import (
    _ANALYTICS_ENABLED,
    drilldown_equipment_trend,
    drilldown_hold_detail,
    drilldown_reject_trend,
    drilldown_yield_trend,
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


# ---------------------------------------------------------------------------
# Drilldown endpoints — read anomaly spool directly (no Oracle)
# ---------------------------------------------------------------------------


@analytics_bp.route("/api/analytics/yield-anomalies/drilldown", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def yield_anomalies_drilldown():
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    workcenter_group = (request.args.get("workcenter_group") or "").strip()
    package = (request.args.get("package") or "").strip()
    if not workcenter_group or not package:
        return validation_error("必須提供 workcenter_group 和 package 參數")

    items, meta = drilldown_yield_trend(workcenter_group, package)
    if items is None:
        return success_response({"items": [], "count": 0}, meta=meta)
    return success_response({"items": items, "count": len(items)}, meta=meta)


@analytics_bp.route("/api/analytics/reject-spikes/drilldown", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def reject_spikes_drilldown():
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    workcenter_group = (request.args.get("workcenter_group") or "").strip()
    if not workcenter_group:
        return validation_error("必須提供 workcenter_group 參數")

    items, meta = drilldown_reject_trend(workcenter_group)
    if items is None:
        return success_response({"items": [], "count": 0}, meta=meta)
    return success_response({"items": items, "count": len(items)}, meta=meta)


@analytics_bp.route("/api/analytics/hold-outliers/drilldown", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def hold_outliers_drilldown():
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    lot_id = (request.args.get("lot_id") or "").strip()
    hold_day = (request.args.get("hold_day") or "").strip()
    if not lot_id or not hold_day:
        return validation_error("必須提供 lot_id 和 hold_day 參數")

    items, meta = drilldown_hold_detail(lot_id, hold_day)
    if items is None:
        return success_response({"items": [], "count": 0}, meta=meta)
    return success_response({"items": items, "count": len(items)}, meta=meta)


@analytics_bp.route("/api/analytics/equipment-deviation/drilldown", methods=["GET"])
@_ANALYTICS_RATE_LIMIT
def equipment_deviation_drilldown():
    if not _ANALYTICS_ENABLED:
        return not_found_error("功能未啟用")

    workcenter_group = (request.args.get("workcenter_group") or "").strip()
    resource_model = (request.args.get("resource_model") or "").strip()
    if not workcenter_group or not resource_model:
        return validation_error("必須提供 workcenter_group 和 resource_model 參數")

    items, meta = drilldown_equipment_trend(workcenter_group, resource_model)
    if items is None:
        return success_response({"items": [], "count": 0}, meta=meta)
    return success_response({"items": items, "count": len(items)}, meta=meta)
