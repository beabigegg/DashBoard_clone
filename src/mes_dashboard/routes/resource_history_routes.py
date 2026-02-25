# -*- coding: utf-8 -*-
"""Resource History Analysis API routes.

Contains Flask Blueprint for historical equipment performance analysis endpoints.
Two-phase flow: POST /query (Oracle → cache) + GET /view (cache → derived views).
"""

from datetime import datetime

from flask import Blueprint, jsonify, request, redirect, Response

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.config.constants import CACHE_TTL_FILTER_OPTIONS
from mes_dashboard.services.resource_history_service import (
    get_filter_options,
    export_csv,
)
from mes_dashboard.services.resource_dataset_cache import (
    execute_primary_query,
    apply_view,
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


# ============================================================
# Two-phase dataset cache endpoints
# ============================================================

def _validate_dates(start_date: str, end_date: str):
    """Validate and return parsed dates, or raise ValueError."""
    if not start_date or not end_date:
        raise ValueError("必須提供 start_date 和 end_date 參數")
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if ed < sd:
        raise ValueError("end_date 不可早於 start_date")
    return sd, ed


def _parse_resource_filters(data: dict) -> dict:
    """Extract resource filter params from dict (request body or query params)."""
    return {
        "workcenter_groups": data.get("workcenter_groups") or None,
        "families": data.get("families") or None,
        "resource_ids": data.get("resource_ids") or None,
        "is_production": _bool_param(data.get("is_production")),
        "is_key": _bool_param(data.get("is_key")),
        "is_monitor": _bool_param(data.get("is_monitor")),
    }


def _bool_param(val) -> bool:
    """Normalize bool-ish values from JSON body or query string."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val in ("1", "true", "True")
    return bool(val) if val is not None else False


@resource_history_bp.route('/query', methods=['POST'])
def api_resource_history_query():
    """API: Primary query — Oracle → cache → return query_id + initial view.

    JSON Body:
        start_date: str (YYYY-MM-DD)
        end_date: str (YYYY-MM-DD)
        granularity: str (day|week|month|year, default: day)
        workcenter_groups: list[str] (optional)
        families: list[str] (optional)
        resource_ids: list[str] (optional)
        is_production: bool (optional)
        is_key: bool (optional)
        is_monitor: bool (optional)

    Returns:
        JSON { success, query_id, summary, detail }
    """
    body = request.get_json(silent=True) or {}
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    granularity = body.get("granularity", "day")

    try:
        _validate_dates(start_date, end_date)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    filters = _parse_resource_filters(body)

    try:
        result = execute_primary_query(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            **filters,
        )
        return jsonify({"success": True, **result})
    except Exception as exc:
        return jsonify({"success": False, "error": f"查詢失敗: {exc}"}), 500


@resource_history_bp.route('/view', methods=['GET'])
def api_resource_history_view():
    """API: Supplementary view — read cache, derive views. No Oracle query.

    Query Parameters:
        query_id: str (required)
        granularity: str (day|week|month|year, default: day)

    Returns:
        JSON { success, summary, detail } or 410 on cache miss.
    """
    query_id = request.args.get("query_id", "")
    granularity = request.args.get("granularity", "day")

    if not query_id:
        return jsonify({"success": False, "error": "必須提供 query_id"}), 400

    result = apply_view(query_id=query_id, granularity=granularity)
    if result is None:
        return jsonify({"success": False, "error": "cache_expired"}), 410

    return jsonify({"success": True, **result})


# ============================================================
# Export (kept — uses existing service directly)
# ============================================================

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

    # Validate export date range (max 365 days)
    try:
        sd = datetime.strptime(start_date, '%Y-%m-%d')
        ed = datetime.strptime(end_date, '%Y-%m-%d')
        if (ed - sd).days > 365:
            return jsonify({
                'success': False,
                'error': 'CSV 匯出範圍不可超過一年 (365 天)'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'error': '日期格式錯誤，請使用 YYYY-MM-DD'
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
