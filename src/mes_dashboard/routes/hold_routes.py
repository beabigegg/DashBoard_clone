# -*- coding: utf-8 -*-
"""Hold Detail API routes for MES Dashboard.

Contains Flask Blueprint for Hold Detail page and API endpoints.
"""

from flask import Blueprint, jsonify, request, render_template, redirect, url_for

from mes_dashboard.services.wip_service import (
    get_hold_detail_summary,
    get_hold_detail_distribution,
    get_hold_detail_lots,
    is_quality_hold,
)

# Create Blueprint
hold_bp = Blueprint('hold', __name__)


def _parse_bool(value: str) -> bool:
    """Parse boolean from query string."""
    return value.lower() in ('true', '1', 'yes') if value else False


# ============================================================
# Page Route
# ============================================================

@hold_bp.route('/hold-detail')
def hold_detail_page():
    """Render the Hold Detail page.

    Query Parameters:
        reason: Hold reason name (required)

    Returns:
        Rendered HTML template
    """
    reason = request.args.get('reason', '').strip()
    if not reason:
        # Redirect to WIP Overview when reason is missing
        return redirect('/wip-overview')

    hold_type = 'quality' if is_quality_hold(reason) else 'non-quality'
    return render_template('hold_detail.html', reason=reason, hold_type=hold_type)


# ============================================================
# Hold Detail APIs
# ============================================================

@hold_bp.route('/api/wip/hold-detail/summary')
def api_hold_detail_summary():
    """API: Get summary statistics for a specific hold reason.

    Query Parameters:
        reason: Hold reason name (required)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with totalLots, totalQty, avgAge, maxAge, workcenterCount
    """
    reason = request.args.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': '缺少必要參數: reason'}), 400

    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_hold_detail_summary(
        reason=reason,
        include_dummy=include_dummy
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_bp.route('/api/wip/hold-detail/distribution')
def api_hold_detail_distribution():
    """API: Get distribution statistics for a specific hold reason.

    Query Parameters:
        reason: Hold reason name (required)
        include_dummy: Include DUMMY lots (default: false)

    Returns:
        JSON with byWorkcenter, byPackage, byAge distributions
    """
    reason = request.args.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': '缺少必要參數: reason'}), 400

    include_dummy = _parse_bool(request.args.get('include_dummy', ''))

    result = get_hold_detail_distribution(
        reason=reason,
        include_dummy=include_dummy
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_bp.route('/api/wip/hold-detail/lots')
def api_hold_detail_lots():
    """API: Get paginated lot details for a specific hold reason.

    Query Parameters:
        reason: Hold reason name (required)
        workcenter: Optional WORKCENTER_GROUP filter
        package: Optional PRODUCTLINENAME filter
        age_range: Optional age range filter ('0-1', '1-3', '3-7', '7+')
        include_dummy: Include DUMMY lots (default: false)
        page: Page number (default 1)
        per_page: Records per page (default 50, max 200)

    Returns:
        JSON with lots list, pagination info, and active filters
    """
    reason = request.args.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': '缺少必要參數: reason'}), 400

    workcenter = request.args.get('workcenter', '').strip() or None
    package = request.args.get('package', '').strip() or None
    age_range = request.args.get('age_range', '').strip() or None
    include_dummy = _parse_bool(request.args.get('include_dummy', ''))
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)

    if page < 1:
        page = 1

    # Validate age_range parameter
    if age_range and age_range not in ('0-1', '1-3', '3-7', '7+'):
        return jsonify({
            'success': False,
            'error': 'Invalid age_range. Use 0-1, 1-3, 3-7, or 7+'
        }), 400

    result = get_hold_detail_lots(
        reason=reason,
        workcenter=workcenter,
        package=package,
        age_range=age_range,
        include_dummy=include_dummy,
        page=page,
        page_size=per_page
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
