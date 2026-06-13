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

from mes_dashboard.config.constants import (
    HOLD_TODAY_AUTO_REFRESH_SECONDS,
    HOLD_TODAY_MODE_ENABLED,
)
from typing import Optional

from flask import Blueprint, current_app, request, send_from_directory

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    service_unavailable_error,
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
from mes_dashboard.services.hold_today_snapshot_service import execute_today_snapshot
from mes_dashboard.core.database import DatabaseCircuitOpenError, DatabasePoolExhaustedError
from mes_dashboard.services.async_query_job_service import (
    enqueue_job_dynamic,
    is_async_available,
)
from mes_dashboard.core.permissions import get_owner_token

logger = logging.getLogger("mes_dashboard.hold_history_routes")

hold_history_bp = Blueprint('hold_history', __name__)

# ── Local-compute feature flags (Task 1.3) ────────────────────────────────────

_HOLD_LOCAL_COMPUTE_ENABLED = os.environ.get(
    "HOLD_HISTORY_LOCAL_COMPUTE_ENABLED", "true"
).strip().lower() in ("1", "true", "yes")

_HOLD_SPOOL_THRESHOLD = int(os.environ.get("HOLD_SPOOL_THRESHOLD", "5000"))
_HOLD_SPOOL_NAMESPACE = "hold_dataset"

# ── Async RQ path — env-contract §Async Worker — Hold History Query ───────────
# All four constants are frozen at import time (module-level).
# Tests must use monkeypatch.setattr(), never monkeypatch.setenv().
HOLD_ASYNC_ENABLED: bool = os.getenv(
    "HOLD_ASYNC_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")
HOLD_ASYNC_DAY_THRESHOLD: int = int(os.getenv("HOLD_ASYNC_DAY_THRESHOLD", "90"))
HOLD_WORKER_QUEUE: str = os.getenv("HOLD_WORKER_QUEUE", "hold-history-query")
HOLD_JOB_TIMEOUT_SECONDS: int = int(os.getenv("HOLD_JOB_TIMEOUT_SECONDS", "1800"))


# ── Spool metadata injection helpers (Tasks 1.2, 1.4) ────────────────────────


def _inject_hold_spool_info(data: dict, query_id: str) -> None:
    """Inject spool_download_url, total_row_count, and workcenter_mapping when eligible."""
    if not _HOLD_LOCAL_COMPUTE_ENABLED:
        return
    try:
        from mes_dashboard.core.query_spool_store import get_spool_metadata
        metadata = get_spool_metadata(_HOLD_SPOOL_NAMESPACE, query_id)
        if metadata is None:
            return
        row_count = int(metadata.get("row_count") or 0)
        data["total_row_count"] = row_count
        if row_count >= _HOLD_SPOOL_THRESHOLD:
            data["spool_download_url"] = (
                f"/api/spool/{_HOLD_SPOOL_NAMESPACE}/{query_id}.parquet"
            )
            _inject_workcenter_mapping(data)
    except Exception:
        pass  # Best-effort; must not break the view response


def _inject_workcenter_mapping(data: dict) -> None:
    """Attach workcenter → group mapping for frontend local compute."""
    try:
        from mes_dashboard.services.filter_cache import get_workcenter_mapping
        mapping = get_workcenter_mapping() or {}
        data["workcenter_mapping"] = {
            wc_name: info.get("group", wc_name) or wc_name
            for wc_name, info in mapping.items()
        }
    except Exception:
        pass

_HOLD_HISTORY_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket='hold-history-query',
    max_attempts_env='HOLD_HISTORY_TREND_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_HISTORY_TREND_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=60,
    default_window_seconds=60,
)

_HOLD_TODAY_SNAPSHOT_RATE_LIMIT = configured_rate_limit(
    bucket='hold-today-snapshot',
    max_attempts_env='HOLD_TODAY_SNAPSHOT_RATE_LIMIT_MAX_REQUESTS',
    window_seconds_env='HOLD_TODAY_SNAPSHOT_RATE_LIMIT_WINDOW_SECONDS',
    default_max_attempts=120,
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

    # ── Async RQ branch (HOLD_ASYNC_ENABLED + threshold + worker available) ──
    # Falls through to the sync 200 path on any false condition (AC-2, AC-8).
    if HOLD_ASYNC_ENABLED:
        from datetime import datetime as _dt
        try:
            sd = _dt.strptime(start_date, "%Y-%m-%d")
            ed = _dt.strptime(end_date, "%Y-%m-%d")
            day_span = (ed - sd).days
        except (ValueError, TypeError):
            day_span = 0
        if day_span >= HOLD_ASYNC_DAY_THRESHOLD:
            if is_async_available():
                _params = dict(
                    start_date=start_date,
                    end_date=end_date,
                    hold_type=hold_type,
                    record_type=record_type,
                )
                try:
                    job_id, err = enqueue_job_dynamic(
                        "hold-history",
                        owner=get_owner_token(),
                        params=_params,
                    )
                    if job_id is not None:
                        return success_response(
                            {
                                "async": True,
                                "job_id": job_id,
                                "status_url": f"/api/job/{job_id}?prefix=hold-history",
                            },
                            status_code=202,
                        )
                    # enqueue returned None — fall through to sync path
                except Exception:
                    pass  # Degradable async failure — fall through silently (AC-8)

    try:
        result = execute_primary_query(
            start_date=start_date,
            end_date=end_date,
            hold_type=hold_type,
            record_type=record_type,
        )
        _inject_hold_spool_info(result, result.get("query_id", ""))
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
    export_mode = request.args.get('export', '0') == '1'
    per_page = max(1, min(per_page or 50, 200))

    raw_sort_col = request.args.get('sort_col', '').strip() or 'holdDate'
    raw_sort_dir = request.args.get('sort_dir', '').strip().lower()
    if raw_sort_dir not in ('asc', 'desc'):
        raw_sort_dir = 'desc'

    try:
        result = apply_view(
            query_id=query_id,
            hold_type=hold_type,
            reason=reason,
            record_type=record_type,
            duration_range=raw_duration,
            page=page,
            per_page=per_page,
            export_mode=export_mode,
            sort_col=raw_sort_col,
            sort_dir=raw_sort_dir,
        )
    except Exception as exc:
        logger.error("Hold history view failed: %s", exc)
        return internal_error()

    if result is None:
        return cache_expired_error()

    _inject_hold_spool_info(result, query_id)
    return success_response(result)


# ============================================================
# GET /api/hold-history/config — feature flags for frontend
# ============================================================


@hold_history_bp.route('/api/hold-history/config')
def api_hold_history_config():
    """Return feature flags and client-side config for Hold History page."""
    return success_response({
        'today_mode_enabled': HOLD_TODAY_MODE_ENABLED,
        'auto_refresh_seconds': HOLD_TODAY_AUTO_REFRESH_SECONDS,
    })


# ============================================================
# POST /api/hold-history/today-snapshot — today-mode snapshot
# ============================================================


@hold_history_bp.route('/api/hold-history/today-snapshot', methods=['POST'])
@_HOLD_TODAY_SNAPSHOT_RATE_LIMIT
def api_hold_history_today_snapshot():
    """Return a snapshot for 當日 or 現況 mode.

    snapshot_mode: 'today' (當日, shift boundary) | 'current' (現況, live)
    """
    body = request.get_json(silent=True) or {}

    raw_snapshot_mode = str(body.get('snapshot_mode', 'today') or 'today').strip().lower()
    if raw_snapshot_mode not in ('today', 'current'):
        return validation_error(f'Invalid snapshot_mode: {raw_snapshot_mode!r}')

    hold_type = _normalize_hold_type(str(body.get('hold_type', '')))

    raw_record_type = str(body.get('record_type', 'on_hold')).strip()
    parts = [p.strip().lower() for p in raw_record_type.split(',') if p.strip()]
    if not parts:
        parts = ['on_hold']
    today_valid = {'on_hold', 'new', 'release'}
    for p in parts:
        if p not in today_valid:
            return validation_error(f'Invalid record_type for today mode: {p!r}')
    record_type = ','.join(parts)

    raw_reason = body.get('reason', '') or ''
    if not isinstance(raw_reason, str):
        return validation_error('Invalid reason: must be a string')
    reason = raw_reason.strip()
    if '\x00' in reason or len(reason) > 200:
        return validation_error('Invalid reason value')
    reason = reason or None

    raw_duration = str(body.get('duration_range', '') or '').strip() or None
    if raw_duration and raw_duration not in _VALID_DURATION_RANGES:
        return validation_error('Invalid duration_range')

    try:
        page = int(body.get('page', 1) or 1)
        per_page = int(body.get('per_page', 50) or 50)
    except (TypeError, ValueError):
        return validation_error('Invalid page or per_page: must be integers')
    page = max(page, 1)
    export_mode = bool(body.get('export'))
    per_page = max(1, min(per_page, 200))

    raw_sort_col_snap = str(body.get('sort_col', '') or '').strip() or 'holdDate'
    raw_sort_dir_snap = str(body.get('sort_dir', '') or '').strip().lower()
    if raw_sort_dir_snap not in ('asc', 'desc'):
        raw_sort_dir_snap = 'desc'

    try:
        result = execute_today_snapshot(
            snapshot_mode=raw_snapshot_mode,
            hold_type=hold_type,
            record_type=record_type,
            reason=reason,
            duration_range=raw_duration,
            page=page,
            per_page=per_page,
            export_mode=export_mode,
            sort_col=raw_sort_col_snap,
            sort_dir=raw_sort_dir_snap,
        )
        return success_response(result)
    except (DatabaseCircuitOpenError, DatabasePoolExhaustedError) as exc:
        logger.error("Hold today snapshot DB unavailable: %s", exc)
        return service_unavailable_error('database_unavailable')
    except Exception as exc:
        # Any service-level failure (including Oracle connection errors) is
        # treated as temporary unavailability, not an application bug.
        logger.error("Hold today snapshot failed: %s", exc)
        return service_unavailable_error('database_unavailable')
