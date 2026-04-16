# -*- coding: utf-8 -*-
"""Reject-history page API routes."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from flask import Blueprint, Response, request

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.response import (
    success_response,
    validation_error,
    not_found_error,
    internal_error,
    cache_expired_error,
    cache_miss_error,
    error_response,
    VALIDATION_ERROR,
    SERVICE_UNAVAILABLE,
)
from mes_dashboard.core.heavy_query_telemetry import record_memory_error
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.utils import parse_bool_query
from mes_dashboard.services.reject_dataset_cache import (
    apply_view,
    compute_batch_pareto,
    compute_dimension_pareto,
    execute_primary_query,
    export_csv_from_cache,
    _has_cached_df,
    _make_query_id,
    _CACHE_SCHEMA_VERSION,
)
from mes_dashboard.services.reject_history_service import (
    _list_to_csv,
    export_csv,
    get_filter_options,
    query_analytics,
    query_list,
    query_row_count,
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
_REJECT_HISTORY_OVERLOAD_RETRY_AFTER_SECONDS = max(
    1,
    int(os.getenv("REJECT_HISTORY_OVERLOAD_RETRY_AFTER_SECONDS", "30")),
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

_REJECT_HISTORY_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket="reject-history-query",
    max_attempts_env="REJECT_HISTORY_QUERY_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="REJECT_HISTORY_QUERY_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)

_REJECT_HISTORY_JOB_RATE_LIMIT = configured_rate_limit(
    bucket="reject-history-job",
    max_attempts_env="REJECT_HISTORY_JOB_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="REJECT_HISTORY_JOB_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
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


def _get_request_args() -> dict:
    """Return request params from JSON body (POST) or query string (GET)."""
    if request.method == 'POST':
        return request.get_json(silent=True) or {}
    return request.args


def _parse_multi_param(name: str, args=None) -> list[str]:
    source = args if args is not None else request.args
    values = []
    # Use getlist() for MultiDict (GET query string); plain dict comes from POST JSON body.
    if hasattr(source, 'getlist'):
        for raw in source.getlist(name):
            for token in str(raw).split(","):
                item = token.strip()
                if item:
                    values.append(item)
    else:
        raw_value = source.get(name)
        if isinstance(raw_value, list):
            for item in raw_value:
                token = str(item).strip()
                if token:
                    values.append(token)
        elif raw_value is not None:
            for token in str(raw_value).split(","):
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


def _overload_error(message: str):
    retry_after = _REJECT_HISTORY_OVERLOAD_RETRY_AFTER_SECONDS
    return error_response(
        SERVICE_UNAVAILABLE,
        message,
        status_code=503,
        meta={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


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
}
_PARETO_SELECTION_PARAMS = {
    "reason": "sel_reason",
    "package": "sel_package",
    "type": "sel_type",
}
_REJECT_PARETO_SCOPE_FIXED = "top80"
_REJECT_BATCH_PARETO_DISPLAY_SCOPE_FIXED = "top20"


def _parse_common_bools(args=None) -> tuple[Optional[tuple[dict, int]], bool, bool, bool]:
    """Parse include_excluded_scrap, exclude_material_scrap, exclude_pb_diode."""
    source = args if args is not None else request.args
    for name in ("include_excluded_scrap", "exclude_material_scrap", "exclude_pb_diode"):
        raw_val = source.get(name, "") if isinstance(source, dict) else source.get(name, "")
        if isinstance(raw_val, bool):
            continue
        raw = str(raw_val or "").strip().lower()
        if raw not in _VALID_BOOL_STRINGS:
            return ({"success": False, "error": f"Invalid {name}, use true/false"}, 400), False, True, True

    def _get_bool(name, default_str):
        raw_val = source.get(name, None) if isinstance(source, dict) else source.get(name, None)
        if isinstance(raw_val, bool):
            return raw_val
        if raw_val is None:
            return parse_bool_query(default_str, default=(default_str.lower() not in ("false", "0", "no", "n", "off", "")))
        return parse_bool_query(str(raw_val), default=False)

    include_excluded_scrap = _get_bool("include_excluded_scrap", "")
    exclude_material_scrap = _get_bool("exclude_material_scrap", "true")
    exclude_pb_diode = _get_bool("exclude_pb_diode", "true")
    return None, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode


def _parse_pareto_selection(args=None) -> tuple[Optional[tuple[dict, int]], Optional[str], Optional[list[str]]]:
    source = args if args is not None else request.args
    raw_dim = source.get("pareto_dimension", "")
    pareto_dimension = str(raw_dim).strip().lower() if raw_dim else ""
    pareto_values = _parse_multi_param("pareto_values", args)
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


def _parse_multi_pareto_selections(args=None) -> dict[str, list[str]]:
    selections: dict[str, list[str]] = {}
    for dim, param_name in _PARETO_SELECTION_PARAMS.items():
        values = _parse_multi_param(param_name, args)
        if values:
            selections[dim] = values
    return selections


@reject_history_bp.route("/api/reject-history/options", methods=["GET"])
def api_reject_history_options():
    start_date, end_date, date_error = _parse_date_range(required=False)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return success_response(cached_payload.get("data", cached_payload), meta=cached_payload.get("meta"))

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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢篩選選項失敗")


@reject_history_bp.route("/api/reject-history/summary", methods=["GET"])
def api_reject_history_summary():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢摘要資料失敗")


@reject_history_bp.route("/api/reject-history/trend", methods=["GET"])
def api_reject_history_trend():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢趨勢資料失敗")


@reject_history_bp.route("/api/reject-history/reason-pareto", methods=["GET"])
def api_reject_history_reason_pareto():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
                return success_response(result, meta=pareto_meta)
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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except MemoryError as exc:
        logger.warning("Reject history reason-pareto memory guard: %s", exc)
        record_memory_error("reject_history.dimension_pareto", reason="rss_guard")
        return _overload_error(str(exc))
    except Exception:
        return internal_error("查詢柏拉圖資料失敗")


@reject_history_bp.route("/api/reject-history/batch-pareto", methods=["GET", "POST"])
def api_reject_history_batch_pareto():
    """Batch pareto view: compute all dimensions from cache only."""
    args = _get_request_args()
    query_id = args.get("query_id", "")
    if isinstance(query_id, str):
        query_id = query_id.strip()
    if not query_id:
        return validation_error("缺少必要參數: query_id")

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools(args)
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

    raw_metric = args.get("metric_mode", "reject_total")
    metric_mode = str(raw_metric).strip().lower() or "reject_total"
    pareto_scope = _REJECT_PARETO_SCOPE_FIXED
    pareto_display_scope = _REJECT_BATCH_PARETO_DISPLAY_SCOPE_FIXED

    try:
        result = compute_batch_pareto(
            query_id=query_id,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
            pareto_display_scope=pareto_display_scope,
            packages=_parse_multi_param("packages", args) or None,
            workcenter_groups=_parse_multi_param("workcenter_groups", args) or None,
            reasons=_parse_multi_param("reasons", args) or None,
            trend_dates=_parse_multi_param("trend_dates", args) or None,
            pareto_selections=_parse_multi_pareto_selections(args),
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )
        if result is None:
            return cache_miss_error()
        pareto_meta = result.pop("_pareto_meta", None)
        return success_response(result, meta=pareto_meta)
    except MemoryError as exc:
        logger.warning("Reject history batch-pareto memory guard: %s", exc)
        record_memory_error("reject_history.batch_pareto", reason="rss_guard")
        return _overload_error(str(exc))
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢批次柏拉圖失敗")


@reject_history_bp.route("/api/reject-history/list", methods=["GET"])
@_REJECT_HISTORY_LIST_RATE_LIMIT
def api_reject_history_list():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢明細資料失敗")


@reject_history_bp.route("/api/reject-history/export", methods=["GET"])
@_REJECT_HISTORY_EXPORT_RATE_LIMIT
def api_reject_history_export():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return validation_error(str(exc))
    except Exception:
        return internal_error("匯出 CSV 失敗")


@reject_history_bp.route("/api/reject-history/analytics", methods=["GET"])
def api_reject_history_analytics():
    start_date, end_date, date_error = _parse_date_range(required=True)
    if date_error:
        return validation_error(date_error[0].get("error", "日期格式錯誤"))

    bool_error, include_excluded_scrap, exclude_material_scrap, exclude_pb_diode = _parse_common_bools()
    if bool_error:
        return validation_error(bool_error[0].get("error", "參數格式錯誤"))

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
        return success_response(data, meta=meta)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("查詢分析資料失敗")


# ============================================================
# Two-phase query endpoints (POST /query, GET /view)
# ============================================================


@reject_history_bp.route("/api/reject-history/query", methods=["POST"])
@_REJECT_HISTORY_QUERY_RATE_LIMIT
def api_reject_history_query():
    """Primary query: execute Oracle → cache DataFrame → return results.

    Supports two response codes:
      200 - existing cached/spooled result served immediately
      202 - spool miss enqueued to RQ for background execution
    """
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    mode = str(body.get("mode", "")).strip()
    if mode not in ("date_range", "container"):
        return validation_error("mode 必須為 date_range 或 container")

    include_excluded_scrap = bool(body.get("include_excluded_scrap", False))
    exclude_material_scrap = bool(body.get("exclude_material_scrap", True))
    exclude_pb_diode = bool(body.get("exclude_pb_diode", True))

    # Parse mode-specific params
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    if mode == "date_range":
        start_date = str(body.get("start_date", "")).strip()
        end_date = str(body.get("end_date", "")).strip()
        if not start_date or not end_date:
            return validation_error("date_range mode 需要 start_date 和 end_date")
        date_range_error = _validate_primary_query_date_range(start_date, end_date)
        if date_range_error:
            return validation_error(date_range_error)

    container_input_type: Optional[str] = None
    container_values: list[str] = []
    if mode == "container":
        container_input_type = str(body.get("container_input_type", "lot")).strip()
        raw_container_values = body.get("container_values", [])
        if not isinstance(raw_container_values, list) or not raw_container_values:
            return validation_error("container mode 需要 container_values 陣列")
        container_values = [str(v).strip() for v in raw_container_values if str(v).strip()]

    _query_id_input = {
        "cache_schema_version": _CACHE_SCHEMA_VERSION,
        "mode": mode,
        "start_date": start_date,
        "end_date": end_date,
        "container_input_type": container_input_type,
        "container_values": sorted(container_values),
    }
    _pre_query_id = _make_query_id(_query_id_input)

    if _has_cached_df(_pre_query_id):
        try:
            result = execute_primary_query(
                mode=mode,
                start_date=start_date,
                end_date=end_date,
                container_input_type=container_input_type,
                container_values=container_values or None,
                include_excluded_scrap=include_excluded_scrap,
                exclude_material_scrap=exclude_material_scrap,
                exclude_pb_diode=exclude_pb_diode,
            )
            return success_response(result)
        except ValueError as exc:
            return validation_error(str(exc))
        except MemoryError as exc:
            record_memory_error("reject_history.query", reason="rss_guard")
            return _overload_error(str(exc))
        except Exception:
            import traceback
            traceback.print_exc()
            return internal_error("主查詢執行失敗")

    try:
        from mes_dashboard.services.reject_query_job_service import enqueue_reject_query

        job_params = {
            "include_excluded_scrap": include_excluded_scrap,
            "exclude_material_scrap": exclude_material_scrap,
            "exclude_pb_diode": exclude_pb_diode,
            "start_date": start_date,
            "end_date": end_date,
        }

        if mode == "container":
            job_params["container_input_type"] = container_input_type
            job_params["container_values"] = container_values

        from mes_dashboard.core.permissions import get_owner_token
        job_id, err = enqueue_reject_query(mode, job_params, owner=get_owner_token())
        if job_id is None:
            logger.warning("reject async enqueue failed (%s)", err)
            return error_response(
                SERVICE_UNAVAILABLE,
                "背景查詢服務不可用，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": _REJECT_HISTORY_OVERLOAD_RETRY_AFTER_SECONDS},
                headers={"Retry-After": str(_REJECT_HISTORY_OVERLOAD_RETRY_AFTER_SECONDS)},
            )

        return success_response(
            {
                "async": True,
                "job_id": job_id,
                "status_url": f"/api/reject-history/job/{job_id}",
                "query_id": _pre_query_id,
            },
            status_code=202,
        )

    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        import traceback
        traceback.print_exc()
        return internal_error("主查詢執行失敗")


@reject_history_bp.route("/api/reject-history/count", methods=["GET"])
def api_reject_history_count():
    """Row-count baseline for data integrity probes.

    Returns COUNT(*) for the given date range using the same default filters
    as the primary list query.  Intended for stress/integrity test use only.
    """
    start_date, end_date, err = _parse_date_range()
    if err:
        return err
    try:
        count = query_row_count(start_date=start_date, end_date=end_date)
        return success_response({"count": count})
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("count query failed")


@reject_history_bp.route("/api/reject-history/job/<job_id>", methods=["GET"])
@_REJECT_HISTORY_JOB_RATE_LIMIT
def api_reject_history_job_status(job_id: str):
    """Get async query job status."""
    from mes_dashboard.services.async_query_job_service import get_job_status
    status = get_job_status("reject", job_id)
    if status is None:
        return not_found_error("Job not found")
    return success_response(status)


_REJECT_SPOOL_DOWNLOAD_THRESHOLD = int(os.environ.get("REJECT_SPOOL_THRESHOLD", "5000"))
_REJECT_SPOOL_NAMESPACE = "reject_dataset"


def _inject_reject_spool_info(data: dict, query_id: str) -> None:
    """Add spool_download_url and total_row_count for large reject datasets."""
    try:
        from mes_dashboard.core.query_spool_store import get_spool_metadata
        metadata = get_spool_metadata(_REJECT_SPOOL_NAMESPACE, query_id)
        if metadata is None:
            return
        row_count = int(metadata.get("row_count") or 0)
        data["total_row_count"] = row_count
        if row_count >= _REJECT_SPOOL_DOWNLOAD_THRESHOLD:
            data["spool_download_url"] = (
                f"/api/spool/{_REJECT_SPOOL_NAMESPACE}/{query_id}.parquet"
            )
    except Exception:
        pass


@reject_history_bp.route("/api/reject-history/view", methods=["GET", "POST"])
def api_reject_history_view():
    """Supplementary view: read cache → filter → return derived data."""
    args = _get_request_args()
    query_id = args.get("query_id", "")
    if isinstance(query_id, str):
        query_id = query_id.strip()
    if not query_id:
        return validation_error("缺少必要參數: query_id")

    try:
        page = int(args.get("page", 1) or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(args.get("per_page", 50) or 50)
    except (TypeError, ValueError):
        per_page = 50
    raw_metric = args.get("metric_filter", "all")
    metric_filter = str(raw_metric).strip().lower() or "all"
    reasons = _parse_multi_param("reasons", args) or None
    raw_dr = args.get("detail_reason", "")
    detail_reason = str(raw_dr).strip() or None if raw_dr else None
    pareto_selections = _parse_multi_pareto_selections(args)
    pareto_dimension = None
    pareto_values = None
    if not pareto_selections:
        pareto_error, pareto_dimension, pareto_values = _parse_pareto_selection(args)
        if pareto_error:
            return validation_error(pareto_error[0].get("error", "查詢失敗"))

    def _get_bool_simple(name, default_true):
        raw_val = args.get(name)
        if isinstance(raw_val, bool):
            return raw_val
        if raw_val is None:
            return default_true
        return str(raw_val).lower() not in ("false", "0", "no", "n", "off") if default_true else str(raw_val).lower() in ("true", "1", "yes", "y", "on")

    include_excluded_scrap = _get_bool_simple("include_excluded_scrap", False)
    exclude_material_scrap = _get_bool_simple("exclude_material_scrap", True)
    exclude_pb_diode = _get_bool_simple("exclude_pb_diode", True)

    try:
        result = apply_view(
            query_id=query_id,
            packages=_parse_multi_param("packages", args) or None,
            workcenter_groups=_parse_multi_param("workcenter_groups", args) or None,
            reasons=reasons,
            metric_filter=metric_filter,
            trend_dates=_parse_multi_param("trend_dates", args) or None,
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
            return cache_expired_error()

        # Task 8.1: Inject spool_download_url + total_row_count for large datasets
        _inject_reject_spool_info(result, query_id)

        return success_response(result)

    except MemoryError as exc:
        logger.warning("Reject history view memory guard: %s", exc)
        record_memory_error("reject_history.view", reason="rss_guard")
        return _overload_error(str(exc))
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        import traceback
        traceback.print_exc()
        return internal_error("視圖查詢失敗")


@reject_history_bp.route("/api/reject-history/export-cached", methods=["GET", "POST"])
def api_reject_history_export_cached():
    """Export CSV from cached dataset. Accepts GET (query params) or POST (JSON body)."""
    args = _get_request_args()

    query_id = args.get("query_id", "")
    if isinstance(query_id, str):
        query_id = query_id.strip()
    if not query_id:
        return validation_error("缺少必要參數: query_id")

    raw_metric = args.get("metric_filter", "all")
    metric_filter = str(raw_metric).strip().lower() or "all"
    reasons = _parse_multi_param("reasons", args) or None
    raw_dr = args.get("detail_reason", "")
    detail_reason = str(raw_dr).strip() or None if raw_dr else None
    pareto_selections = _parse_multi_pareto_selections(args)
    pareto_dimension = None
    pareto_values = None
    if not pareto_selections:
        pareto_error, pareto_dimension, pareto_values = _parse_pareto_selection(args)
        if pareto_error:
            return validation_error(pareto_error[0].get("error", "查詢失敗"))

    def _get_bool_simple(name, default_true):
        raw_val = args.get(name)
        if isinstance(raw_val, bool):
            return raw_val
        if raw_val is None:
            return default_true
        return str(raw_val).lower() not in ("false", "0", "no", "n", "off") if default_true else str(raw_val).lower() in ("true", "1", "yes", "y", "on")

    include_excluded_scrap = _get_bool_simple("include_excluded_scrap", False)
    exclude_material_scrap = _get_bool_simple("exclude_material_scrap", True)
    exclude_pb_diode = _get_bool_simple("exclude_pb_diode", True)

    try:
        rows = export_csv_from_cache(
            query_id=query_id,
            packages=_parse_multi_param("packages", args) or None,
            workcenter_groups=_parse_multi_param("workcenter_groups", args) or None,
            reasons=reasons,
            metric_filter=metric_filter,
            trend_dates=_parse_multi_param("trend_dates", args) or None,
            detail_reason=detail_reason,
            pareto_dimension=pareto_dimension,
            pareto_values=pareto_values,
            pareto_selections=pareto_selections or None,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
        )

        if rows is None:
            return cache_expired_error()

        headers = [
            "LOT", "WORKCENTER", "WORKCENTER_GROUP", "Package", "FUNCTION",
            "TYPE", "PRODUCT", "原因", "EQUIPMENT", "COMMENT", "SPEC",
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
        record_memory_error("reject_history.export_cached", reason="rss_guard")
        return _overload_error(str(exc))
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        return internal_error("匯出 CSV 失敗")
