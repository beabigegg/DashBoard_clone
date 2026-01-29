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
    get_merged_resource_status,
    get_resource_status_summary,
    get_workcenter_status_matrix,
)
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.config.constants import STATUS_CATEGORIES

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


# ============================================================
# Realtime Equipment Status APIs (New)
# ============================================================

@resource_bp.route('/status')
def api_resource_status():
    """API: Get merged resource status from realtime cache.

    Query params:
        workcenter_groups: Comma-separated group names (e.g., '焊接,成型')
        is_production: '1' or 'true' to filter production equipment
        is_key: '1' or 'true' to filter key equipment
        is_monitor: '1' or 'true' to filter monitor equipment
        status_categories: Comma-separated categories (e.g., 'PRODUCTIVE,DOWN')
    """
    # Parse filters
    wc_groups_param = request.args.get('workcenter_groups')
    workcenter_groups = wc_groups_param.split(',') if wc_groups_param else None

    is_production = None
    is_prod_param = request.args.get('is_production')
    if is_prod_param:
        is_production = is_prod_param.lower() in ('1', 'true', 'yes')

    is_key = None
    is_key_param = request.args.get('is_key')
    if is_key_param:
        is_key = is_key_param.lower() in ('1', 'true', 'yes')

    is_monitor = None
    is_monitor_param = request.args.get('is_monitor')
    if is_monitor_param:
        is_monitor = is_monitor_param.lower() in ('1', 'true', 'yes')

    status_cats_param = request.args.get('status_categories')
    status_categories = status_cats_param.split(',') if status_cats_param else None

    try:
        data = get_merged_resource_status(
            workcenter_groups=workcenter_groups,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
            status_categories=status_categories,
        )
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data),
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@resource_bp.route('/status/options')
def api_resource_status_options():
    """API: Get filter options for realtime status queries.

    Returns workcenter_groups, status_categories, and other filter options.
    """
    try:
        # Get workcenter groups from cache
        wc_groups = get_workcenter_groups() or []

        return jsonify({
            'success': True,
            'data': {
                'workcenter_groups': [g['name'] for g in wc_groups],
                'status_categories': STATUS_CATEGORIES,
            }
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@resource_bp.route('/status/summary')
def api_resource_status_summary():
    """API: Get resource status summary statistics.

    Query params: same as /status
    """
    # Parse filters (same as /status)
    wc_groups_param = request.args.get('workcenter_groups')
    workcenter_groups = wc_groups_param.split(',') if wc_groups_param else None

    is_production = None
    is_prod_param = request.args.get('is_production')
    if is_prod_param:
        is_production = is_prod_param.lower() in ('1', 'true', 'yes')

    is_key = None
    is_key_param = request.args.get('is_key')
    if is_key_param:
        is_key = is_key_param.lower() in ('1', 'true', 'yes')

    is_monitor = None
    is_monitor_param = request.args.get('is_monitor')
    if is_monitor_param:
        is_monitor = is_monitor_param.lower() in ('1', 'true', 'yes')

    try:
        data = get_resource_status_summary(
            workcenter_groups=workcenter_groups,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@resource_bp.route('/status/matrix')
def api_resource_status_matrix():
    """API: Get workcenter × status matrix.

    Query params:
        is_production: Filter by production equipment
        is_key: Filter by key equipment
        is_monitor: Filter by monitor equipment
    """
    is_production = None
    is_prod_param = request.args.get('is_production')
    if is_prod_param:
        is_production = is_prod_param.lower() in ('1', 'true', 'yes')

    is_key = None
    is_key_param = request.args.get('is_key')
    if is_key_param:
        is_key = is_key_param.lower() in ('1', 'true', 'yes')

    is_monitor = None
    is_monitor_param = request.args.get('is_monitor')
    if is_monitor_param:
        is_monitor = is_monitor_param.lower() in ('1', 'true', 'yes')

    try:
        data = get_workcenter_status_matrix(
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
