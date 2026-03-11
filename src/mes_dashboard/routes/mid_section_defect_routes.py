# -*- coding: utf-8 -*-
"""Defect Traceability Analysis API routes.

Bidirectional traceability from any detection station to upstream/downstream.
"""

from flask import Blueprint, request, Response

from mes_dashboard.core.response import success_response, validation_error, internal_error
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.mid_section_defect_service import (
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
    query_station_options,
    export_csv,
)

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

    result = query_analysis(start_date, end_date, loss_reasons, station, direction)

    if result is None:
        return internal_error('查詢失敗，請稍後再試')

    if 'error' in result:
        return validation_error(result['error'])

    summary = {
        'kpi': result.get('kpi'),
        'charts': result.get('charts'),
        'daily_trend': result.get('daily_trend'),
        'available_loss_reasons': result.get('available_loss_reasons'),
        'genealogy_status': result.get('genealogy_status'),
        'detail_total_count': len(result.get('detail', [])),
        'attribution': result.get('attribution', []),
    }

    return success_response(summary)


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
