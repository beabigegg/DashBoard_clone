# -*- coding: utf-8 -*-
"""Mid-Section Defect Traceability Analysis API routes.

Reverse traceability from TMTT (test) station back to upstream production stations.
"""

from flask import Blueprint, jsonify, request, Response

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.mid_section_defect_service import (
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
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


@mid_section_defect_bp.route('/analysis', methods=['GET'])
@_ANALYSIS_RATE_LIMIT
def api_analysis():
    """API: Get mid-section defect traceability analysis (summary).

    Returns kpi, charts, daily_trend, available_loss_reasons, genealogy_status,
    and detail_total_count.  Does NOT include the detail array — use
    /analysis/detail for paginated detail data.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required
        loss_reasons: Comma-separated loss reason names, optional
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    loss_reasons_str = request.args.get('loss_reasons', '')
    loss_reasons = [r.strip() for r in loss_reasons_str.split(',') if r.strip()] or None

    result = query_analysis(start_date, end_date, loss_reasons)

    if result is None:
        return jsonify({'success': False, 'error': '查詢失敗，請稍後再試'}), 500

    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 400

    # Return summary only (no detail array) to keep response lightweight
    summary = {
        'kpi': result.get('kpi'),
        'charts': result.get('charts'),
        'daily_trend': result.get('daily_trend'),
        'available_loss_reasons': result.get('available_loss_reasons'),
        'genealogy_status': result.get('genealogy_status'),
        'detail_total_count': len(result.get('detail', [])),
    }

    return jsonify({'success': True, 'data': summary})


@mid_section_defect_bp.route('/analysis/detail', methods=['GET'])
@_DETAIL_RATE_LIMIT
def api_analysis_detail():
    """API: Get paginated detail table for mid-section defect analysis.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required
        loss_reasons: Comma-separated loss reason names, optional
        page: Page number (default 1)
        page_size: Records per page (default 200, max 500)
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    loss_reasons_str = request.args.get('loss_reasons', '')
    loss_reasons = [r.strip() for r in loss_reasons_str.split(',') if r.strip()] or None

    page = max(request.args.get('page', 1, type=int), 1)
    page_size = max(1, min(request.args.get('page_size', 200, type=int), 500))

    result = query_analysis_detail(
        start_date, end_date, loss_reasons,
        page=page, page_size=page_size,
    )

    if result is None:
        return jsonify({'success': False, 'error': '查詢失敗，請稍後再試'}), 500

    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 400

    return jsonify({'success': True, 'data': result})


@mid_section_defect_bp.route('/loss-reasons', methods=['GET'])
def api_loss_reasons():
    """API: Get all TMTT loss reasons (cached daily).

    No parameters required — returns all loss reasons from last 180 days,
    cached in Redis with 24h TTL for instant dropdown population.

    Returns:
        JSON with loss_reasons list.
    """
    result = query_all_loss_reasons()

    if result is None:
        return jsonify({'success': False, 'error': '查詢失敗，請稍後再試'}), 500

    return jsonify({'success': True, 'data': result})


@mid_section_defect_bp.route('/export', methods=['GET'])
@_EXPORT_RATE_LIMIT
def api_export():
    """API: Export mid-section defect detail data as CSV.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required
        loss_reasons: Comma-separated loss reason names, optional

    Returns:
        CSV file download.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    loss_reasons_str = request.args.get('loss_reasons', '')
    loss_reasons = [r.strip() for r in loss_reasons_str.split(',') if r.strip()] or None

    filename = f"mid_section_defect_{start_date}_to_{end_date}.csv"

    return Response(
        export_csv(start_date, end_date, loss_reasons),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
