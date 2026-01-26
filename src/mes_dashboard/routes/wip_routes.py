# -*- coding: utf-8 -*-
"""WIP API routes for MES Dashboard.

Contains Flask Blueprint for WIP-related API endpoints.
"""

from flask import Blueprint, jsonify, request

from mes_dashboard.services.wip_service import (
    query_wip_summary,
    query_wip_by_spec_workcenter,
    query_wip_by_product_line,
    query_wip_by_status,
    query_wip_by_mfgorder,
    query_wip_distribution_filter_options,
    query_wip_distribution_pivot_columns,
    query_wip_distribution,
)

# Create Blueprint
wip_bp = Blueprint('wip', __name__, url_prefix='/api/wip')


@wip_bp.route('/summary')
def api_wip_summary():
    """API: Current WIP summary."""
    summary = query_wip_summary()
    if summary:
        return jsonify({'success': True, 'data': summary})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/by_spec_workcenter')
def api_wip_by_spec_workcenter():
    """API: Current WIP by spec/workcenter."""
    df = query_wip_by_spec_workcenter()
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data, 'count': len(data)})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/by_product_line')
def api_wip_by_product_line():
    """API: Current WIP by product line."""
    df = query_wip_by_product_line()
    if df is not None:
        data = df.to_dict(orient='records')
        if not df.empty:
            product_line_summary = df.groupby('PRODUCTLINENAME_LEF').agg({
                'LOT_COUNT': 'sum',
                'TOTAL_QTY': 'sum',
                'TOTAL_QTY2': 'sum'
            }).reset_index()
            summary = product_line_summary.to_dict(orient='records')
        else:
            summary = []
        return jsonify({'success': True, 'data': data, 'summary': summary, 'count': len(data)})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/by_status')
def api_wip_by_status():
    """API: Current WIP by status."""
    df = query_wip_by_status()
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/by_mfgorder')
def api_wip_by_mfgorder():
    """API: Current WIP by mfg order (Top N)."""
    limit = request.args.get('limit', 100, type=int)
    df = query_wip_by_mfgorder(limit)
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/distribution/filter_options')
def api_wip_distribution_filter_options():
    """API: Get WIP distribution filter options."""
    days_back = request.args.get('days_back', 90, type=int)
    options = query_wip_distribution_filter_options(days_back)
    if options:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/distribution/pivot_columns', methods=['POST'])
def api_wip_distribution_pivot_columns():
    """API: Get WIP distribution pivot columns."""
    data = request.get_json() or {}
    filters = data.get('filters')
    days_back = data.get('days_back', 90)
    columns = query_wip_distribution_pivot_columns(filters, days_back)
    if columns is not None:
        return jsonify({'success': True, 'data': columns})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/distribution', methods=['POST'])
def api_wip_distribution():
    """API: Query WIP distribution main data."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = min(data.get('limit', 500), 1000)  # Max 1000 records
    offset = data.get('offset', 0)
    days_back = data.get('days_back', 90)

    result = query_wip_distribution(filters, limit, offset, days_back)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
