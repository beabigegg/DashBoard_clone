# -*- coding: utf-8 -*-
"""Reject-history page API routes."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from flask import Blueprint, Response, jsonify, request

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.utils import parse_bool_query
from mes_dashboard.services.reject_dataset_cache import (
    apply_view,
    compute_batch_pareto,
    compute_dimension_pareto,
    execute_primary_query,
    export_csv_from_cache,
)
from mes_dashboard.services.reject_history_service import (
    _list_to_csv,
    export_csv,
    get_filter_options,
    query_analytics,
    query_list,
    query_dimension_pareto,
    query_reason_pareto,
    query_summary,
    query_trend,
)

reject_history_bp = Blueprint("reject_history", __name__)
logger = logging.getLogger("mes_dashboard.reject_history_routes")
_REJECT_HISTORY_OPTIONS_CACHE_TTL_SECONDS = int(
    os.getenv("REJECT_HISTORY_OPTIONS_CACHE_TTL_SECONDS", "14400")
)
_REJECT_HISTORY_PRIMARY_MAX_QUERY_DAYS = max(
    1, int(os.getenv("REJECT_HISTORY_PRIMARY_MAX_QUERY_DAYS", "190"))
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


def _validate_primary_query_date_range(start_date: str, end_date: str) -> Optional[str]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return "start_date / end_date 日期格式需為 YYYY-MM-DD"

    if end < start:
        return "結束日期必須大於起始日期"

    range_days = (end - start).days + 1
    if range_days > _REJECT_HISTORY_PRIMARY_MAX_QUERY_DAYS:
        return f"查詢範圍不可超過 {_REJECT_HISTORY_PRIMARY_MAX_QUERY_DAYS} 天（約半年）"
    return None


def _parse_date_range(required: bool = True) -> tuple[Optional[str], Optional[str], Optional[tuple[dict, int]]]:
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    if not start_date or not end_date:
        if required:
            return None, None, ({"success": False, "error": "缺少必要參數: start_date, end_date"}, 400)
        start_date, end_date = _default_date_range()

    return start_date, end_date, None


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


_VALID_BOOL_STRINGS = {"", "0", "false", "no", "n", "off", "1", "true", "yes", "y", "on"}
_VALID_PARETO_DIMENSIONS = {
    "reason",
    "package",
    "type",
    "workflow",
    "workcenter",
    "equipment",
}
_PARETO_SELECTION_PARAMS = {
    "reason": "sel_reason",
    "package": "sel_package",
    "type": "sel_type",
    "workflow": "sel_workflow",
    "workcenter": "sel_workcenter",
    "equipment": "sel_equipment",
}
_REJECT_PARETO_SCOPE_FIXED = "top80"
_REJECT_BATCH_PARETO_DISPLAY_SCOPE_FIXED = "top20"


def _parse_common_bools() -> tuple[Optional[tuple[dict, int]], bool, bool, bool]:
    """Parse include_excluded_scrap, exclude_material_scrap, exclude_pb_diode."""
    for name in ("include_excluded_scrap", "exclude_material_scrap", "exclude_pb_diode"):
        raw = str(request.args.get(name, "") or "").strip().lower()
        if raw not in _VALID_BOOL_STRINGS:
            return ({"success": False, "error": f"Invalid {name}, use true/false"}, 400), False, True, True

    include_excluded_scrap = parse_bool_query(
        request.args.get("include_excluded_scrap", ""),
        default=False,
    )
    exclude_material_scrap = parse_bool_query(
        request.args.get("exclude_material_scrap", "true"),
        default=True,
    )
    exclude_pb_diode = parse_bool_query(
        request.args.get("exclude_pb_diode", "true"),
        default=True,
    )
    return None, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode


def _parse_pareto_selection() -> tuple[Optional[tuple[dict, int]], Optional[str], Optional[list[str]]]:
    pareto_dimension = request.args.get("pareto_dimension", "").strip().lower()
    pareto_values = _parse_multi_param("pareto_values")
    if pareto_values and not pareto_dimension:
        pareto_dimension = "reason"
    if pareto_dimension and pareto_dimension not in _VALID_PARETO_DIMENSIONS:
        return (
            {
                "success": False,
                "error": f"Invalid pareto_dimension, supported: {', '.join(sorted(_VALID_PARETO_DIMENSIONS))}",
            },
            400,
        ), None, None
    return None, (pareto_dimension or None), (pareto_values or None)


def _parse_multi_pareto_selections() -> dict[str, list[str]]:
    selections: dict[str, list[str]] = {}
    for dim, param_name in _PARETO_SELECTION_PARAMS.items():
        values = _parse_multi_param(param_name)
        if values:
            selections[dim] = values
    return selections


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
    pareto_scope = _REJECT_PARETO_SCOPE_FIXED
    dimension = request.args.get("dimension", "reason").strip().lower() or "reason"
    query_id = request.args.get("query_id", "").strip()

    try:
        # Prefer cache-based computation when query_id is available
        if query_id:
            result = compute_dimension_pareto(
                query_id=query_id,
                dimension=dimension,
                metric_mode=metric_mode,
                pareto_scope=pareto_scope,
                packages=_parse_multi_param("packages") or None,
                workcenter_groups=_parse_multi_param("workcenter_groups") or None,
                reasons=_parse_multi_param("reasons") or None,
                trend_dates=_parse_multi_param("trend_dates") or None,
                include_excluded_scrap=include_excluded_scrap,
                exclude_material_scrap=exclude_material_scrap,
                exclude_pb_diode=exclude_pb_diode,
            )
            if result is not None:
                pareto_meta = result.pop("_pareto_meta", None) or {}
                return jsonify({"success": True, "data": result, "meta": pareto_meta})
            # Cache expired, fall through to Oracle query

        result = query_dimension_pareto(
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
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
    except MemoryError as exc:
        logger.warning("Reject history reason-pareto memory guard: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢柏拉圖資料失敗"}), 500


@reject_history_bp.route("/api/reject-history/batch-pareto", methods=["GET"])
def api_reject_history_batch_pareto():
    """Batch pareto view: compute all dimensions from cache only."""
    query_id = request.args.get("query_id", "").strip()
    if not query_id:
        return jsonify({"success": False, "error": "缺少必要參數: query_id"}), 400

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return jsonify(bool_error[0]), bool_error[1]

    metric_mode = request.args.get("metric_mode", "reject_total").strip().lower() or "reject_total"
    pareto_scope = _REJECT_PARETO_SCOPE_FIXED
    pareto_display_scope = _REJECT_BATCH_PARETO_DISPLAY_SCOPE_FIXED

    try:
        result = compute_batch_pareto(
            query_id=query_id,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
            pareto_display_scope=pareto_display_scope,
            packages=_parse_multi_param("packages") or None,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            reasons=_parse_multi_param("reasons") or None,
            trend_dates=_parse_multi_param("trend_dates") or None,
            pareto_selections=_parse_multi_pareto_selections(),
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        if result is None:
            return jsonify({"success": False, "error": "cache_miss"}), 400
        pareto_meta = result.pop("_pareto_meta", None)
        resp: dict = {"success": True, "data": result}
        if pareto_meta:
            resp["meta"] = pareto_meta
        return jsonify(resp)
    except MemoryError as exc:
        logger.warning("Reject history batch-pareto memory guard: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "查詢批次柏拉圖失敗"}), 500


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


# ============================================================
# Two-phase query endpoints (POST /query, GET /view)
# ============================================================


@reject_history_bp.route("/api/reject-history/query", methods=["POST"])
def api_reject_history_query():
    """Primary query: execute Oracle → cache DataFrame → return results."""
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return jsonify({"success": False, "error": payload_error.message}), payload_error.status_code

    mode = str(body.get("mode", "")).strip()
    if mode not in ("date_range", "container"):
        return jsonify({"success": False, "error": "mode 必須為 date_range 或 container"}), 400

    include_excluded_scrap = bool(body.get("include_excluded_scrap", False))
    exclude_material_scrap = bool(body.get("exclude_material_scrap", True))
    exclude_pb_diode = bool(body.get("exclude_pb_diode", True))

    try:
        kwargs = {
            "mode": mode,
            "include_excluded_scrap": include_excluded_scrap,
            "exclude_material_scrap": exclude_material_scrap,
            "exclude_pb_diode": exclude_pb_diode,
        }

        if mode == "date_range":
            kwargs["start_date"] = str(body.get("start_date", "")).strip()
            kwargs["end_date"] = str(body.get("end_date", "")).strip()
            if not kwargs["start_date"] or not kwargs["end_date"]:
                return jsonify({"success": False, "error": "date_range mode 需要 start_date 和 end_date"}), 400
            date_range_error = _validate_primary_query_date_range(
                kwargs["start_date"],
                kwargs["end_date"],
            )
            if date_range_error:
                return jsonify({"success": False, "error": date_range_error}), 400
        else:
            kwargs["container_input_type"] = str(body.get("container_input_type", "lot")).strip()
            container_values = body.get("container_values", [])
            if not isinstance(container_values, list) or not container_values:
                return jsonify({"success": False, "error": "container mode 需要 container_values 陣列"}), 400
            kwargs["container_values"] = [str(v).strip() for v in container_values if str(v).strip()]

        result = execute_primary_query(**kwargs)
        return jsonify({"success": True, **result})

    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": "主查詢執行失敗"}), 500


@reject_history_bp.route("/api/reject-history/view", methods=["GET"])
def api_reject_history_view():
    """Supplementary view: read cache → filter → return derived data."""
    query_id = request.args.get("query_id", "").strip()
    if not query_id:
        return jsonify({"success": False, "error": "缺少必要參數: query_id"}), 400

    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 50, type=int) or 50
    metric_filter = request.args.get("metric_filter", "all").strip().lower() or "all"
    reasons = _parse_multi_param("reasons") or None
    detail_reason = request.args.get("detail_reason", "").strip() or None
    pareto_selections = _parse_multi_pareto_selections()
    pareto_dimension = None
    pareto_values = None
    if not pareto_selections:
        pareto_error, pareto_dimension, pareto_values = _parse_pareto_selection()
        if pareto_error:
            return jsonify(pareto_error[0]), pareto_error[1]

    include_excluded_scrap = request.args.get("include_excluded_scrap", "false").lower() == "true"
    exclude_material_scrap = request.args.get("exclude_material_scrap", "true").lower() != "false"
    exclude_pb_diode = request.args.get("exclude_pb_diode", "true").lower() != "false"

    try:
        result = apply_view(
            query_id=query_id,
            packages=_parse_multi_param("packages") or None,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            reasons=reasons,
            metric_filter=metric_filter,
            trend_dates=_parse_multi_param("trend_dates") or None,
            detail_reason=detail_reason,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections or None,
            page=page,
            per_page=per_page,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )

        if result is None:
            return jsonify({"success": False, "error": "cache_expired"}), 410

        return jsonify({"success": True, "data": result})

    except MemoryError as exc:
        logger.warning("Reject history view memory guard: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": "視圖查詢失敗"}), 500


@reject_history_bp.route("/api/reject-history/export-cached", methods=["GET"])
def api_reject_history_export_cached():
    """Export CSV from cached dataset."""
    query_id = request.args.get("query_id", "").strip()
    if not query_id:
        return jsonify({"success": False, "error": "缺少必要參數: query_id"}), 400

    metric_filter = request.args.get("metric_filter", "all").strip().lower() or "all"
    reasons = _parse_multi_param("reasons") or None
    detail_reason = request.args.get("detail_reason", "").strip() or None
    pareto_selections = _parse_multi_pareto_selections()
    pareto_dimension = None
    pareto_values = None
    if not pareto_selections:
        pareto_error, pareto_dimension, pareto_values = _parse_pareto_selection()
        if pareto_error:
            return jsonify(pareto_error[0]), pareto_error[1]

    include_excluded_scrap = request.args.get("include_excluded_scrap", "false").lower() == "true"
    exclude_material_scrap = request.args.get("exclude_material_scrap", "true").lower() != "false"
    exclude_pb_diode = request.args.get("exclude_pb_diode", "true").lower() != "false"

    try:
        rows = export_csv_from_cache(
            query_id=query_id,
            packages=_parse_multi_param("packages") or None,
            workcenter_groups=_parse_multi_param("workcenter_groups") or None,
            reasons=reasons,
            metric_filter=metric_filter,
            trend_dates=_parse_multi_param("trend_dates") or None,
            detail_reason=detail_reason,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )

        if rows is None:
            return jsonify({"success": False, "error": "cache_expired"}), 410

        headers = [
            "LOT", "WORKCENTER", "WORKCENTER_GROUP", "Package", "FUNCTION",
            "TYPE", "WORKFLOW", "PRODUCT", "原因", "EQUIPMENT", "COMMENT", "SPEC",
            "REJECT_QTY", "STANDBY_QTY", "QTYTOPROCESS_QTY", "INPROCESS_QTY",
            "PROCESSED_QTY", "扣帳報廢量", "不扣帳報廢量", "MOVEIN_QTY",
            "報廢時間", "日期",
        ]
        return Response(
            _list_to_csv(rows, headers=headers),
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=reject_history_export.csv",
                "Content-Type": "text/csv; charset=utf-8-sig",
            },
        )

    except MemoryError as exc:
        logger.warning("Reject history export-cached memory guard: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "error": "匯出 CSV 失敗"}), 500
