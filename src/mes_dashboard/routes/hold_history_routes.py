# -*- coding: utf-8 -*-
"""Hold History page route and API endpoints."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Tuple

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.hold_history_service import (
    get_hold_history_duration,
    get_hold_history_list,
    get_hold_history_reason_pareto,
    get_hold_history_trend,
)

hold_history_bp = Blueprint('hold_history', __name__)

_HOLD_HISTORY_TREND_RATE_LIMIT = configured_rate_limit(
    bucket='hold-history-trend',
    max_attempts_env='HOLD_HISTORY_TREND_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_HISTORY_TREND_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=60,
    default_window_seconds=60,
)

_HOLD_HISTORY_LIST_RATE_LIMIT = configured_rate_limit(
    bucket='hold-history-list',
    max_attempts_env='HOLD_HISTORY_LIST_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_HISTORY_LIST_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=90,
    default_window_seconds=60,
)

_VALID_HOLD_TYPES = {'quality', 'non-quality', 'all'}
_VALID_RECORD_TYPES = {'new', 'on_hold', 'released'}
_VALID_DURATION_RANGES = {'<4h', '4-24h', '1-3d', '>3d'}


def _parse_date_range() -> tuple[Optional[str], Optional[str], Optional[tuple[dict, int]]]:
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    if not start_date or not end_date:
        return None, None, ({'success': False, 'error': '缺少必要參數: start_date, end_date'}, 400)

    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return None, None, ({'success': False, 'error': '日期格式錯誤，請使用 YYYY-MM-DD'}, 400)

    if end < start:
        return None, None, ({'success': False, 'error': 'end_date 不可早於 start_date'}, 400)

    return start_date, end_date, None


def _parse_hold_type(default: str = 'quality') -> tuple[Optional[str], Optional[tuple[dict, int]]]:
    raw = request.args.get('hold_type', '').strip().lower()
    hold_type = raw or default
    if hold_type not in _VALID_HOLD_TYPES:
        return None, (
            {'success': False, 'error': 'Invalid hold_type. Use quality, non-quality, or all'},
            400,
        )
    return hold_type, None


def _parse_record_type(default: str = 'new') -> tuple[Optional[str], Optional[tuple[dict, int]]]:
    raw = request.args.get('record_type', '').strip().lower()
    record_type = raw or default
    parts = [p.strip() for p in record_type.split(',') if p.strip()]
    if not parts:
        parts = [default]
    for part in parts:
        if part not in _VALID_RECORD_TYPES:
            return None, (
                {'success': False, 'error': 'Invalid record_type. Use new, on_hold, or released'},
                400,
            )
    return ','.join(parts), None


@hold_history_bp.route('/hold-history')
def hold_history_page():
    """Render Hold History page from static Vite output."""
    dist_dir = os.path.join(current_app.static_folder or '', 'dist')
    dist_html = os.path.join(dist_dir, 'hold-history.html')
    if os.path.exists(dist_html):
        return send_from_directory(dist_dir, 'hold-history.html')

    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>Hold History</title>'
        '<script type="module" src="/static/dist/hold-history.js"></script>'
        '</head><body><div id="app"></div></body></html>',
        200,
    )


@hold_history_bp.route('/api/hold-history/trend')
@_HOLD_HISTORY_TREND_RATE_LIMIT
def api_hold_history_trend():
    """Return daily hold history trend data."""
    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    result = get_hold_history_trend(start_date, end_date)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_history_bp.route('/api/hold-history/reason-pareto')
def api_hold_history_reason_pareto():
    """Return hold reason Pareto data."""
    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    hold_type, hold_type_error = _parse_hold_type(default='quality')
    if hold_type_error:
        return jsonify(hold_type_error[0]), hold_type_error[1]

    record_type, record_type_error = _parse_record_type()
    if record_type_error:
        return jsonify(record_type_error[0]), record_type_error[1]

    result = get_hold_history_reason_pareto(start_date, end_date, hold_type, record_type)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_history_bp.route('/api/hold-history/duration')
def api_hold_history_duration():
    """Return hold duration distribution data."""
    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    hold_type, hold_type_error = _parse_hold_type(default='quality')
    if hold_type_error:
        return jsonify(hold_type_error[0]), hold_type_error[1]

    record_type, record_type_error = _parse_record_type()
    if record_type_error:
        return jsonify(record_type_error[0]), record_type_error[1]

    result = get_hold_history_duration(start_date, end_date, hold_type, record_type)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@hold_history_bp.route('/api/hold-history/list')
@_HOLD_HISTORY_LIST_RATE_LIMIT
def api_hold_history_list():
    """Return paginated hold detail list."""
    start_date, end_date, date_error = _parse_date_range()
    if date_error:
        return jsonify(date_error[0]), date_error[1]

    hold_type, hold_type_error = _parse_hold_type(default='quality')
    if hold_type_error:
        return jsonify(hold_type_error[0]), hold_type_error[1]

    record_type, record_type_error = _parse_record_type()
    if record_type_error:
        return jsonify(record_type_error[0]), record_type_error[1]

    reason = request.args.get('reason', '').strip() or None

    raw_duration = request.args.get('duration_range', '').strip() or None
    if raw_duration and raw_duration not in _VALID_DURATION_RANGES:
        return jsonify({'success': False, 'error': 'Invalid duration_range'}), 400
    duration_range = raw_duration

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    if page is None:
        page = 1
    if per_page is None:
        per_page = 50

    page = max(page, 1)
    per_page = max(1, min(per_page, 200))

    result = get_hold_history_list(
        start_date=start_date,
        end_date=end_date,
        hold_type=hold_type,
        reason=reason,
        record_type=record_type,
        duration_range=duration_range,
        page=page,
        per_page=per_page,
    )
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
