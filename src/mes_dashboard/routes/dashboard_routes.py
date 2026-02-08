# -*- coding: utf-8 -*-
"""Dashboard API routes for MES Dashboard.

Contains Flask Blueprint for dashboard/KPI-related API endpoints.
"""

from flask import Blueprint, jsonify, request

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.utils import get_days_back
from mes_dashboard.services.dashboard_service import (
    query_dashboard_kpi,
    query_workcenter_cards,
    query_resource_detail_with_job,
    query_ou_trend,
    query_utilization_heatmap,
)

# Create Blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


@dashboard_bp.route('/kpi', methods=['POST'])
def api_dashboard_kpi():
    """API: Dashboard KPI data."""
    data = request.get_json() or {}
    filters = data.get('filters')

    days_back = get_days_back(filters)
    cache_key = make_cache_key("dashboard_kpi", days_back, filters)
    kpi = cache_get(cache_key)
    if kpi is None:
        kpi = query_dashboard_kpi(filters)
        if kpi:
            cache_set(cache_key, kpi)
    if kpi:
        return jsonify({'success': True, 'data': kpi})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@dashboard_bp.route('/workcenter_cards', methods=['POST'])
def api_dashboard_workcenter_cards():
    """API: Workcenter cards data."""
    data = request.get_json() or {}
    filters = data.get('filters')

    days_back = get_days_back(filters)
    cache_key = make_cache_key("dashboard_workcenter_cards", days_back, filters)
    cards = cache_get(cache_key)
    if cards is None:
        cards = query_workcenter_cards(filters)
        if cards is not None:
            cache_set(cache_key, cards)
    if cards is not None:
        return jsonify({'success': True, 'data': cards})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@dashboard_bp.route('/detail', methods=['POST'])
def api_dashboard_detail():
    """API: Resource detail with JOB info."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = data.get('limit', 200)
    offset = data.get('offset', 0)

    df, max_status_time = query_resource_detail_with_job(filters, limit, offset)
    if df is not None:
        records = df.to_dict(orient='records')
        return jsonify({
            'success': True,
            'data': records,
            'count': len(records),
            'offset': offset,
            'max_status_time': max_status_time
        })
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@dashboard_bp.route('/ou_trend', methods=['POST'])
def api_dashboard_ou_trend():
    """API: OU% trend data for line chart."""
    data = request.get_json() or {}
    filters = data.get('filters')
    days = data.get('days', 7)

    cache_key = make_cache_key("dashboard_ou_trend", days, filters)
    trend = cache_get(cache_key)
    if trend is None:
        trend = query_ou_trend(days, filters)
        if trend is not None:
            cache_set(cache_key, trend, ttl=300)  # 5 min cache
    if trend is not None:
        return jsonify({'success': True, 'data': trend})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@dashboard_bp.route('/utilization_heatmap', methods=['POST'])
def api_dashboard_utilization_heatmap():
    """API: Utilization heatmap data."""
    data = request.get_json() or {}
    filters = data.get('filters')
    days = data.get('days', 7)

    cache_key = make_cache_key("dashboard_heatmap", days, filters)
    heatmap = cache_get(cache_key)
    if heatmap is None:
        heatmap = query_utilization_heatmap(days, filters)
        if heatmap is not None:
            cache_set(cache_key, heatmap, ttl=300)  # 5 min cache
    if heatmap is not None:
        return jsonify({'success': True, 'data': heatmap})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
