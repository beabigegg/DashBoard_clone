# -*- coding: utf-8 -*-
"""Hold History page route and API endpoints.

Two-phase query pattern:
  POST /api/hold-history/query  → single Oracle query → cache → full response
  GET  /api/hold-history/view   → read cache → filtered views (no Oracle)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from flask import Blueprint, current_app, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    success_response,
    validation_error,
)
from mes_dashboard.core.modernization_policy import (
    missing_in_scope_asset_response,
    maybe_redirect_to_canonical_shell,
)
from mes_dashboard.services.hold_dataset_cache import (
    apply_view,
    execute_primary_query,
)

logger = logging.getLogger("mes_dashboard.hold_history_routes")

hold_history_bp = Blueprint('hold_history', __name__)

_HOLD_HISTORY_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket='hold-history-query',
    max_attempts_env='HOLD_HISTORY_TREND_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_HISTORY_TREND_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=60,
    default_window_seconds=60,
)

_HOLD_HISTORY_VIEW_RATE_LIMIT = configured_rate_limit(
    bucket='hold-history-view',
    max_attempts_env='HOLD_HISTORY_LIST_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_HISTORY_LIST_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=90,
    default_window_seconds=60,
)

_VALID_HOLD_TYPES = {'quality', 'non-quality', 'all'}
_VALID_RECORD_TYPES = {'new', 'on_hold', 'released'}
_VALID_DURATION_RANGES = {'<4h', '4-24h', '1-3d', '>3d'}


# ============================================================
# Helpers
# ============================================================


def _validate_date(value: str) -> Optional[str]:
    """Return ISO date string or None if invalid."""
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return value
    except (ValueError, TypeError):
        return None


def _normalize_hold_type(value: str, default: str = 'quality') -> str:
    v = str(value or default).strip().lower()
    return v if v in _VALID_HOLD_TYPES else default


def _normalize_record_type(value: str, default: str = 'new') -> Optional[str]:
    """Validate CSV record_type. Returns normalised string or None on error."""
    parts = [p.strip().lower() for p in str(value or default).split(',') if p.strip()]
    if not parts:
        parts = [default]
    for p in parts:
        if p not in _VALID_RECORD_TYPES:
            return None
    return ','.join(parts)


# ============================================================
# Page route
# ============================================================


@hold_history_bp.route('/hold-history')
def hold_history_page():
    """Render Hold History page from static Vite output."""
    canonical_redirect = maybe_redirect_to_canonical_shell('/hold-history')
    if canonical_redirect is not None:
        return canonical_redirect

    dist_dir = os.path.join(current_app.static_folder or '', 'dist')
    dist_html = os.path.join(dist_dir, 'hold-history.html')
    if os.path.exists(dist_html):
        return send_from_directory(dist_dir, 'hold-history.html')

    return missing_in_scope_asset_response('/hold-history', (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>Hold History</title>'
        '<script type="module" src="/static/dist/hold-history.js"></script>'
        '</head><body><div id="app"></div></body></html>',
        200,
    ))


# ============================================================
# POST /api/hold-history/query — primary query (single Oracle)
# ============================================================


@hold_history_bp.route('/api/hold-history/query', methods=['POST'])
@_HOLD_HISTORY_QUERY_RATE_LIMIT
def api_hold_history_query():
    """Execute primary Oracle query, cache, and return full result."""
    body = request.get_json(silent=True) or {}

    start_date = _validate_date(str(body.get('start_date', '')).strip())
    end_date = _validate_date(str(body.get('end_date', '')).strip())
    if not start_date or not end_date:
        return validation_error('缺少必要參數: start_date, end_date')

    if end_date < start_date:
        return validation_error('end_date 不可早於 start_date')

    hold_type = _normalize_hold_type(str(body.get('hold_type', '')))
    record_type = _normalize_record_type(str(body.get('record_type', '')))
    if record_type is None:
        return validation_error('Invalid record_type')

    try:
        result = execute_primary_query(
            start_date=start_date,
            end_date=end_date,
            hold_type=hold_type,
            record_type=record_type,
        )
        return success_response(result)
    except Exception as exc:
        logger.error("Hold history primary query failed: %s", exc)
        return internal_error()


# ============================================================
# GET /api/hold-history/view — supplementary view (cache only)
# ============================================================


@hold_history_bp.route('/api/hold-history/view')
@_HOLD_HISTORY_VIEW_RATE_LIMIT
def api_hold_history_view():
    """Read cached DataFrame, apply filters, return derived views."""
    query_id = request.args.get('query_id', '').strip()
    if not query_id:
        return validation_error('缺少 query_id')

    hold_type = _normalize_hold_type(request.args.get('hold_type', ''))
    reason = request.args.get('reason', '').strip() or None
    record_type = _normalize_record_type(request.args.get('record_type', ''))
    if record_type is None:
        return validation_error('Invalid record_type')

    raw_duration = request.args.get('duration_range', '').strip() or None
    if raw_duration and raw_duration not in _VALID_DURATION_RANGES:
        return validation_error('Invalid duration_range')

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    page = max(page or 1, 1)
    per_page = max(1, min(per_page or 50, 200))

    try:
        result = apply_view(
            query_id=query_id,
            hold_type=hold_type,
            reason=reason,
            record_type=record_type,
            duration_range=raw_duration,
            page=page,
            per_page=per_page,
        )
    except Exception as exc:
        logger.error("Hold history view failed: %s", exc)
        return internal_error()

    if result is None:
        return cache_expired_error()

    return success_response(result)
