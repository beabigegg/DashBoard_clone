# -*- coding: utf-8 -*-
"""TMTT Defect Analysis API routes.

Contains Flask Blueprint for TMTT printing & lead form defect analysis endpoints.
"""

from flask import Blueprint, jsonify, request, Response

from mes_dashboard.services.tmtt_defect_service import (
    query_tmtt_defect_analysis,
    export_csv,
)

# Create Blueprint
tmtt_defect_bp = Blueprint(
    'tmtt_defect',
    __name__,
    url_prefix='/api/tmtt-defect'
)


@tmtt_defect_bp.route('/analysis', methods=['GET'])
def api_tmtt_defect_analysis():
    """API: Get TMTT defect analysis data (KPI + charts + detail).

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required

    Returns:
        JSON with kpi, charts, detail sections.
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    result = query_tmtt_defect_analysis(start_date, end_date)

    if result is None:
        return jsonify({'success': False, 'error': '查詢失敗，請稍後再試'}), 500

    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 400

    return jsonify({'success': True, 'data': result})


@tmtt_defect_bp.route('/export', methods=['GET'])
def api_tmtt_defect_export():
    """API: Export TMTT defect detail data as CSV.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD), required
        end_date: End date (YYYY-MM-DD), required

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

    filename = f"tmtt_defect_{start_date}_to_{end_date}.csv"

    return Response(
        export_csv(start_date, end_date),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
