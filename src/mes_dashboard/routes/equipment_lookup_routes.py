# -*- coding: utf-8 -*-
"""Equipment Lookup (機台查詢) API routes for MES Dashboard.

Quick-lookup page under the 查詢工具 drawer letting users filter
equipment by 機台位置 (LOCATIONNAME) / 機型 (RESOURCEFAMILYNAME) /
編號 (RESOURCENAME). Backed entirely by the resource_cache in-memory
equipment snapshot — no direct Oracle queries in this module.
"""

import logging

from flask import Blueprint, request

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.response import (
    INTERNAL_ERROR,
    error_response,
    success_response,
    validation_error,
)
from mes_dashboard.services.equipment_lookup_service import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_BY,
    SORTABLE_COLUMNS,
    get_equipment_lookup_list,
    get_equipment_lookup_options,
)

equipment_lookup_bp = Blueprint(
    'equipment_lookup', __name__, url_prefix='/api/equipment-lookup'
)
logger = logging.getLogger('mes_dashboard.equipment_lookup_routes')

_OPTIONS_CACHE_TTL_SECONDS = 300
_MAX_PAGE_SIZE = 10000


def _parse_multi_values(name: str):
    """Parse a repeatable/comma-separated query param into a list or None.

    Supports both ?name=A,B and repeated ?name=A&name=B (and a mix).
    """
    values = []
    for raw in request.args.getlist(name):
        if raw is None:
            continue
        for part in str(raw).split(','):
            part = part.strip()
            if part:
                values.append(part)
    return values or None


@equipment_lookup_bp.route('/options')
def api_equipment_lookup_options():
    """API: Get filter dropdown options (locations/families/resource_names).

    Options are the full universe of values with no cross-filter narrowing
    (deliberately independent filters). Cached briefly since resource_cache
    itself only syncs from Oracle every 24h.
    """
    try:
        cache_key = make_cache_key("equipment_lookup_options")
        cached = cache_get(cache_key)
        if cached is not None:
            return success_response(cached)

        data = get_equipment_lookup_options()
        cache_set(cache_key, data, ttl=_OPTIONS_CACHE_TTL_SECONDS)

        return success_response(data)
    except Exception as exc:
        logger.exception("Failed to load equipment lookup options: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )


@equipment_lookup_bp.route('/list')
def api_equipment_lookup_list():
    """API: Get filtered/sorted/paginated equipment list.

    Query params:
        locations: Repeatable/comma-separated LOCATIONNAME exact-match values.
        families: Repeatable/comma-separated RESOURCEFAMILYNAME exact-match values.
        resource_names: Repeatable/comma-separated RESOURCENAME exact-match values.
        page: 1-based page number (default 1).
        page_size: Rows per page (default 20, max 10000 — supports fetching
            all matching rows in one call for CSV export; there is
            deliberately no separate export endpoint).
        sort_by: One of RESOURCENAME/LOCATIONNAME/RESOURCEFAMILYNAME (default RESOURCENAME).
        sort_dir: asc or desc (default asc).
    """
    locations = _parse_multi_values('locations')
    families = _parse_multi_values('families')
    resource_names = _parse_multi_values('resource_names')

    try:
        page = int(request.args.get('page', DEFAULT_PAGE))
    except (TypeError, ValueError):
        return validation_error('page 必須為正整數')
    if page < 1:
        return validation_error('page 必須為正整數')

    try:
        page_size = int(request.args.get('page_size', DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        return validation_error('page_size 必須為正整數')
    if page_size < 1:
        return validation_error('page_size 必須為正整數')
    if page_size > _MAX_PAGE_SIZE:
        return validation_error(f'page_size 不可超過 {_MAX_PAGE_SIZE}')

    sort_by = str(request.args.get('sort_by', DEFAULT_SORT_BY) or DEFAULT_SORT_BY).strip()
    if sort_by not in SORTABLE_COLUMNS:
        return validation_error(f"sort_by 不支援，允許值: {', '.join(SORTABLE_COLUMNS)}")

    sort_dir = str(request.args.get('sort_dir', 'asc') or 'asc').strip().lower()
    if sort_dir not in ('asc', 'desc'):
        return validation_error('sort_dir 僅支援 asc/desc')

    try:
        data = get_equipment_lookup_list(
            locations=locations,
            families=families,
            resource_names=resource_names,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        return success_response(data)
    except Exception as exc:
        logger.exception("Failed to load equipment lookup list: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )
