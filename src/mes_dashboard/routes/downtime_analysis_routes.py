# -*- coding: utf-8 -*-
"""Downtime Analysis API routes.

Blueprint for historical downtime analysis endpoints.
Type-A spool pattern: POST /query (Oracle → spool) + GET /view (spool → views).

Endpoints per api-contract.md §10:
  GET  /api/downtime-analysis/options
  POST /api/downtime-analysis/query
  GET  /api/downtime-analysis/view
  GET  /api/downtime-analysis/equipment-detail
  GET  /api/downtime-analysis/event-detail
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, request

from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.downtime_analysis_service import (
    apply_view,
    get_filter_options,
    query_downtime_dataset,
)

downtime_analysis_bp = Blueprint(
    'downtime_analysis',
    __name__,
    url_prefix='/api/downtime-analysis',
)

# ── Maximum allowed date range (SYS-04) ──────────────────────────────────────
_MAX_DAYS = 730


# ============================================================
# Validation helpers
# ============================================================


def _validate_dates(start_date: str, end_date: str) -> None:
    """Raise ValueError on invalid/missing dates or range > 730d (SYS-04)."""
    if not start_date or not end_date:
        raise ValueError("必須提供 start_date 和 end_date 參數")
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if ed < sd:
        raise ValueError("end_date 不可早於 start_date")
    if (ed - sd).days > _MAX_DAYS:
        raise ValueError(f"查詢範圍不可超過 {_MAX_DAYS} 天")


def _csv_param(val: str | None) -> list[str] | None:
    """Parse comma-separated query param into list, or None when empty."""
    if not val:
        return None
    parts = [v.strip() for v in val.split(',') if v.strip()]
    return parts if parts else None


# ============================================================
# GET /api/downtime-analysis/options
# ============================================================


@downtime_analysis_bp.route('/options', methods=['GET'])
def api_downtime_options():
    """API: Get filter options for downtime-analysis page.

    Query Parameters (optional, for cross-narrow):
        workcenter_groups: comma-separated
        families:          comma-separated
        resource_ids:      comma-separated
        package_groups:    comma-separated

    Returns:
        JSON with workcenter_groups, families, resources, package_groups,
              big_categories, reasons lists.
    """
    workcenter_groups = _csv_param(request.args.get('workcenter_groups', ''))
    families = _csv_param(request.args.get('families', ''))
    resource_ids = _csv_param(request.args.get('resource_ids', ''))
    package_groups = _csv_param(request.args.get('package_groups', ''))

    options = get_filter_options(
        workcenter_groups=workcenter_groups,
        families=families,
        resource_ids=resource_ids,
        package_groups=package_groups,
    )
    if options is None:
        return internal_error("篩選條件選項載入失敗")
    return success_response(options)


# ============================================================
# POST /api/downtime-analysis/query
# ============================================================


@downtime_analysis_bp.route('/query', methods=['POST'])
def api_downtime_query():
    """API: Primary query — Oracle → spool → return query_id + summary views.

    JSON Body:
        start_date:       str (YYYY-MM-DD, required)
        end_date:         str (YYYY-MM-DD, required)
        workcenter_groups: list[str] (optional)
        families:          list[str] (optional)
        resource_ids:      list[str] (optional)
        package_groups:    list[str] (optional)
        big_categories:    list[str] (optional)
        status_types:      list[str] (optional, e.g. ['UDT','SDT'])

    Returns:
        JSON { success, data: { query_id, summary, daily_trend, big_category, top_reasons } }
    """
    body = request.get_json(silent=True) or {}
    start_date = body.get('start_date', '')
    end_date = body.get('end_date', '')

    try:
        _validate_dates(start_date, end_date)
    except ValueError as exc:
        return validation_error(str(exc))

    workcenter_groups = body.get('workcenter_groups') or None
    families = body.get('families') or None
    resource_ids = body.get('resource_ids') or None
    package_groups = body.get('package_groups') or None
    big_categories = body.get('big_categories') or None
    status_types = body.get('status_types') or None

    try:
        result = query_downtime_dataset(
            start_date=start_date,
            end_date=end_date,
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            package_groups=package_groups,
            big_categories=big_categories,
            status_types=status_types,
        )
        return success_response(result)
    except Exception as exc:
        return internal_error(str(exc))


# ============================================================
# GET /api/downtime-analysis/view
# ============================================================


@downtime_analysis_bp.route('/view', methods=['GET'])
def api_downtime_view():
    """API: Re-group spool for summary/trend/big-category/top-reasons view.

    Query Parameters:
        query_id:    str (required)
        granularity: str (day|week|month, default: day)
        top_n:       int (default: 10)

    Returns:
        JSON { success, data: { summary, daily_trend, big_category, top_reasons } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    granularity = request.args.get('granularity', 'day').strip()
    top_n = request.args.get('top_n', 10, type=int)

    if not query_id:
        return validation_error("必須提供 query_id")

    if granularity != 'day':
        return validation_error('granularity must be "day" (week/month not yet implemented)')

    result = apply_view(
        view_name='summary',
        query_id=query_id,
        granularity=granularity,
        top_n=top_n,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# GET /api/downtime-analysis/equipment-detail
# ============================================================


@downtime_analysis_bp.route('/equipment-detail', methods=['GET'])
def api_downtime_equipment_detail():
    """API: Per-equipment summary from spool.

    Query Parameters:
        query_id: str (required)

    Returns:
        JSON { success, data: { equipment_detail: EquipmentDetailRow[] } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()

    if not query_id:
        return validation_error("必須提供 query_id")

    # Build resource lookup for display names
    resource_lookup = _get_resource_lookup_safe()

    result = apply_view(
        view_name='equipment_detail',
        query_id=query_id,
        resource_lookup=resource_lookup,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# GET /api/downtime-analysis/event-detail
# ============================================================


@downtime_analysis_bp.route('/event-detail', methods=['GET'])
def api_downtime_event_detail():
    """API: Paginated per-event detail from spool.

    Query Parameters:
        query_id:  str (required)
        page:      int (default: 1)
        page_size: int (default: 50, max: 200)

    Returns:
        JSON { success, data: { events: EventDetailRow[], pagination: {...} } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)

    if not query_id:
        return validation_error("必須提供 query_id")

    page_size = min(max(page_size, 1), 200)
    page = max(page, 1)

    resource_lookup = _get_resource_lookup_safe()

    result = apply_view(
        view_name='event_detail',
        query_id=query_id,
        page=page,
        page_size=page_size,
        resource_lookup=resource_lookup,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# Resource lookup helper
# ============================================================


def _get_resource_lookup_safe() -> dict:
    """Return resource lookup dict {historyid: info}; empty dict on error."""
    try:
        from mes_dashboard.services.resource_cache import get_all_resources
        resources = get_all_resources() or []
        return {
            str(r.get('RESOURCEID', '')).strip(): r
            for r in resources
            if r.get('RESOURCEID')
        }
    except Exception:
        return {}
