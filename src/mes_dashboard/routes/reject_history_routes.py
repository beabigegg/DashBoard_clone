# -*- coding: utf-8 -*-
"""Reject-history page API routes."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from flask import Blueprint, Response, jsonify, request

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.reject_history_service import (
    export_csv,
    get_filter_options,
    query_analytics,
    query_list,
    query_reason_pareto,
    query_summary,
    query_trend,
)

reject_history_bp = Blueprint("reject_history", __name__)
_REJECT_HISTORY_OPTIONS_CACHE_TTL_SECONDS = int(
    os.getenv("REJECT_HISTORY_OPTIONS_CACHE_TTL_SECONDS", "14400")
)

_REJECT_HISTORY_LIST_RATE_LIMIT = configured_rate_limit(
    bucket="reject-history-list",
    max_attempts_env="REJECT_HISTORY_LIST_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="REJECT_HISTORY_LIST_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=90,
    default_window_seconds=60,
)

_REJECT_HISTORY_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="reject-history-export",
    max_attempts_env="REJECT_HISTORY_EXPORT_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="REJECT_HISTORY_EXPORT_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)


def _default_date_range() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=29)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _parse_date_range(required: bool = True) -> tuple[Optional[str], Optional[str], Optional[tuple[dict, int]]]:
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    if not start_date or not end_date:
        if required:
            return None, None, ({"success": False, "error": "缺少必要參數: start_date, end_date"}, 400)
        start_date, end_date = _default_date_range()

    return start_date, end_date, None


def _parse_bool(value: str, *, name: str) -> tuple[Optional[bool], Optional[tuple[dict, int]]]:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "0", "false", "no", "n", "off"}:
        return False, None
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True, None
    return None, ({"success": False, "error": f"Invalid {name}, use true/false"}, 400)


def _parse_multi_param(name: str) -> list[str]:
    values = []
    for raw in request.args.getlist(name):
        for token in str(raw).split(","):
            item = token.strip()
            if item:
                values.append(item)
    # Deduplicate while preserving order.
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalized_list_for_cache(values: Optional[list[str]]) -> Optional[list[str]]:
    if not values:
        return None
    return sorted({
        str(value).strip()
        for value in values
        if str(value).strip()
    })


def _extract_meta(
    payload: dict,
    include_excluded_scrap: bool,
    exclude_material_scrap: bool,
    exclude_pb_diode: bool = True,
) -> tuple[dict, dict]:
    data = dict(payload or {})
    meta = data.pop("meta", {}) if isinstance(data.get("meta"), dict) else {}
    meta["include_excluded_scrap"] = bool(include_excluded_scrap)
    meta["exclude_material_scrap"] = bool(exclude_material_scrap)
    meta["exclude_pb_diode"] = bool(exclude_pb_diode)
    return data, meta


def _parse_common_bools() -> tuple[Optional[tuple[dict, int]], bool, bool, bool]:
    """Parse include_excluded_scrap, exclude_material_scrap, exclude_pb_diode."""
    include_excluded_scrap, err1 = _parse_bool(
        request.args.get("include_excluded_scrap", ""),
        name="include_excluded_scrap",
    )
    if err1:
        return err1, False, True, True
    exclude_material_scrap, err2 = _parse_bool(
        request.args.get("exclude_material_scrap", "true"),
        name="exclude_material_scrap",
    )
    if err2:
        return err2, False, True, True
    exclude_pb_diode, err3 = _parse_bool(
        request.args.get("exclude_pb_diode", "true"),
        name="exclude_pb_diode",
    )
    if err3:
        return err3, False, True, True
    return (
        None,
        bool(include_excluded_scrap),
        bool(exclude_material_scrap),
        bool(exclude_pb_diode),
    )


@reject_history_bp.route("/api/reject-history/options", methods=["GET"])
def api_reject_history_options():
    start_date, end_date, date_error = _parse_date_range(required=False)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    workcenter_groups = _parse_multi_param("workcenter_groups") or None
    packages = _parse_multi_param("packages") or None
    categories = _parse_multi_param("categories") or None

    reasons = _parse_multi_param("reasons")
    single_reason = _parse_multi_param("reason")
    for reason in single_reason:
        if reason not in reasons:
            reasons.append(reason)
    reasons = reasons or None

    cache_filters = {
        "start_date": start_date,
        "end_date": end_date,
        "workcenter_groups": _normalized_list_for_cache(workcenter_groups),
        "packages": _normalized_list_for_cache(packages),
        "reasons": _normalized_list_for_cache(reasons),
        "categories": _normalized_list_for_cache(categories),
        "include_excluded_scrap": bool(include_excluded_scrap),
        "exclude_material_scrap": bool(exclude_material_scrap),
        "exclude_pb_diode": bool(exclude_pb_diode),
    }
    cache_key = make_cache_key("reject_history_options_v2", filters=cache_filters)
    cached_payload = cache_get(cache_key)
    if cached_payload is not None:
        return jsonify(cached_payload)

    try:
        result = get_filter_options(
            start_date=start_date,
            end_date=end_date,
            workcenter_groups=workcenter_groups,
            packages=packages,
            reasons=reasons,
            categories=categories,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        payload = {"success": True, "data": data, "meta": meta}
        cache_set(
            cache_key,
            payload,
            ttl=max(_REJECT_HISTORY_OPTIONS_CACHE_TTL_SECONDS, 1),
        )
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢篩選選項失敗"}), 500


@reject_history_bp.route("/api/reject-history/summary", methods=["GET"])
def api_reject_history_summary():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    try:
        result = query_summary(
            start_date=start_date,
            end_date=end_date,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            packages=_parse_multi_param("packages") or None,
            reasons=_parse_multi_param("reasons") or None,
            categories=_parse_multi_param("categories") or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢摘要資料失敗"}), 500


@reject_history_bp.route("/api/reject-history/trend", methods=["GET"])
def api_reject_history_trend():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    granularity = request.args.get("granularity", "day").strip().lower() or "day"
    try:
        result = query_trend(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            packages=_parse_multi_param("packages") or None,
            reasons=_parse_multi_param("reasons") or None,
            categories=_parse_multi_param("categories") or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢趨勢資料失敗"}), 500


@reject_history_bp.route("/api/reject-history/reason-pareto", methods=["GET"])
def api_reject_history_reason_pareto():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    metric_mode = request.args.get("metric_mode", "reject_total").strip().lower() or "reject_total"
    pareto_scope = request.args.get("pareto_scope", "top80").strip().lower() or "top80"

    try:
        result = query_reason_pareto(
            start_date=start_date,
            end_date=end_date,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            packages=_parse_multi_param("packages") or None,
            reasons=_parse_multi_param("reasons") or None,
            categories=_parse_multi_param("categories") or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢柏拉圖資料失敗"}), 500


@reject_history_bp.route("/api/reject-history/list", methods=["GET"])
@_REJECT_HISTORY_LIST_RATE_LIMIT
def api_reject_history_list():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 50, type=int) or 50
    metric_filter = request.args.get("metric_filter", "all").strip().lower() or "all"

    try:
        result = query_list(
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            packages=_parse_multi_param("packages") or None,
            reasons=_parse_multi_param("reasons") or None,
            categories=_parse_multi_param("categories") or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
            metric_filter=metric_filter,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢明細資料失敗"}), 500


@reject_history_bp.route("/api/reject-history/export", methods=["GET"])
@_REJECT_HISTORY_EXPORT_RATE_LIMIT
def api_reject_history_export():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    metric_filter = request.args.get("metric_filter", "all").strip().lower() or "all"
    filename = f"reject_history_{start_date}_to_{end_date}.csv"
    try:
        return Response(
            export_csv(
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=_parse_multi_param("workcenter_groups") or None,
                packages=_parse_multi_param("packages") or None,
                reasons=_parse_multi_param("reasons") or None,
                categories=_parse_multi_param("categories") or None,
                include_excluded_scrap=include_excluded_scrap,
                exclude_material_scrap=exclude_material_scrap,
                exclude_pb_diode=exclude_pb_diode,
                metric_filter=metric_filter,
            ),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8-sig",
            },
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "匯出 CSV 失敗"}), 500


@reject_history_bp.route("/api/reject-history/analytics", methods=["GET"])
def api_reject_history_analytics():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    metric_mode = request.args.get("metric_mode", "reject_total").strip().lower() or "reject_total"

    try:
        result = query_analytics(
            start_date=start_date,
            end_date=end_date,
            metric_mode=metric_mode,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            packages=_parse_multi_param("packages") or None,
            reasons=_parse_multi_param("reasons") or None,
            categories=_parse_multi_param("categories") or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        data, meta = _extract_meta(
            result,
            include_excluded_scrap,
            exclude_material_scrap,
            exclude_pb_diode,
        )
        return jsonify({"success": True, "data": data, "meta": meta})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢分析資料失敗"}), 500
