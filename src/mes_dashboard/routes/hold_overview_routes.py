# -*- coding: utf-8 -*-
"""Hold Overview page route and API endpoints."""

import os
from typing import Optional

from flask import Blueprint, current_app, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    internal_error,
    success_response,
    validation_error,
)
from mes_dashboard.core.utils import parse_bool_query
from mes_dashboard.core.modernization_policy import (
    missing_in_scope_asset_response,
    maybe_redirect_to_canonical_shell,
)
from mes_dashboard.services.wip_service import (
    get_hold_detail_lots,
    get_hold_detail_summary,
    get_hold_overview_treemap,
    get_wip_matrix,
)

hold_overview_bp = Blueprint('hold_overview', __name__)

_HOLD_OVERVIEW_MATRIX_RATE_LIMIT = configured_rate_limit(
    bucket="hold-overview-matrix",
    max_attempts_env="HOLD_OVERVIEW_MATRIX_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="HOLD_OVERVIEW_MATRIX_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=120,
    default_window_seconds=60,
)

_HOLD_OVERVIEW_LOTS_RATE_LIMIT = configured_rate_limit(
    bucket="hold-overview-lots",
    max_attempts_env="HOLD_OVERVIEW_LOTS_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="HOLD_OVERVIEW_LOTS_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=90,
    default_window_seconds=60,
)

_VALID_HOLD_TYPES = {'quality', 'non-quality', 'all'}
_VALID_AGE_RANGES = {'0-1', '1-3', '3-7', '7+'}


def _parse_reason_list() -> 'Optional[list[str]]':
    """Parse comma-separated reason parameter into a list, or None if empty."""
    raw = request.args.get('reason', '').strip()
    if not raw:
        return None
    values = [v.strip() for v in raw.split(',') if v.strip()]
    return values or None


def _parse_hold_type(default: str = 'all') -> tuple[Optional[str], Optional[object]]:
    raw = request.args.get('hold_type', '').strip().lower()
    hold_type = raw or default
    if hold_type not in _VALID_HOLD_TYPES:
        return None, validation_error('Invalid hold_type. Use quality, non-quality, or all')
    if hold_type == 'all':
        return None, None
    return hold_type, None


@hold_overview_bp.route('/hold-overview')
def hold_overview_page():
    """Render hold overview page from static Vite output."""
    canonical_redirect = maybe_redirect_to_canonical_shell('/hold-overview')
    if canonical_redirect is not None:
        return canonical_redirect

    dist_dir = os.path.join(current_app.static_folder or "", "dist")
    dist_html = os.path.join(dist_dir, "hold-overview.html")
    if os.path.exists(dist_html):
        return send_from_directory(dist_dir, 'hold-overview.html')

    return missing_in_scope_asset_response('/hold-overview', (
        "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Hold Overview</title>"
        "<script type=\"module\" src=\"/static/dist/hold-overview.js\"></script>"
        "</head><body><div id='app'></div></body></html>",
        200,
    ))


@hold_overview_bp.route('/api/hold-overview/summary')
def api_hold_overview_summary():
    """Return summary KPI data for hold overview page."""
    hold_type, error = _parse_hold_type(default='all')
    if error:
        return error

    reason = _parse_reason_list()
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_hold_detail_summary(
        reason=reason,
        hold_type=hold_type,
        workorder=workorder,
        lotid=lotid,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        include_dummy=include_dummy,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@hold_overview_bp.route('/api/hold-overview/matrix')
@_HOLD_OVERVIEW_MATRIX_RATE_LIMIT
def api_hold_overview_matrix():
    """Return hold-only workcenter x package matrix."""
    hold_type, error = _parse_hold_type(default='all')
    if error:
        return error

    reason = _parse_reason_list()
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_wip_matrix(
        include_dummy=include_dummy,
        status='HOLD',
        hold_type=hold_type,
        reason=reason,
        workorder=workorder,
        lotid=lotid,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@hold_overview_bp.route('/api/hold-overview/treemap')
def api_hold_overview_treemap():
    """Return grouped hold overview data for treemap chart."""
    hold_type, error = _parse_hold_type(default='all')
    if error:
        return error

    reason = _parse_reason_list()
    workcenter = request.args.get('workcenter', '').strip() or None
    package = request.args.get('package', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_hold_overview_treemap(
        hold_type=hold_type,
        reason=reason,
        workcenter=workcenter,
        package=package,
        include_dummy=include_dummy,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@hold_overview_bp.route('/api/hold-overview/lots')
@_HOLD_OVERVIEW_LOTS_RATE_LIMIT
def api_hold_overview_lots():
    """Return paginated hold lot details."""
    hold_type, error = _parse_hold_type(default='all')
    if error:
        return error

    reason = _parse_reason_list()
    treemap_reason = request.args.get('treemap_reason', '').strip() or None
    workcenter = request.args.get('workcenter', '').strip() or None
    package = request.args.get('package', '').strip() or None
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    age_range = request.args.get('age_range', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    if age_range and age_range not in _VALID_AGE_RANGES:
        return validation_error('Invalid age_range. Use 0-1, 1-3, 3-7, or 7+')

    if page is None:
        page = 1
    if per_page is None:
        per_page = 50

    page = max(page, 1)
    per_page = max(1, min(per_page, 200))

    result = get_hold_detail_lots(
        reason=reason,
        hold_type=hold_type,
        treemap_reason=treemap_reason,
        workcenter=workcenter,
        package=package,
        workorder=workorder,
        lotid=lotid,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        age_range=age_range,
        include_dummy=include_dummy,
        page=page,
        page_size=per_page,
    )
    if result is not None:
        return success_response(result)
    return internal_error()
