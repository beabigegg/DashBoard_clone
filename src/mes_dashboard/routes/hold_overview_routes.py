# -*- coding: utf-8 -*-
"""Hold Overview page route and API endpoints."""

import os
from typing import Optional

from flask import Blueprint, current_app, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import validate_workcenter_group_filter
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


def _get_request_args() -> dict:
    """Return request params from JSON body (POST) or query string (GET)."""
    if request.method == 'POST':
        return request.get_json(silent=True) or {}
    return request.args


def _coerce_int(value, default: int) -> int:
    """Coerce value to int, returning default on failure."""
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_reason_list(args=None) -> 'Optional[list[str]]':
    """Parse reason parameter into a list, or None if empty.

    Supports JSON array (POST) or comma-separated string (GET).
    """
    source = args if args is not None else request.args
    raw = source.get('reason', '')
    if not raw:
        return None
    if isinstance(raw, list):
        values = [v.strip() for v in raw if str(v).strip()]
    else:
        values = [v.strip() for v in str(raw).split(',') if v.strip()]
    return values or None


def _parse_hold_type(default: str = 'all', args=None) -> tuple[Optional[str], Optional[object]]:
    source = args if args is not None else request.args
    raw = source.get('hold_type', '')
    if isinstance(raw, str):
        raw = raw.strip().lower()
    else:
        raw = ''
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


@hold_overview_bp.route('/api/hold-overview/summary', methods=['GET', 'POST'])
def api_hold_overview_summary():
    """Return summary KPI data for hold overview page."""
    args = _get_request_args()
    if "workcenter_group" in args:
        workcenter_group_error = validate_workcenter_group_filter(args.get("workcenter_group"))
        if workcenter_group_error:
            return validation_error(workcenter_group_error)
    hold_type, error = _parse_hold_type(default='all', args=args)
    if error:
        return error

    reason = _parse_reason_list(args=args)
    workorder = args.get('workorder', '').strip() or None
    lotid = args.get('lotid', '').strip() or None
    package = args.get('package', '').strip() or None
    pj_type = args.get('type', '').strip() or None
    firstname = args.get('firstname', '').strip() or None
    waferdesc = args.get('waferdesc', '').strip() or None
    workflow = args.get('workflow', '').strip() or ''
    bop = args.get('bop', '').strip() or ''
    pj_function = args.get('pj_function', '').strip() or ''
    include_dummy = parse_bool_query(args.get('include_dummy'))

    result = get_hold_detail_summary(
        reason=reason,
        hold_type=hold_type,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        include_dummy=include_dummy,
        workflow=workflow,
        bop=bop,
        pj_function=pj_function,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@hold_overview_bp.route('/api/hold-overview/matrix', methods=['GET', 'POST'])
@_HOLD_OVERVIEW_MATRIX_RATE_LIMIT
def api_hold_overview_matrix():
    """Return hold-only workcenter x package matrix."""
    args = _get_request_args()
    hold_type, error = _parse_hold_type(default='all', args=args)
    if error:
        return error

    reason = _parse_reason_list(args=args)
    workorder = args.get('workorder', '').strip() or None
    lotid = args.get('lotid', '').strip() or None
    package = args.get('package', '').strip() or None
    pj_type = args.get('type', '').strip() or None
    firstname = args.get('firstname', '').strip() or None
    waferdesc = args.get('waferdesc', '').strip() or None
    workflow = args.get('workflow', '').strip() or ''
    bop = args.get('bop', '').strip() or ''
    pj_function = args.get('pj_function', '').strip() or ''
    include_dummy = parse_bool_query(args.get('include_dummy'))

    result = get_wip_matrix(
        include_dummy=include_dummy,
        status='HOLD',
        hold_type=hold_type,
        reason=reason,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        workflow=workflow,
        bop=bop,
        pj_function=pj_function,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@hold_overview_bp.route('/api/hold-overview/treemap', methods=['GET', 'POST'])
def api_hold_overview_treemap():
    """Return grouped hold overview data for treemap chart."""
    args = _get_request_args()
    hold_type, error = _parse_hold_type(default='all', args=args)
    if error:
        return error

    reason = _parse_reason_list(args=args)
    workcenter = args.get('workcenter', '').strip() or None
    package = args.get('package', '').strip() or None
    include_dummy = parse_bool_query(args.get('include_dummy'))

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


@hold_overview_bp.route('/api/hold-overview/lots', methods=['GET', 'POST'])
@_HOLD_OVERVIEW_LOTS_RATE_LIMIT
def api_hold_overview_lots():
    """Return paginated hold lot details."""
    args = _get_request_args()
    hold_type, error = _parse_hold_type(default='all', args=args)
    if error:
        return error

    reason = _parse_reason_list(args=args)
    treemap_reason = args.get('treemap_reason', '').strip() or None
    workcenter = args.get('workcenter', '').strip() or None
    package = args.get('package', '').strip() or None
    workorder = args.get('workorder', '').strip() or None
    lotid = args.get('lotid', '').strip() or None
    pj_type = args.get('type', '').strip() or None
    firstname = args.get('firstname', '').strip() or None
    waferdesc = args.get('waferdesc', '').strip() or None
    workflow = args.get('workflow', '').strip() or ''
    bop = args.get('bop', '').strip() or ''
    pj_function = args.get('pj_function', '').strip() or ''
    age_range = args.get('age_range', '').strip() or None
    include_dummy = parse_bool_query(args.get('include_dummy'))
    page = _coerce_int(args.get('page', 1), default=1)
    per_page = _coerce_int(args.get('per_page', 50), default=50)

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
        workflow=workflow,
        bop=bop,
        pj_function=pj_function,
        age_range=age_range,
        include_dummy=include_dummy,
        page=page,
        page_size=per_page,
    )
    if result is not None:
        return success_response(result)
    return internal_error()
