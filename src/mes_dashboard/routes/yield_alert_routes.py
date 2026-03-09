# -*- coding: utf-8 -*-
"""Yield Alert Center API routes."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from flask import Blueprint, jsonify, make_response, request

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.services.yield_alert_dataset_cache import (
    apply_view as apply_cached_view,
    execute_linkage_query,
    execute_primary_query,
)
from mes_dashboard.services.yield_alert_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_QUERY_DAYS,
    VALID_SORT_FIELDS,
    build_drilldown_payload,
    build_query_cache_key,
    expand_workcenter_groups_to_departments,
    get_yield_workcenter_group_options,
    query_alert_candidates,
    query_reason_detail,
    query_yield_summary,
    query_yield_trend,
)

logger = logging.getLogger("mes_dashboard.yield_alert_routes")

yield_alert_bp = Blueprint("yield_alert", __name__)

_YIELD_ALERT_ENABLED = os.getenv("YIELD_ALERT_CENTER_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_DEFAULT_CACHE_TTL = max(30, int(os.getenv("YIELD_ALERT_CACHE_TTL_SECONDS", "300")))

_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket="yield-alert-query",
    max_attempts_env="YIELD_ALERT_QUERY_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="YIELD_ALERT_QUERY_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)


def _default_date_range() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=29)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _parse_date_range(required: bool = True) -> tuple[str | None, str | None, tuple[dict, int] | None]:
    start_date = str(request.args.get("start_date", "")).strip()
    end_date = str(request.args.get("end_date", "")).strip()

    if not start_date or not end_date:
        if required:
            return None, None, (
                {
                    "success": False,
                    "error": "缺少必要參數: start_date, end_date",
                    "meta": {"max_query_days": MAX_QUERY_DAYS},
                },
                400,
            )
        start_date, end_date = _default_date_range()

    return start_date, end_date, None


def _parse_multi_param(name: str) -> list[str]:
    values: list[str] = []
    for raw in request.args.getlist(name):
        for token in str(raw).split(","):
            item = token.strip()
            if item:
                values.append(item)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _common_filters() -> dict:
    workcenter_groups = _parse_multi_param("workcenter_groups")
    departments = expand_workcenter_groups_to_departments(workcenter_groups)
    if not departments:
        departments = _parse_multi_param("departments")
    return {
        "workcenter_groups": workcenter_groups,
        "departments": departments,
        "lines": _parse_multi_param("lines"),
        "packages": _parse_multi_param("packages"),
        "types": _parse_multi_param("types"),
        "functions": _parse_multi_param("functions"),
        "operations": _parse_multi_param("operations"),
    }


def _cache_response(namespace: str, payload_key: dict, compute_fn):
    cache_key = build_query_cache_key(namespace, payload_key)
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info("Yield alert cache hit: namespace=%s key=%s", namespace, cache_key)
        cached_payload = dict(cached)
        meta = dict(cached_payload.get("meta") or {})
        meta["cache"] = {"hit": True, "key": cache_key}
        cached_payload["meta"] = meta
        return jsonify(cached_payload)

    logger.info("Yield alert cache miss: namespace=%s key=%s", namespace, cache_key)
    payload = compute_fn()
    meta = dict(payload.get("meta") or {})
    meta["cache"] = {"hit": False, "key": cache_key}
    payload["meta"] = meta
    cache_set(cache_key, payload, ttl=_DEFAULT_CACHE_TTL)
    return jsonify(payload)


@yield_alert_bp.route("/api/yield-alert/query", methods=["POST"])
@_QUERY_RATE_LIMIT
def api_yield_alert_query():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return jsonify({"success": False, "error": payload_error.message}), payload_error.status_code

    start_date = str(body.get("start_date", "")).strip()
    end_date = str(body.get("end_date", "")).strip()
    if not start_date or not end_date:
        return jsonify({"success": False, "error": "缺少必要參數: start_date, end_date"}), 400

    try:
        result = execute_primary_query(start_date=start_date, end_date=end_date)
        return jsonify({"success": True, **result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "meta": {"max_query_days": MAX_QUERY_DAYS}}), 400
    except Exception:
        logger.exception("Yield alert primary query failed")
        return jsonify({"success": False, "error": "主查詢執行失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/analyze", methods=["POST"])
@_QUERY_RATE_LIMIT
def api_yield_alert_analyze():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return jsonify({"success": False, "error": payload_error.message}), payload_error.status_code

    query_id = str(body.get("query_id", "")).strip()
    if not query_id:
        return jsonify({"success": False, "error": "缺少必要參數: query_id"}), 400

    try:
        result = execute_linkage_query(query_id=query_id)
        if result is None:
            resp = make_response(jsonify({"success": False, "error": "cache_expired"}), 410)
            resp.headers["Cache-Control"] = "no-store"
            return resp
        return jsonify({"success": True, **result})
    except Exception:
        logger.exception("Yield alert linkage analysis failed")
        return jsonify({"success": False, "error": "告警連結分析失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/view", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_view():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    query_id = str(request.args.get("query_id", "")).strip()
    if not query_id:
        return jsonify({"success": False, "error": "缺少必要參數: query_id"}), 400

    filters = _common_filters()

    try:
        page = max(1, int(request.args.get("page", "1") or 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "page 必須為正整數"}), 400
    try:
        per_page = int(request.args.get("per_page", str(DEFAULT_PAGE_SIZE)) or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "per_page 必須為正整數"}), 400
    per_page = min(max(1, per_page), MAX_PAGE_SIZE)

    sort_by = str(request.args.get("sort_by", "date_bucket") or "date_bucket").strip()
    if sort_by not in VALID_SORT_FIELDS:
        return jsonify({"success": False, "error": f"sort_by 不支援，允許值: {', '.join(sorted(VALID_SORT_FIELDS))}"}), 400
    sort_dir = str(request.args.get("sort_dir", "desc") or "desc").strip().lower()
    if sort_dir not in {"asc", "desc"}:
        return jsonify({"success": False, "error": "sort_dir 僅支援 asc/desc"}), 400

    try:
        risk_threshold = float(request.args.get("risk_threshold", "98"))
        min_scrap_qty = float(request.args.get("min_scrap_qty", "1"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "risk_threshold/min_scrap_qty 需為數值"}), 400

    granularity = str(request.args.get("granularity", "day") or "day").strip().lower()

    try:
        result = apply_cached_view(
            query_id=query_id,
            filters=filters,
            granularity=granularity,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            sort_dir=sort_dir,
            risk_threshold=risk_threshold,
            min_scrap_qty=min_scrap_qty,
        )
        if result is None:
            resp = make_response(jsonify({"success": False, "error": "cache_expired"}), 410)
            resp.headers["Cache-Control"] = "no-store"
            return resp

        data = dict(result)
        meta = dict(data.pop("meta", {}) or {})
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "meta": {"max_query_days": MAX_QUERY_DAYS, "max_per_page": MAX_PAGE_SIZE},
            }
        ), 400
    except Exception:
        logger.exception("Yield alert cached view query failed")
        return jsonify({"success": False, "error": "視圖查詢失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/summary", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_summary():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    filters = _common_filters()

    payload_key = {
        "start_date": start_date,
        "end_date": end_date,
        "filters": filters,
    }

    def _compute():
        result = query_yield_summary(
            start_date=start_date or "",
            end_date=end_date or "",
            filters=filters,
        )
        return {
            "success": True,
            "data": result["summary"],
            "meta": result.get("meta") or {},
        }

    try:
        return _cache_response("summary", payload_key, _compute)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "meta": {"max_query_days": MAX_QUERY_DAYS}}), 400
    except Exception:
        logger.exception("Yield alert summary query failed")
        return jsonify({"success": False, "error": "查詢良率摘要失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/trend", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_trend():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    granularity = str(request.args.get("granularity", "day") or "day").strip().lower()
    filters = _common_filters()

    payload_key = {
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "filters": filters,
    }

    def _compute():
        result = query_yield_trend(
            start_date=start_date or "",
            end_date=end_date or "",
            granularity=granularity,
            filters=filters,
        )
        return {
            "success": True,
            "data": {
                "items": result["items"],
                "granularity": result["granularity"],
            },
            "meta": result.get("meta") or {},
        }

    try:
        return _cache_response("trend", payload_key, _compute)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "meta": {"max_query_days": MAX_QUERY_DAYS}}), 400
    except Exception:
        logger.exception("Yield alert trend query failed")
        return jsonify({"success": False, "error": "查詢良率趨勢失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/alerts", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_alerts():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    filters = _common_filters()

    try:
        page = max(1, int(request.args.get("page", "1") or 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "page 必須為正整數"}), 400
    try:
        per_page = int(request.args.get("per_page", str(DEFAULT_PAGE_SIZE)) or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "per_page 必須為正整數"}), 400
    per_page = min(max(1, per_page), MAX_PAGE_SIZE)

    sort_by = str(request.args.get("sort_by", "date_bucket") or "date_bucket").strip()
    if sort_by not in VALID_SORT_FIELDS:
        return jsonify({"success": False, "error": f"sort_by 不支援，允許值: {', '.join(sorted(VALID_SORT_FIELDS))}"}), 400
    sort_dir = str(request.args.get("sort_dir", "desc") or "desc").strip().lower()
    if sort_dir not in {"asc", "desc"}:
        return jsonify({"success": False, "error": "sort_dir 僅支援 asc/desc"}), 400

    try:
        risk_threshold = float(request.args.get("risk_threshold", "98"))
        min_scrap_qty = float(request.args.get("min_scrap_qty", "1"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "risk_threshold/min_scrap_qty 需為數值"}), 400

    payload_key = {
        "start_date": start_date,
        "end_date": end_date,
        "filters": filters,
        "page": page,
        "per_page": per_page,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "risk_threshold": risk_threshold,
        "min_scrap_qty": min_scrap_qty,
    }

    def _compute():
        result = query_alert_candidates(
            start_date=start_date or "",
            end_date=end_date or "",
            filters=filters,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            sort_dir=sort_dir,
            risk_threshold=risk_threshold,
            min_scrap_qty=min_scrap_qty,
        )
        return {
            "success": True,
            "data": {
                "items": result["items"],
                "pagination": result["pagination"],
                "quality": result["quality"],
                "sort": result["sort"],
            },
            "meta": result.get("meta") or {},
        }

    try:
        return _cache_response("alerts", payload_key, _compute)
    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "meta": {"max_query_days": MAX_QUERY_DAYS, "max_per_page": MAX_PAGE_SIZE},
            }
        ), 400
    except Exception:
        logger.exception("Yield alert candidate query failed")
        return jsonify({"success": False, "error": "查詢告警清單失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/reason-detail", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_reason_detail():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    workorder = str(request.args.get("workorder", "")).strip()
    date_bucket = str(request.args.get("date_bucket", "")).strip()
    reason_code = str(request.args.get("reason_code", "")).strip()
    department = str(request.args.get("department", "")).strip()

    if not workorder or not date_bucket:
        return jsonify({"success": False, "error": "缺少必要參數: workorder, date_bucket"}), 400

    try:
        items = query_reason_detail(workorder=workorder, date_bucket=date_bucket, reason_code=reason_code, department=department)
        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "workorder": workorder,
                "date_bucket": date_bucket,
            },
        })
    except Exception:
        logger.exception("Yield alert reason detail query failed")
        return jsonify({"success": False, "error": "查詢報廢明細失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/drilldown-context", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_drilldown_context():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    date_bucket = str(request.args.get("date_bucket", "")).strip()
    workorder = str(request.args.get("workorder", "")).strip()
    reason_code = str(request.args.get("reason_code", "")).strip()

    if not date_bucket or not workorder:
        return jsonify({"success": False, "error": "缺少必要參數: date_bucket, workorder"}), 400

    try:
        payload = build_drilldown_payload(
            date_bucket=date_bucket,
            workorder=workorder,
            reason_code=reason_code,
        )
        return jsonify({"success": True, "data": payload})
    except Exception:
        logger.exception("Yield alert drilldown context failed")
        return jsonify({"success": False, "error": "建立追溯連結失敗"}), 500


@yield_alert_bp.route("/api/yield-alert/filter-options", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_yield_alert_filter_options():
    if not _YIELD_ALERT_ENABLED:
        return jsonify({"success": False, "error": "yield_alert_disabled"}), 404

    try:
        groups = get_yield_workcenter_group_options()
        return jsonify(
            {
                "success": True,
                "data": {
                    "workcenter_groups": groups,
                },
            }
        )
    except Exception:
        logger.exception("Yield alert filter options query failed")
        return jsonify({"success": False, "error": "載入站別群組選項失敗"}), 500
