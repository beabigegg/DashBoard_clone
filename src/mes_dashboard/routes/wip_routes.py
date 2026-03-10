# -*- coding: utf-8 -*-
"""WIP API routes for MES Dashboard.

Contains Flask Blueprint for WIP-related API endpoints.
Uses DWH.DW_MES_LOT_V view for real-time WIP data.
"""

from flask import Blueprint, request

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    success_response,
    validation_error,
    not_found_error,
    internal_error,
)
from mes_dashboard.core.utils import parse_bool_query
from mes_dashboard.services.wip_service import (
    get_wip_summary,
    get_wip_matrix,
    get_wip_hold_summary,
    get_wip_detail,
    get_workcenters,
    get_packages,
    get_wip_filter_options,
    search_workorders,
    search_lot_ids,
    search_packages,
    search_types,
    get_lot_detail,
)

# Create Blueprint
wip_bp = Blueprint('wip', __name__, url_prefix='/api/wip')

_WIP_MATRIX_RATE_LIMIT = configured_rate_limit(
    bucket="wip-overview-matrix",
    max_attempts_env="WIP_MATRIX_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="WIP_MATRIX_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=120,
    default_window_seconds=60,
)

_WIP_DETAIL_RATE_LIMIT = configured_rate_limit(
    bucket="wip-detail",
    max_attempts_env="WIP_DETAIL_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="WIP_DETAIL_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=90,
    default_window_seconds=60,
)


# ============================================================
# Overview APIs
# ============================================================

@wip_bp.route('/overview/summary')
def api_overview_summary():
    """API: Get WIP KPI summary for overview dashboard.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with totalLots, totalQtyPcs, byWipStatus, dataUpdateDate
    """
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_wip_summary(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/overview/matrix')
@_WIP_MATRIX_RATE_LIMIT
def api_overview_matrix():
    """API: Get workcenter x product line matrix for overview dashboard.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        include_dummy: Include DUMMY lots (default: false)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'

    Returns:
        JSON with workcenters, packages, matrix, workcenter_totals,
        package_totals, grand_total
    """
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))
    status = request.args.get('status', '').strip().upper() or None
    hold_type = request.args.get('hold_type', '').strip().lower() or None

    # Validate status parameter
    if status and status not in ('RUN', 'QUEUE', 'HOLD'):
        return validation_error('Invalid status. Use RUN, QUEUE, or HOLD')

    # Validate hold_type parameter
    if hold_type and hold_type not in ('quality', 'non-quality'):
        return validation_error('Invalid hold_type. Use quality or non-quality')

    result = get_wip_matrix(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        status=status,
        hold_type=hold_type,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/overview/hold')
def api_overview_hold():
    """API: Get hold summary grouped by hold reason.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with items list containing reason, lots, qty
    """
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_wip_hold_summary(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


# ============================================================
# Detail APIs
# ============================================================

@wip_bp.route('/detail/<workcenter>')
@_WIP_DETAIL_RATE_LIMIT
def api_detail(workcenter: str):
    """API: Get WIP detail for a specific workcenter group.

    Args:
        workcenter: WORKCENTER_GROUP name (URL path parameter)

    Query Parameters:
        package: Optional PRODUCTLINENAME filter
        type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        include_dummy: Include DUMMY lots (default: false)
        page: Page number (default 1)
        page_size: Records per page (default 100, max 500)

    Returns:
        JSON with workcenter, summary, specs, lots, pagination, sys_date
    """
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None
    status = request.args.get('status', '').strip().upper() or None
    hold_type = request.args.get('hold_type', '').strip().lower() or None
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    include_dummy = parse_bool_query(request.args.get('include_dummy'))
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 100, type=int)

    if page is None:
        page = 1
    if page_size is None:
        page_size = 100

    page = max(page, 1)
    page_size = max(1, min(page_size, 500))

    # Validate status parameter
    if status and status not in ('RUN', 'QUEUE', 'HOLD'):
        return validation_error('Invalid status. Use RUN, QUEUE, or HOLD')

    # Validate hold_type parameter
    if hold_type and hold_type not in ('quality', 'non-quality'):
        return validation_error('Invalid hold_type. Use quality or non-quality')

    result = get_wip_detail(
        workcenter=workcenter,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        status=status,
        hold_type=hold_type,
        workorder=workorder,
        lotid=lotid,
        include_dummy=include_dummy,
        page=page,
        page_size=page_size
    )

    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/lot/<lotid>')
def api_lot_detail(lotid: str):
    """API: Get detailed information for a specific lot.

    Args:
        lotid: LOTID (URL path parameter)

    Returns:
        JSON with lot details including all fields from DW_MES_LOT_V
    """
    result = get_lot_detail(lotid)

    if result is not None:
        return success_response(result)
    return not_found_error('找不到此批號')


# ============================================================
# Meta APIs
# ============================================================

@wip_bp.route('/meta/workcenters')
def api_meta_workcenters():
    """API: Get list of workcenter groups with lot counts.

    Query Parameters:
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with list of {name, lot_count} sorted by sequence
    """
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_workcenters(include_dummy=include_dummy)
    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/meta/packages')
def api_meta_packages():
    """API: Get list of packages (product lines) with lot counts.

    Query Parameters:
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with list of {name, lot_count} sorted by count desc
    """
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_packages(include_dummy=include_dummy)
    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/meta/filter-options')
def api_meta_filter_options():
    """API: Get interdependent WIP overview filter options from cache-backed source."""
    include_dummy = parse_bool_query(request.args.get('include_dummy'))
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None
    firstname = request.args.get('firstname', '').strip() or None
    waferdesc = request.args.get('waferdesc', '').strip() or None

    result = get_wip_filter_options(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )
    if result is not None:
        return success_response(result)
    return internal_error()


@wip_bp.route('/meta/search')
def api_meta_search():
    """API: Search for WORKORDER, LOTID, PACKAGE, or PJ_TYPE values.

    Query Parameters:
        field: Field to search ('workorder', 'lotid', 'package', or 'pj_type')
        q: Search query (minimum 2 characters)
        limit: Maximum results (default: 20, max: 50)
        include_dummy: Include DUMMY lots (default: false)

        Cross-filter parameters (for interdependent filter suggestions):
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        lotid: Optional LOTID cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)
        type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        JSON with items list containing matching values
    """
    search_field = request.args.get('field', '').strip().lower()
    q = request.args.get('q', '').strip()
    limit_value = request.args.get('limit', 20, type=int)
    if limit_value is None:
        limit_value = 20
    limit = min(max(limit_value, 1), 50)
    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    # Cross-filter parameters
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    package = request.args.get('package', '').strip() or None
    pj_type = request.args.get('type', '').strip() or None

    # Validate search field
    if search_field not in ('workorder', 'lotid', 'package', 'pj_type'):
        return validation_error('Invalid field. Use "workorder", "lotid", "package", or "pj_type"')

    # Validate query length
    if len(q) < 2:
        return success_response({'items': []})

    # Perform search with cross-filters (exclude the field being searched)
    if search_field == 'workorder':
        result = search_workorders(
            q=q, limit=limit, include_dummy=include_dummy,
            lotid=lotid, package=package, pj_type=pj_type
        )
    elif search_field == 'lotid':
        result = search_lot_ids(
            q=q, limit=limit, include_dummy=include_dummy,
            workorder=workorder, package=package, pj_type=pj_type
        )
    elif search_field == 'package':
        result = search_packages(
            q=q, limit=limit, include_dummy=include_dummy,
            workorder=workorder, lotid=lotid, pj_type=pj_type
        )
    else:  # pj_type
        result = search_types(
            q=q, limit=limit, include_dummy=include_dummy,
            workorder=workorder, lotid=lotid, package=package
        )

    if result is not None:
        return success_response({'items': result})
    return internal_error()
