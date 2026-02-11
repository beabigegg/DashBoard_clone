# -*- coding: utf-8 -*-
"""Resource History Analysis API routes.

Contains Flask Blueprint for historical equipment performance analysis endpoints.
"""

from flask import Blueprint, jsonify, request, redirect, Response

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.config.constants import CACHE_TTL_FILTER_OPTIONS, CACHE_TTL_TREND
from mes_dashboard.services.resource_history_service import (
    get_filter_options,
    query_summary,
    query_detail,
    export_csv,
)

# Create Blueprint
resource_history_bp = Blueprint(
    'resource_history',
    __name__,
    url_prefix='/api/resource/history'
)


# ============================================================
# Page Route (for template rendering)
# ============================================================

@resource_history_bp.route('/page', methods=['GET'], endpoint='page_alias')
def api_resource_history_page():
    """Backward-compatible alias for the migrated /resource-history page route."""
    return redirect('/resource-history')


# ============================================================
# API Endpoints
# ============================================================

@resource_history_bp.route('/options', methods=['GET'])
def api_resource_history_options():
    """API: Get filter options (workcenters and families).

    Returns:
        JSON with workcenters and families lists.
    """
    cache_key = make_cache_key("resource_history_options_v2")
    options = cache_get(cache_key)

    if options is None:
        options = get_filter_options()
        if options is not None:
            cache_set(cache_key, options, ttl=CACHE_TTL_FILTER_OPTIONS)

    if options is not None:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢篩選選項失敗'}), 500


@resource_history_bp.route('/summary', methods=['GET'])
def api_resource_history_summary():
    """API: Get summary data (KPI, trend, heatmap, workcenter comparison).

    Query Parameters:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        granularity: day|week|month|year (default: day)
        workcenter_groups: Optional workcenter group filter (multi-select)
        families: Optional resource family filter (multi-select)
        is_production: 1 to filter production equipment
        is_key: 1 to filter key equipment
        is_monitor: 1 to filter monitored equipment

    Returns:
        JSON with kpi, trend, heatmap, workcenter_comparison sections.
    """
    # Parse query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    granularity = request.args.get('granularity', 'day')
    workcenter_groups = request.args.getlist('workcenter_groups') or None
    families = request.args.getlist('families') or None
    resource_ids = request.args.getlist('resource_ids') or None
    is_production = request.args.get('is_production') == '1'
    is_key = request.args.get('is_key') == '1'
    is_monitor = request.args.get('is_monitor') == '1'

    # Validate required parameters
    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    # Build cache key with filters dict
    cache_filters = {
        'start_date': start_date,
        'end_date': end_date,
        'granularity': granularity,
        'workcenter_groups': sorted(workcenter_groups) if workcenter_groups else None,
        'families': sorted(families) if families else None,
        'resource_ids': sorted(resource_ids) if resource_ids else None,
        'is_production': is_production,
        'is_key': is_key,
        'is_monitor': is_monitor,
    }
    cache_key = make_cache_key("resource_history_summary", filters=cache_filters)
    result = cache_get(cache_key)

    if result is None:
        result = query_summary(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )
        if result is not None and 'error' not in result:
            cache_set(cache_key, result, ttl=CACHE_TTL_TREND)

    if result is not None:
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 400
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢摘要資料失敗'}), 500


@resource_history_bp.route('/detail', methods=['GET'])
def api_resource_history_detail():
    """API: Get hierarchical detail data.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        granularity: day|week|month|year (default: day)
        workcenter_groups: Optional workcenter group filter (multi-select)
        families: Optional resource family filter (multi-select)
        is_production: 1 to filter production equipment
        is_key: 1 to filter key equipment
        is_monitor: 1 to filter monitored equipment

    Returns:
        JSON with data array, total count, truncated flag.
    """
    # Parse query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    granularity = request.args.get('granularity', 'day')
    workcenter_groups = request.args.getlist('workcenter_groups') or None
    families = request.args.getlist('families') or None
    resource_ids = request.args.getlist('resource_ids') or None
    is_production = request.args.get('is_production') == '1'
    is_key = request.args.get('is_key') == '1'
    is_monitor = request.args.get('is_monitor') == '1'

    # Validate required parameters
    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    result = query_detail(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        workcenter_groups=workcenter_groups,
        families=families,
        resource_ids=resource_ids,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
    )

    if result is not None:
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 400
        return jsonify({'success': True, **result})
    return jsonify({'success': False, 'error': '查詢明細資料失敗'}), 500


@resource_history_bp.route('/export', methods=['GET'])
def api_resource_history_export():
    """API: Export detail data as CSV.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        granularity: day|week|month|year (default: day)
        workcenter_groups: Optional workcenter group filter (multi-select)
        families: Optional resource family filter (multi-select)
        is_production: 1 to filter production equipment
        is_key: 1 to filter key equipment
        is_monitor: 1 to filter monitored equipment

    Returns:
        CSV file download.
    """
    # Parse query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    granularity = request.args.get('granularity', 'day')
    workcenter_groups = request.args.getlist('workcenter_groups') or None
    families = request.args.getlist('families') or None
    resource_ids = request.args.getlist('resource_ids') or None
    is_production = request.args.get('is_production') == '1'
    is_key = request.args.get('is_key') == '1'
    is_monitor = request.args.get('is_monitor') == '1'

    # Validate required parameters
    if not start_date or not end_date:
        return jsonify({
            'success': False,
            'error': '必須提供 start_date 和 end_date 參數'
        }), 400

    # Generate filename
    filename = f"resource_history_{start_date}_to_{end_date}.csv"

    # Stream CSV response
    return Response(
        export_csv(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        ),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
