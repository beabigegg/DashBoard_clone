# -*- coding: utf-8 -*-
"""Defect Traceability Analysis API routes.

Bidirectional traceability from any detection station to upstream/downstream.
"""

import logging
import os

from flask import Blueprint, request, Response

from mes_dashboard.core.response import (
    success_response,
    validation_error,
    internal_error,
    error_response,
    not_found_error,
    SERVICE_UNAVAILABLE,
)
from mes_dashboard.core.cache import cache_get, make_cache_key
from mes_dashboard.core.database import get_slow_query_active_count
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.async_query_job_service import is_async_available
from mes_dashboard.services.mid_section_defect_service import (
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
    query_station_options,
    export_csv,
)
from mes_dashboard.services.msd_query_job_service import (
    enqueue_msd_analysis,
    get_msd_job_result,
    get_msd_job_status,
)

logger = logging.getLogger('mes_dashboard.mid_section_defect_routes')

mid_section_defect_bp = Blueprint(
    'mid_section_defect',
    __name__,
    url_prefix='/api/mid-section-defect'
)

_HEAVY_QUERY_REJECT_THRESHOLD = max(1, int(os.getenv("HEAVY_QUERY_REJECT_THRESHOLD", "4")))

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
    }


@mid_section_defect_bp.route('/station-options', methods=['GET'])
def api_station_options():
    """API: Get available detection station options for dropdown."""
    return success_response(query_station_options())


@mid_section_defect_bp.route('/analysis', methods=['GET'])
@_ANALYSIS_RATE_LIMIT
def api_analysis():
    """API: Get defect traceability analysis (summary).

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

    if is_async_available():
        job_id, err = enqueue_msd_analysis(
            start_date=start_date,
            end_date=end_date,
            station=station,
            direction=direction,
            loss_reasons=loss_reasons,
        )
        if job_id is not None:
            return success_response(
                {
                    "async": True,
                    "job_id": job_id,
                    "status_url": f"/api/mid-section-defect/analysis/job/{job_id}",
                },
                status_code=202,
            )
        # Enqueue failure falls back to sync execution.
        if err:
            logger.warning("msd async enqueue failed, fallback to sync: %s", err)

    # Phase 0: concurrency fast-rejection (sync fallback path only)
    try:
        if get_slow_query_active_count() >= _HEAVY_QUERY_REJECT_THRESHOLD:
            return error_response(
                SERVICE_UNAVAILABLE,
                "系統忙碌中，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": 30},
                headers={"Retry-After": "30"},
            )
    except Exception:
        pass

    result = query_analysis(start_date, end_date, loss_reasons, station, direction)

    if result is None:
        return internal_error('查詢失敗，請稍後再試')

    if 'error' in result:
        return validation_error(result['error'])

    return success_response(_build_summary_payload(result))


@mid_section_defect_bp.route('/analysis/job/<job_id>', methods=['GET'])
def api_analysis_job_status(job_id: str):
    status = get_msd_job_status(job_id)
    if status is None:
        return not_found_error("job not found or expired")
    return success_response(status)


@mid_section_defect_bp.route('/analysis/job/<job_id>/result', methods=['GET'])
def api_analysis_job_result(job_id: str):
    status = get_msd_job_status(job_id)
    if status is None:
        return not_found_error("job not found or expired")

    if status.get("status") != "completed":
        return error_response(
            "JOB_NOT_COMPLETE",
            "job has not completed yet",
            status_code=409,
            meta={"job_status": status.get("status")},
        )

    result = get_msd_job_result(job_id)
    if result is None:
        return not_found_error("job result expired")

    return success_response(_build_summary_payload(result))


@mid_section_defect_bp.route('/analysis/detail', methods=['GET'])
@_DETAIL_RATE_LIMIT
def api_analysis_detail():
    """API: Get paginated detail table for defect traceability analysis.

    Query Parameters:
        start_date, end_date, loss_reasons, station, direction (same as /analysis)
        page: Page number (default 1)
        page_size: Records per page (default 200, max 500)
    """
    start_date, end_date, loss_reasons, station, direction = _parse_common_params()

    if not start_date or not end_date:
        return validation_error('必須提供 start_date 和 end_date 參數')

    page = max(request.args.get('page', 1, type=int), 1)
    page_size = max(1, min(request.args.get('page_size', 200, type=int), 500))

    result = query_analysis_detail(
        start_date, end_date, loss_reasons, station, direction,
        page=page, page_size=page_size,
    )

    if result is None:
        return internal_error('查詢失敗，請稍後再試')

    if 'error' in result:
        return validation_error(result['error'])

    return success_response(result)


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
        start_date, end_date, loss_reasons, station, direction (same as /analysis)
    """
    start_date, end_date, loss_reasons, station, direction = _parse_common_params()

    if not start_date or not end_date:
        return validation_error('必須提供 start_date 和 end_date 參數')

    filename = f"defect_trace_{station}_{direction}_{start_date}_to_{end_date}.csv"

    return Response(
        export_csv(start_date, end_date, loss_reasons, station, direction),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
