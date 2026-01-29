# -*- coding: utf-8 -*-
"""Resource (Equipment) API routes for MES Dashboard.

Contains Flask Blueprint for resource/equipment-related API endpoints.
"""

from flask import Blueprint, jsonify, request

from mes_dashboard.core.database import get_db_connection
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.utils import get_days_back
from mes_dashboard.services.resource_service import (
    query_resource_status_summary,
    query_resource_by_status,
    query_resource_by_workcenter,
    query_resource_detail,
    query_resource_workcenter_status_matrix,
    query_resource_filter_options,
)

# Create Blueprint
resource_bp = Blueprint('resource', __name__, url_prefix='/api/resource')


@resource_bp.route('/summary')
def api_resource_summary():
    """API: Resource status summary."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_summary", days_back)
    summary = cache_get(cache_key)
    if summary is None:
        summary = query_resource_status_summary(days_back)
        if summary:
            cache_set(cache_key, summary)
    if summary:
        return jsonify({'success': True, 'data': summary})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/by_status')
def api_resource_by_status():
    """API: Resource count by status."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_status", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_status(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/by_workcenter')
def api_resource_by_workcenter():
    """API: Resource count by workcenter."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_workcenter", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_workcenter(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/workcenter_status_matrix')
def api_resource_workcenter_status_matrix():
    """API: Resource count matrix by workcenter and status category."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_workcenter_matrix", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_workcenter_status_matrix(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/detail', methods=['POST'])
def api_resource_detail():
    """API: Resource detail with filters."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = data.get('limit', 500)
    offset = data.get('offset', 0)
    days_back = get_days_back(filters)

    df = query_resource_detail(filters, limit, offset, days_back)
    if df is not None:
        records = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': records, 'count': len(records), 'offset': offset})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/filter_options')
def api_resource_filter_options():
    """API: Get filter options."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_filter_options", days_back)
    options = cache_get(cache_key)
    if options is None:
        options = query_resource_filter_options(days_back)
        if options:
            cache_set(cache_key, options)
    if options:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/status_values')
def api_resource_status_values():
    """API: Get all distinct status values with counts (for verification)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': '數據庫連接失敗'}), 500

    try:
        sql = """
            SELECT DISTINCT NEWSTATUSNAME, COUNT(*) as CNT
            FROM DWH.DW_MES_RESOURCESTATUS
            WHERE NEWSTATUSNAME IS NOT NULL
              AND LASTSTATUSCHANGEDATE >= SYSDATE - 30
            GROUP BY NEWSTATUSNAME
            ORDER BY CNT DESC
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        data = [{'status': row[0], 'count': row[1]} for row in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        if connection:
            connection.close()
        return jsonify({'success': False, 'error': str(exc)}), 500
