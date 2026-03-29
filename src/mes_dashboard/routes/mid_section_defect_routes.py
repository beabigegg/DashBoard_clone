# -*- coding: utf-8 -*-
"""Defect Traceability Analysis API routes.

Bidirectional traceability from any detection station to upstream/downstream.
"""

import logging

from flask import Blueprint, request, Response

from mes_dashboard.core.response import (
    success_response,
    validation_error,
    internal_error,
    error_response,
    cache_expired_error,
)
from mes_dashboard.core.cache import cache_get, make_cache_key
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.mid_section_defect_service import (
    resolve_analysis_trace_context,
    query_analysis,
    query_all_loss_reasons,
    query_station_options,
)

logger = logging.getLogger('mes_dashboard.mid_section_defect_routes')

mid_section_defect_bp = Blueprint(
    'mid_section_defect',
    __name__,
    url_prefix='/api/mid-section-defect'
)
_ANALYSIS_RATE_LIMIT = configured_rate_limit(
    bucket="mid-section-defect-analysis",
    max_attempts_env="MID_SECTION_DEFECT_ANALYSIS_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="MID_SECTION_DEFECT_ANALYSIS_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=6,
    default_window_seconds=60,
)

_DETAIL_RATE_LIMIT = configured_rate_limit(
    bucket="mid-section-defect-analysis-detail",
    max_attempts_env="MID_SECTION_DEFECT_DETAIL_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="MID_SECTION_DEFECT_DETAIL_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=15,
    default_window_seconds=60,
)

_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="mid-section-defect-export",
    max_attempts_env="MID_SECTION_DEFECT_EXPORT_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="MID_SECTION_DEFECT_EXPORT_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=3,
    default_window_seconds=60,
)


def _parse_common_params():
    """Extract common query params (dates, loss_reasons, station, direction)."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    loss_reasons_str = request.args.get('loss_reasons', '')
    loss_reasons = [r.strip() for r in loss_reasons_str.split(',') if r.strip()] or None
    station = request.args.get('station', '測試')
    direction = request.args.get('direction', 'backward')
    return start_date, end_date, loss_reasons, station, direction


def _analysis_cache_key(
    start_date: str,
    end_date: str,
    station: str,
    direction: str,
    loss_reasons,
) -> str:
    return make_cache_key(
        "mid_section_defect",
        filters={
            "start_date": start_date,
            "end_date": end_date,
            "loss_reasons": sorted(loss_reasons) if loss_reasons else None,
            "station": station,
            "direction": direction,
        },
    )


def _build_summary_payload(result: dict) -> dict:
    return {
        'kpi': result.get('kpi'),
        'charts': result.get('charts'),
        'daily_trend': result.get('daily_trend'),
        'available_loss_reasons': result.get('available_loss_reasons'),
        'genealogy_status': result.get('genealogy_status'),
        'detail_total_count': len(result.get('detail', [])),
        'attribution': result.get('attribution', []),
        'trace_query_id': result.get('trace_query_id'),
    }


@mid_section_defect_bp.route('/station-options', methods=['GET'])
def api_station_options():
    """API: Get available detection station options for dropdown."""
    return success_response(query_station_options())


@mid_section_defect_bp.route('/analysis', methods=['GET'])
@_ANALYSIS_RATE_LIMIT
def api_analysis():
    """API: Compatibility adapter for defect traceability analysis (summary).

    This endpoint is retained as a compatibility adapter while MSD migrates to
    the staged trace + spool + DuckDB pipeline (task 5.5).  Do NOT remove until
    all consumers (frontend, AI registry, tests, api_inventory.md) are migrated.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required
        loss_reasons: Comma-separated loss reason names, optional
        station: Detection station workcenter group (default '測試')
        direction: 'backward' or 'forward' (default 'backward')
    """
    start_date, end_date, loss_reasons, station, direction = _parse_common_params()

    if not start_date or not end_date:
        return validation_error('必須提供 start_date 和 end_date 參數')

    cache_key = _analysis_cache_key(
        start_date=start_date,
        end_date=end_date,
        station=station,
        direction=direction,
        loss_reasons=loss_reasons,
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return success_response(_build_summary_payload(cached))

    result = query_analysis(start_date, end_date, loss_reasons, station, direction)

    if result is None:
        return internal_error('查詢失敗，請稍後再試')

    if 'error' in result:
        return validation_error(result['error'])

    return success_response(_build_summary_payload(result))


@mid_section_defect_bp.route('/analysis/detail', methods=['GET'])
@_DETAIL_RATE_LIMIT
def api_analysis_detail():
    """API: Get paginated detail table for defect traceability analysis.

    Query Parameters:
        trace_query_id: Canonical spool id from a previous MSD query (preferred)
        start_date, end_date, loss_reasons, station, direction (same as /analysis)
        page: Page number (default 1)
        page_size: Records per page (default 200, max 500)
        sort_by: Column to sort by (default defect_rate)
        order: asc or desc (default desc)
    """
    # Task 5.3 / 6.5: resolve canonical trace_query_id first, then serve from spool.
    trace_query_id = request.args.get("trace_query_id", "").strip() or None
    start_date, end_date, loss_reasons, station, direction = _parse_common_params()
    if not trace_query_id:
        if not start_date or not end_date:
            return validation_error('必須提供 start_date 和 end_date 參數')
        context = resolve_analysis_trace_context(
            start_date=start_date,
            end_date=end_date,
            station=station,
            direction=direction,
        )
        if context is None:
            return internal_error('查詢失敗，請稍後再試')
        if 'error' in context:
            return validation_error(context['error'])
        trace_query_id = context.get("trace_query_id")
        if not context.get("seed_container_ids"):
            return success_response({
                "detail": [],
                "pagination": {
                    "page": max(request.args.get("page", 1, type=int), 1),
                    "page_size": max(1, min(request.args.get("page_size", 200, type=int), 500)),
                    "total_count": 0,
                    "total_pages": 1,
                },
                "trace_query_id": trace_query_id,
            })

    if trace_query_id:
        try:
            from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
            page = max(request.args.get("page", 1, type=int), 1)
            per_page = max(1, min(request.args.get("page_size", 200, type=int), 500))
            sort_by = request.args.get("sort_by", "defect_rate")
            order = request.args.get("order", "desc")
            rt = MsdDuckdbRuntime(trace_query_id)
            if rt.is_available():
                detail = rt.get_detail(page=page, per_page=per_page, sort_by=sort_by, order=order)
                if detail is not None:
                    pagination = detail.get("pagination") or {}
                    return success_response({
                        "detail": detail.get("items") or [],
                        "pagination": {
                            "page": pagination.get("page", page),
                            "page_size": pagination.get("per_page", per_page),
                            "total_count": pagination.get("total", 0),
                            "total_pages": pagination.get("total_pages", 1),
                        },
                        "trace_query_id": detail.get("trace_query_id") or trace_query_id,
                    })
        except Exception as exc:
            logger.warning("detail spool path failed (trace_query_id=%s): %s", trace_query_id, exc)
        return cache_expired_error()

    return internal_error('查詢失敗，請稍後再試')


@mid_section_defect_bp.route('/loss-reasons', methods=['GET'])
def api_loss_reasons():
    """API: Get all loss reasons (cached daily)."""
    result = query_all_loss_reasons()

    if result is None:
        return internal_error('查詢失敗，請稍後再試')

    return success_response(result)


@mid_section_defect_bp.route('/export', methods=['GET'])
@_EXPORT_RATE_LIMIT
def api_export():
    """API: Export defect traceability detail data as CSV.

    Query Parameters:
        trace_query_id: Canonical spool id from a previous MSD query (preferred)
        start_date, end_date, loss_reasons, station, direction (same as /analysis)
    """
    # Task 5.4 / 6.5: resolve canonical trace_query_id first, then stream from spool.
    trace_query_id = request.args.get("trace_query_id", "").strip() or None
    start_date, end_date, loss_reasons, station, direction = _parse_common_params()
    if not trace_query_id:
        if not start_date or not end_date:
            return validation_error('必須提供 start_date 和 end_date 參數')
        context = resolve_analysis_trace_context(
            start_date=start_date,
            end_date=end_date,
            station=station,
            direction=direction,
        )
        if context is None:
            return internal_error('查詢失敗，請稍後再試')
        if 'error' in context:
            return validation_error(context['error'])
        trace_query_id = context.get("trace_query_id")

    if trace_query_id:
        try:
            from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
            rt = MsdDuckdbRuntime(trace_query_id)
            if rt.is_available():
                filename = f"defect_trace_{trace_query_id}.csv"
                return Response(
                    rt.export_csv(),
                    mimetype="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "Content-Type": "text/csv; charset=utf-8-sig",
                    },
                )
        except Exception as exc:
            logger.warning("export spool path failed (trace_query_id=%s): %s", trace_query_id, exc)
        return cache_expired_error()

    return internal_error('查詢失敗，請稍後再試')
