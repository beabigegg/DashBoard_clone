# -*- coding: utf-8 -*-
"""Hold Detail API routes for MES Dashboard.

Contains Flask Blueprint for Hold Detail page and API endpoints.
"""

import html
import os

from flask import Blueprint, current_app, jsonify, redirect, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.utils import parse_bool_query
from mes_dashboard.core.modernization_policy import (
    missing_in_scope_asset_response,
    maybe_redirect_to_canonical_shell,
)
from mes_dashboard.services.wip_service import (
    get_hold_detail_summary,
    get_hold_detail_distribution,
    get_hold_detail_lots,
)

# Create Blueprint
hold_bp = Blueprint('hold', __name__)

_HOLD_LOTS_RATE_LIMIT = configured_rate_limit(
    bucket="hold-detail-lots",
    max_attempts_env="HOLD_LOTS_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="HOLD_LOTS_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=90,
    default_window_seconds=60,
)


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
        # Redirect to overview route; in SPA mode this becomes canonical shell URL.
        overview_redirect = maybe_redirect_to_canonical_shell('/hold-overview')
        if overview_redirect is not None:
            return overview_redirect
        return redirect('/hold-overview')

    canonical_redirect = maybe_redirect_to_canonical_shell('/hold-detail')
    if canonical_redirect is not None:
        return canonical_redirect

    # Keep server-side validation, then serve static Vite output directly.
    dist_dir = os.path.join(current_app.static_folder or "", "dist")
    dist_html = os.path.join(dist_dir, "hold-detail.html")
    if os.path.exists(dist_html):
        return send_from_directory(dist_dir, 'hold-detail.html')

    safe_reason = html.escape(reason, quote=True)
    return missing_in_scope_asset_response('/hold-detail', (
        "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>Hold Detail - {safe_reason}</title>"
        "<script type=\"module\" src=\"/static/dist/hold-detail.js\"></script>"
        f"<meta name=\"hold-reason\" content=\"{safe_reason}\">"
        "</head><body><div id='app'></div></body></html>",
        200,
    ))


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

    include_dummy = parse_bool_query(request.args.get('include_dummy'))

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

    include_dummy = parse_bool_query(request.args.get('include_dummy'))

    result = get_hold_detail_distribution(
        reason=reason,
        include_dummy=include_dummy
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_bp.route('/api/wip/hold-detail/lots')
@_HOLD_LOTS_RATE_LIMIT
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
    include_dummy = parse_bool_query(request.args.get('include_dummy'))
    page = request.args.get('page', 1, type=int)
    per_page_value = request.args.get('per_page', 50, type=int)
    if per_page_value is None:
        per_page_value = 50
    per_page = min(max(per_page_value, 1), 200)

    if page is None or page < 1:
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
