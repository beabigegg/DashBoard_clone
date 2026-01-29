# -*- coding: utf-8 -*-
"""WIP API routes for MES Dashboard.

Contains Flask Blueprint for WIP-related API endpoints.
Uses DW_MES_LOT_V view for real-time WIP data.
"""

from flask import Blueprint, jsonify, request

from mes_dashboard.services.wip_service import (
    get_wip_summary,
    get_wip_matrix,
    get_wip_hold_summary,
    get_wip_detail,
    get_workcenters,
    get_packages,
    search_workorders,
    search_lot_ids,
)

# Create Blueprint
wip_bp = Blueprint('wip', __name__, url_prefix='/api/wip')


def _parse_bool(value: str) -> bool:
    """Parse boolean from query string."""
    return value.lower() in ('true', '1', 'yes') if value else False


# ============================================================
# Overview APIs
# ============================================================

@wip_bp.route('/overview/summary')
def api_overview_summary():
    """API: Get WIP KPI summary for overview dashboard.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with totalLots, totalQtyPcs, byWipStatus, dataUpdateDate
    """
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_wip_summary(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/overview/matrix')
def api_overview_matrix():
    """API: Get workcenter x product line matrix for overview dashboard.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
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
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))
    status = request.args.get('status', '').strip().upper() or None
    hold_type = request.args.get('hold_type', '').strip().lower() or None

    # Validate status parameter
    if status and status not in ('RUN', 'QUEUE', 'HOLD'):
        return jsonify({
            'success': False,
            'error': 'Invalid status. Use RUN, QUEUE, or HOLD'
        }), 400

    # Validate hold_type parameter
    if hold_type and hold_type not in ('quality', 'non-quality'):
        return jsonify({
            'success': False,
            'error': 'Invalid hold_type. Use quality or non-quality'
        }), 400

    result = get_wip_matrix(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        status=status,
        hold_type=hold_type
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/overview/hold')
def api_overview_hold():
    """API: Get hold summary grouped by hold reason.

    Query Parameters:
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with items list containing reason, lots, qty
    """
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_wip_hold_summary(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


# ============================================================
# Detail APIs
# ============================================================

@wip_bp.route('/detail/<workcenter>')
def api_detail(workcenter: str):
    """API: Get WIP detail for a specific workcenter group.

    Args:
        workcenter: WORKCENTER_GROUP name (URL path parameter)

    Query Parameters:
        package: Optional PRODUCTLINENAME filter
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
    status = request.args.get('status', '').strip().upper() or None
    hold_type = request.args.get('hold_type', '').strip().lower() or None
    workorder = request.args.get('workorder', '').strip() or None
    lotid = request.args.get('lotid', '').strip() or None
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 100, type=int), 500)

    if page < 1:
        page = 1

    # Validate status parameter
    if status and status not in ('RUN', 'QUEUE', 'HOLD'):
        return jsonify({
            'success': False,
            'error': 'Invalid status. Use RUN, QUEUE, or HOLD'
        }), 400

    # Validate hold_type parameter
    if hold_type and hold_type not in ('quality', 'non-quality'):
        return jsonify({
            'success': False,
            'error': 'Invalid hold_type. Use quality or non-quality'
        }), 400

    result = get_wip_detail(
        workcenter=workcenter,
        package=package,
        status=status,
        hold_type=hold_type,
        workorder=workorder,
        lotid=lotid,
        include_dummy=include_dummy,
        page=page,
        page_size=page_size
    )

    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


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
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_workcenters(include_dummy=include_dummy)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/meta/packages')
def api_meta_packages():
    """API: Get list of packages (product lines) with lot counts.

    Query Parameters:
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with list of {name, lot_count} sorted by count desc
    """
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_packages(include_dummy=include_dummy)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@wip_bp.route('/meta/search')
def api_meta_search():
    """API: Search for WORKORDER or LOTID values.

    Query Parameters:
        type: Search type ('workorder' or 'lotid')
        q: Search query (minimum 2 characters)
        limit: Maximum results (default: 20, max: 50)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with items list containing matching values
    """
    search_type = request.args.get('type', '').strip().lower()
    q = request.args.get('q', '').strip()
    limit = min(request.args.get('limit', 20, type=int), 50)
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    # Validate search type
    if search_type not in ('workorder', 'lotid'):
        return jsonify({
            'success': False,
            'error': 'Invalid type. Use "workorder" or "lotid"'
        }), 400

    # Validate query length
    if len(q) < 2:
        return jsonify({'success': True, 'data': {'items': []}})

    # Perform search
    if search_type == 'workorder':
        result = search_workorders(q=q, limit=limit, include_dummy=include_dummy)
    else:
        result = search_lot_ids(q=q, limit=limit, include_dummy=include_dummy)

    if result is not None:
        return jsonify({'success': True, 'data': {'items': result}})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
