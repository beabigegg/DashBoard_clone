# -*- coding: utf-8 -*-
"""Query Tool API routes.

Contains Flask Blueprint for batch tracing and equipment period query endpoints:
- LOT resolution (LOT ID / Serial Number / Work Order → CONTAINERID)
- LOT production history and adjacent lots
- LOT associations (materials, rejects, holds, jobs)
- Equipment period queries (status hours, lots, materials, rejects, jobs)
- CSV export functionality
"""

import gc
import hashlib
import logging
import os
from functools import wraps

from flask import Blueprint, request, Response, render_template, current_app

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.database import DatabaseDegradedError
from mes_dashboard.core.modernization_policy import maybe_redirect_to_canonical_shell
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.heavy_query_telemetry import record_memory_error
from mes_dashboard.core.response import (
    success_response,
    validation_error,
    not_found_error,
    internal_error,
    query_timeout_error,
    service_unavailable_error,
    error_response,
    VALIDATION_ERROR,
)
from mes_dashboard.core.exceptions import (
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
)
from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_cost_policy import classify_query_cost
from mes_dashboard.services.async_query_job_service import (
    enqueue_query_job,
    is_async_available,
)
from mes_dashboard.core.permissions import get_owner_token

# ── Feature flag: RQ async dispatch for query-tool (query-path-c-elimination-cleanup) ──
# Default off; operators enable by setting QUERY_TOOL_USE_RQ=on.
# Frozen at import time — tests must use monkeypatch.setattr(), not monkeypatch.setenv().
_QUERY_TOOL_USE_RQ: bool = resolve_bool_flag("QUERY_TOOL_USE_RQ", default=False)

logger = logging.getLogger('mes_dashboard.query_tool_routes')


def map_service_errors(fn):
    """Decorator that maps typed service exceptions to HTTP responses.

    Catches each ``MesServiceError`` subclass from ``core.exceptions`` and
    returns the matching response helper.  Unknown exceptions are logged with
    a full traceback and returned as ``internal_error()``.

    Apply this decorator to every route handler that calls into
    ``query_tool_service`` so that the handler body never needs its own
    try/except for error-envelope construction.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DatabaseDegradedError:
            # Let app-level degraded handlers return retry-aware 503 responses.
            raise
        except UserInputError as e:
            return validation_error(e.message)
        except ResourceNotFoundError as e:
            return not_found_error(e.message)
        except QueryTimeoutError as e:
            return query_timeout_error(e.message)
        except DataContractError as e:
            logger.error(
                "data contract error in %s: %s (details=%s)",
                fn.__name__, e.message, e.details,
                exc_info=e.cause,
            )
            return internal_error(e.message)
        except InternalQueryError as e:
            logger.error(
                "internal query error in %s: %s",
                fn.__name__, e.message,
                exc_info=e.cause,
            )
            return internal_error(e.message)
        except Exception:
            logger.error(
                "unexpected error in %s",
                fn.__name__,
                exc_info=True,
            )
            return internal_error()
    return wrapper
from mes_dashboard.services.query_tool_service import (
    resolve_lots,
    get_lot_history,
    get_lot_history_batch,
    get_adjacent_lots,
    get_lot_materials,
    get_lot_rejects,
    get_lot_holds,
    get_lot_splits,
    get_lot_jobs,
    get_lot_jobs_with_history,
    get_lot_associations_batch,
    get_equipment_status_hours,
    get_equipment_lots,
    get_equipment_materials,
    get_equipment_rejects,
    get_equipment_jobs,
    resolve_lot_equipment,
    generate_csv_stream,
    validate_date_range,
    validate_lot_input,
)


def _resolve_export_cids(params: dict) -> list[str]:
    """Extract container_ids from export params, supporting both batch and single."""
    cids = params.get('container_ids') or []
    if isinstance(cids, list) and cids:
        return [c for c in cids if c]
    single = params.get('container_id')
    return [single] if single else []


def _memory_error_response(route_name: str, exc: MemoryError):
    record_memory_error(route_name, reason="rss_guard")
    return service_unavailable_error(str(exc))

# Create Blueprint
query_tool_bp = Blueprint('query_tool', __name__)
_QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE = int(os.getenv('QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE', '200'))
_QUERY_TOOL_DETAIL_MAX_PER_PAGE = int(os.getenv('QUERY_TOOL_DETAIL_MAX_PER_PAGE', '500'))

_QUERY_TOOL_RESOLVE_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-resolve",
    max_attempts_env="QT_RESOLVE_RATE_MAX_REQUESTS",
    window_seconds_env="QT_RESOLVE_RATE_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)
_QUERY_TOOL_HISTORY_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-history",
    max_attempts_env="QT_HISTORY_RATE_MAX_REQUESTS",
    window_seconds_env="QT_HISTORY_RATE_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)
_QUERY_TOOL_ASSOC_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-association",
    max_attempts_env="QT_ASSOC_RATE_MAX_REQUESTS",
    window_seconds_env="QT_ASSOC_RATE_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)
_QUERY_TOOL_ADJACENT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-adjacent",
    max_attempts_env="QT_ADJACENT_RATE_MAX_REQUESTS",
    window_seconds_env="QT_ADJACENT_RATE_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)
_QUERY_TOOL_EQUIPMENT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-equipment",
    max_attempts_env="QT_EQUIP_RATE_MAX_REQUESTS",
    window_seconds_env="QT_EQUIP_RATE_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)
_QUERY_TOOL_LOT_EQUIP_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-lot-equipment",
    max_attempts_env="QT_LOT_EQUIP_RATE_MAX_REQUESTS",
    window_seconds_env="QT_LOT_EQUIP_RATE_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)
_QUERY_TOOL_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-export",
    max_attempts_env="QT_EXPORT_RATE_MAX_REQUESTS",
    window_seconds_env="QT_EXPORT_RATE_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)


def _query_tool_max_container_ids() -> int:
    try:
        value = int(current_app.config.get("QUERY_TOOL_MAX_CONTAINER_IDS", 200))
    except Exception:
        value = 200
    return max(value, 1)


def _reject_if_batch_too_large(container_ids: list[str]):
    max_ids = _query_tool_max_container_ids()
    if len(container_ids) <= max_ids:
        return None
    return error_response(VALIDATION_ERROR, f'container_ids 數量不可超過 {max_ids} 筆', status_code=413)


def _sanitize_page(value: str | int | None) -> int:
    try:
        return max(int(value or 1), 1)
    except Exception:
        return 1


def _sanitize_per_page(value: str | int | None) -> int:
    try:
        per_page = int(value or _QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE)
    except Exception:
        per_page = _QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE
    return min(max(per_page, 1), max(_QUERY_TOOL_DETAIL_MAX_PER_PAGE, 1))


def _format_lot_materials_export_rows(rows):
    """Normalize LOT material export columns for UI/CSV consistency."""
    normalized_rows = []
    for row in rows or []:
        lot_id = row.get('CONTAINERNAME') or row.get('CONTAINERID') or ''
        normalized_rows.append({
            'LOT ID': lot_id,
            'MATERIALPARTNAME': row.get('MATERIALPARTNAME', ''),
            'MATERIALLOTNAME': row.get('MATERIALLOTNAME', ''),
            'QTYCONSUMED': row.get('QTYCONSUMED', ''),
            'WORKCENTERNAME': row.get('WORKCENTERNAME', ''),
            'SPECNAME': row.get('SPECNAME', ''),
            'EQUIPMENTNAME': row.get('EQUIPMENTNAME', ''),
            'TXNDATE': row.get('TXNDATE', ''),
        })
    return normalized_rows


def _format_lot_holds_export_rows(rows):
    """Normalize LOT hold export columns for UI/CSV consistency."""
    normalized_rows = []
    for row in rows or []:
        lot_id = row.get('CONTAINERNAME') or row.get('CONTAINERID') or ''
        normalized_rows.append({
            'LOT ID': lot_id,
            'WORKCENTERNAME': row.get('WORKCENTERNAME', ''),
            'HOLDTXNDATE': row.get('HOLDTXNDATE', ''),
            'RELEASETXNDATE': row.get('RELEASETXNDATE', ''),
            'HOLD_STATUS': row.get('HOLD_STATUS', ''),
            'HOLD_HOURS': row.get('HOLD_HOURS', ''),
            'HOLDREASONNAME': row.get('HOLDREASONNAME', ''),
            'HOLDCOMMENTS': row.get('HOLDCOMMENTS', ''),
            'HOLDEMP': row.get('HOLDEMP', ''),
            'HOLDEMPDEPTNAME': row.get('HOLDEMPDEPTNAME', ''),
            'RELEASEEMP': row.get('RELEASEEMP', ''),
            'RELEASECOMMENTS': row.get('RELEASECOMMENTS', ''),
            'NCRID': row.get('NCRID', ''),
        })
    return normalized_rows


def _format_equipment_lots_export_rows(rows):
    """Normalize equipment lots export columns for UI/CSV consistency."""
    normalized_rows = []
    for row in rows or []:
        normalized_rows.append({
            'LOT ID': row.get('CONTAINERNAME') or row.get('CONTAINERID') or '',
            'WAFER LOT': row.get('WAFER_LOT_ID', ''),
            'TYPE': row.get('PJ_TYPE', ''),
            'BOP': row.get('PJ_BOP', ''),
            'SPECNAME': row.get('SPECNAME', ''),
            'WORKORDER': row.get('PJ_WORKORDER', ''),
            'TRACKINTIMESTAMP': row.get('TRACKINTIMESTAMP', ''),
            'TRACKOUTTIMESTAMP': row.get('TRACKOUTTIMESTAMP', ''),
            'TRACKINQTY': row.get('TRACKINQTY', ''),
            'TRACKOUTQTY': row.get('TRACKOUTQTY', ''),
            'EQUIPMENTNAME': row.get('EQUIPMENTNAME', ''),
            'WORKCENTERNAME': row.get('WORKCENTERNAME', ''),
            'PRODUCTLINENAME': row.get('PRODUCTLINENAME', ''),
        })
    return normalized_rows


_LOT_HISTORY_COLUMN_RENAMES = {
    'CONTAINERNAME': 'LOT ID',
    'PJ_TYPE': 'TYPE',
    'PJ_BOP': 'BOP',
    'PJ_WORKORDER': 'WORKORDER',
}

_LOT_HISTORY_HIDDEN = {'CONTAINERID', 'EQUIPMENTID', 'RESOURCEID'}


def _format_lot_history_export_rows(rows):
    """Rename columns in lot history export to match frontend labels."""
    normalized_rows = []
    for row in rows or []:
        out = {}
        for key, value in row.items():
            if key in _LOT_HISTORY_HIDDEN:
                continue
            label = _LOT_HISTORY_COLUMN_RENAMES.get(key, key)
            out[label] = value if value is not None else ''
        normalized_rows.append(out)
    return normalized_rows


def _format_lot_rejects_export_rows(rows):
    """Rename CONTAINERNAME to LOT ID in lot rejects export."""
    normalized_rows = []
    for row in rows or []:
        out = {}
        for key, value in row.items():
            if key == 'CONTAINERID':
                continue
            if key == 'CONTAINERNAME':
                out['LOT ID'] = value or ''
            else:
                out[key] = value if value is not None else ''
        normalized_rows.append(out)
    return normalized_rows


def _format_lot_jobs_export_rows(rows):
    """Rename CONTAINERNAMES to LOT ID in lot jobs export."""
    normalized_rows = []
    for row in rows or []:
        out = {}
        for key, value in row.items():
            if key == 'CONTAINERNAMES':
                out['LOT ID'] = value or ''
            else:
                out[key] = value if value is not None else ''
        normalized_rows.append(out)
    return normalized_rows


# ============================================================
# Page Route
# ============================================================

@query_tool_bp.route('/query-tool')
def query_tool_page():
    """Render the query tool page."""
    canonical_redirect = maybe_redirect_to_canonical_shell('/query-tool')
    if canonical_redirect is not None:
        return canonical_redirect
    return render_template('query_tool.html')


# ============================================================
# LOT Resolution API
# ============================================================

@query_tool_bp.route('/api/query-tool/resolve', methods=['POST'])
@_QUERY_TOOL_RESOLVE_RATE_LIMIT
@map_service_errors
def resolve_lot_input():
    """Resolve user input to CONTAINERID list.

    Expects JSON body:
    {
        "input_type": "lot_id" | "wafer_lot" | "serial_number" | "work_order" | "gd_work_order" | "gd_lot_id",
        "values": ["value1", "value2", ...]
    }

    Returns:
    {
        "data": [{"container_id": "...", "input_value": "..."}, ...],
        "total": 10,
        "input_count": 5,
        "not_found": ["value3"]
    }
    """
    data, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    input_type = data.get('input_type')
    values = data.get('values', [])

    # Validate input type
    valid_types = ['lot_id', 'wafer_lot', 'serial_number', 'work_order', 'gd_work_order', 'gd_lot_id']
    if input_type not in valid_types:
        return validation_error(f'不支援的查詢類型: {input_type}')

    # Validate values
    lot_input_err = validate_lot_input(input_type, values)
    if lot_input_err:
        return validation_error(lot_input_err)

    cache_values = [
        v.strip()
        for v in values
        if isinstance(v, str) and v.strip()
    ]
    cache_key = None
    if cache_values:
        values_hash = hashlib.md5(
            "|".join(sorted(cache_values)).encode("utf-8")
        ).hexdigest()[:16]
        cache_key = f"qt:resolve:{input_type}:{values_hash}"
        cached = cache_get(cache_key)
        if cached is not None:
            return success_response(cached)

    result = resolve_lots(input_type, values)

    if cache_key is not None:
        cache_set(cache_key, result, ttl=60)

    return success_response(result)


# ============================================================
# LOT History API
# ============================================================

@query_tool_bp.route('/api/query-tool/lot-history', methods=['GET'])
@_QUERY_TOOL_HISTORY_RATE_LIMIT
@map_service_errors
def query_lot_history():
    """Query production history for one or more LOTs.

    Query params:
        container_id: Single CONTAINERID (16-char hex)
        container_ids: Comma-separated CONTAINERIDs (batch mode)
        workcenter_groups: Optional comma-separated list of WORKCENTER_GROUP names

    When container_ids is provided, uses batch query (single EventFetcher call).
    Falls back to container_id for single-CID requests.
    """
    container_ids_param = request.args.get('container_ids')
    container_id = request.args.get('container_id')
    workcenter_groups_param = request.args.get('workcenter_groups')

    # Parse workcenter_groups if provided
    workcenter_groups = None
    if workcenter_groups_param:
        workcenter_groups = [
            g.strip() for g in workcenter_groups_param.split(',') if g.strip()
        ]
    page = _sanitize_page(request.args.get('page'))
    per_page = _sanitize_per_page(request.args.get('per_page'))

    # Batch mode: container_ids takes precedence
    if container_ids_param:
        cids = [c.strip() for c in container_ids_param.split(',') if c.strip()]
        if not cids:
            return validation_error('請指定 CONTAINERID')
        too_large = _reject_if_batch_too_large(cids)
        if too_large is not None:
            return too_large
        try:
            result = get_lot_history_batch(
                cids,
                workcenter_groups=workcenter_groups,
                page=page,
                per_page=per_page,
            )
        except MemoryError as exc:
            return _memory_error_response("query_tool.lot_history", exc)
    elif container_id:
        try:
            result = get_lot_history(
                container_id,
                workcenter_groups=workcenter_groups,
                page=page,
                per_page=per_page,
            )
        except MemoryError as exc:
            return _memory_error_response("query_tool.lot_history", exc)
    else:
        return validation_error('請指定 CONTAINERID')

    resp, status = success_response(result)
    total = result.get('total', 0)
    if total > 10000:
        gc.collect()
    return resp, status


# ============================================================
# Adjacent Lots API
# ============================================================

@query_tool_bp.route('/api/query-tool/adjacent-lots', methods=['GET'])
@_QUERY_TOOL_ADJACENT_RATE_LIMIT
@map_service_errors
def query_adjacent_lots():
    """Query adjacent lots (前後批) for a specific equipment.

    Finds lots before/after target on same equipment until different PJ_TYPE,
    with minimum 3 lots in each direction.

    Query params:
        equipment_id: Equipment ID
        target_time: Target lot's TRACKINTIMESTAMP (ISO format)
        time_window: Time window in hours (optional, default 24)

    Returns adjacent lots with relative position.
    """
    equipment_id = request.args.get('equipment_id')
    target_time = request.args.get('target_time')
    time_window = request.args.get('time_window', 24, type=int)

    if not all([equipment_id, target_time]):
        return validation_error('請指定設備和目標時間')

    result = get_adjacent_lots(equipment_id, target_time, time_window)

    return success_response(result)


# ============================================================
# LOT Associations API
# ============================================================

@query_tool_bp.route('/api/query-tool/lot-associations', methods=['GET'])
@_QUERY_TOOL_ASSOC_RATE_LIMIT
@map_service_errors
def query_lot_associations():
    """Query association data for one or more LOTs.

    Query params:
        container_id: Single CONTAINERID (16-char hex)
        container_ids: Comma-separated CONTAINERIDs (batch mode)
        type: Association type ('materials', 'rejects', 'holds', 'jobs')
        equipment_id: Equipment ID (required for 'jobs' type)
        time_start: Start time (required for 'jobs' type)
        time_end: End time (required for 'jobs' type)

    When container_ids is provided for materials/rejects/holds, uses batch query.
    """
    container_ids_param = request.args.get('container_ids')
    container_id = request.args.get('container_id')
    assoc_type = request.args.get('type')
    page = _sanitize_page(request.args.get('page'))
    per_page = _sanitize_per_page(request.args.get('per_page'))

    valid_types = ['materials', 'rejects', 'holds', 'splits', 'jobs']
    if assoc_type not in valid_types:
        return validation_error(f'不支援的關聯類型: {assoc_type}')

    # Batch mode for materials/rejects/holds
    batch_types = {'materials', 'rejects', 'holds'}
    if container_ids_param and assoc_type in batch_types:
        cids = [c.strip() for c in container_ids_param.split(',') if c.strip()]
        if not cids:
            return validation_error('請指定 CONTAINERID')
        too_large = _reject_if_batch_too_large(cids)
        if too_large is not None:
            return too_large
        try:
            result = get_lot_associations_batch(
                cids,
                assoc_type,
                page=page,
                per_page=per_page,
            )
        except MemoryError as exc:
            return _memory_error_response(f"query_tool.lot_associations.{assoc_type}", exc)
    else:
        if not container_id:
            return validation_error('請指定 CONTAINERID')

        if assoc_type == 'materials':
            result = get_lot_materials(container_id, page=page, per_page=per_page)
        elif assoc_type == 'rejects':
            result = get_lot_rejects(container_id, page=page, per_page=per_page)
        elif assoc_type == 'holds':
            result = get_lot_holds(container_id, page=page, per_page=per_page)
        elif assoc_type == 'splits':
            full_history = str(request.args.get('full_history', '')).strip().lower() in {'1', 'true', 'yes'}
            result = get_lot_splits(container_id, full_history=full_history)
        elif assoc_type == 'jobs':
            equipment_id = request.args.get('equipment_id')
            time_start = request.args.get('time_start')
            time_end = request.args.get('time_end')

            if not all([equipment_id, time_start, time_end]):
                return validation_error('查詢 JOB 需指定設備和時間範圍')

            result = get_lot_jobs(equipment_id, time_start, time_end)

    return success_response(result)


# ============================================================
# Equipment Period Query API
# ============================================================

@query_tool_bp.route('/api/query-tool/equipment-period', methods=['POST'])
@_QUERY_TOOL_EQUIPMENT_RATE_LIMIT
@map_service_errors
def query_equipment_period():
    """Query equipment data for a time period.

    Expects JSON body:
    {
        "equipment_ids": ["id1", "id2", ...],
        "equipment_names": ["name1", "name2", ...],
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "query_type": "status_hours" | "lots" | "materials" | "rejects" | "jobs"
    }

    Returns data based on query_type.
    """
    data, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    equipment_ids = data.get('equipment_ids', [])
    equipment_names = data.get('equipment_names', [])
    workcenter_groups = data.get('workcenter_groups') or []
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    query_type = data.get('query_type')
    page = _sanitize_page(data.get('page'))
    per_page = _sanitize_per_page(data.get('per_page'))

    # Validate date range
    if not start_date or not end_date:
        return validation_error('請指定日期範圍')

    date_range_err = validate_date_range(start_date, end_date)
    if date_range_err:
        return validation_error(date_range_err)

    # Validate query type
    valid_types = ['status_hours', 'lots', 'materials', 'rejects', 'jobs']
    if query_type not in valid_types:
        return validation_error(f'不支援的查詢類型: {query_type}')

    # ── RQ async dispatch (QUERY_TOOL_USE_RQ=on, query-path-c-elimination-cleanup IP-4) ──
    # When flag is on and classify_query_cost returns ASYNC, dispatch to RQ and
    # return 202+job_id instead of blocking the gunicorn worker.
    # Falls through to sync path when: flag=off (default), query is SYNC,
    # or RQ is unavailable.
    if _QUERY_TOOL_USE_RQ and is_async_available():
        _cost = classify_query_cost(
            domain="query_tool",
            params={"date_from": start_date, "date_to": end_date},
        )
        if _cost == "ASYNC":
            _owner = get_owner_token()
            _params = dict(
                owner=_owner,
                query_type="equipment_period",
                query_sub_type=query_type,
                equipment_ids=equipment_ids,
                equipment_names=equipment_names,
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=workcenter_groups,
                page=page,
                per_page=per_page,
            )
            job_id, err, status_hint = enqueue_query_job(
                "query-tool",
                owner=_owner,
                params=_params,
                sync_fallback_allowed=True,
            )
            if job_id is not None:
                return success_response(
                    {
                        "async": True,
                        "job_id": job_id,
                        "status_url": f"/api/job/{job_id}?prefix=query-tool",
                    },
                    status_code=202,
                )
            # enqueue failed — fall through to sync path

    # Execute query based on type (sync path — default or flag-off)
    try:
        if query_type == 'status_hours':
            if not equipment_ids:
                return validation_error('請選擇至少一台設備')
            result = get_equipment_status_hours(equipment_ids, start_date, end_date)

        elif query_type == 'lots':
            if not equipment_ids:
                return validation_error('請選擇至少一台設備')
            result = get_equipment_lots(
                equipment_ids,
                start_date,
                end_date,
                page=page,
                per_page=per_page,
            )

        elif query_type == 'materials':
            if not equipment_names:
                return validation_error('請選擇至少一台設備')
            result = get_equipment_materials(equipment_names, start_date, end_date)

        elif query_type == 'rejects':
            if not equipment_ids:
                return validation_error('請選擇至少一台設備')
            result = get_equipment_rejects(
                equipment_ids=equipment_ids,
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=workcenter_groups or None,
            )

        elif query_type == 'jobs':
            if not equipment_ids:
                return validation_error('請選擇至少一台設備')
            result = get_equipment_jobs(equipment_ids, start_date, end_date)
    except MemoryError as exc:
        return _memory_error_response(f"query_tool.equipment_period.{query_type}", exc)

    resp, status = success_response(result)
    total = result.get('total', 0)
    if total > 10000:
        gc.collect()
    return resp, status


# ============================================================
# Equipment List API (for selection UI)
# ============================================================

@query_tool_bp.route('/api/query-tool/equipment-list', methods=['GET'])
def get_equipment_list():
    """Get available equipment for selection.

    Returns equipment from cache for equipment selection UI.
    """
    from mes_dashboard.services.resource_cache import get_all_resources

    try:
        resources = get_all_resources()
        if not resources:
            return internal_error('無法載入設備資料')

        # Return minimal data for selection UI
        data = []
        for r in resources:
            data.append({
                'RESOURCEID': r.get('RESOURCEID'),
                'RESOURCENAME': r.get('RESOURCENAME'),
                'WORKCENTERNAME': r.get('WORKCENTERNAME'),
                'RESOURCEFAMILYNAME': r.get('RESOURCEFAMILYNAME'),
            })

        # Sort by WORKCENTERNAME, then RESOURCENAME
        data.sort(key=lambda x: (x.get('WORKCENTERNAME', ''), x.get('RESOURCENAME', '')))

        return success_response({
            'data': data,
            'total': len(data)
        })

    except Exception as exc:
        return internal_error(f'載入設備資料失敗: {str(exc)}')


# ============================================================
# Workcenter Groups API (for filtering)
# ============================================================

@query_tool_bp.route('/api/query-tool/workcenter-groups', methods=['GET'])
def get_workcenter_groups_list():
    """Get available workcenter groups for filtering.

    Returns workcenter groups list sorted by sequence.
    Used for production history filtering UI.
    """
    from mes_dashboard.services.filter_cache import get_workcenter_groups

    try:
        groups = get_workcenter_groups()
        if groups is None:
            return internal_error('無法載入站點群組資料')

        return success_response({
            'data': groups,
            'total': len(groups)
        })

    except Exception as exc:
        return internal_error(f'載入站點群組失敗: {str(exc)}')


# ============================================================
# Lot → Equipment Lookup API
# ============================================================

@query_tool_bp.route('/api/query-tool/lot-equipment-lookup', methods=['POST'])
@_QUERY_TOOL_LOT_EQUIP_RATE_LIMIT
@map_service_errors
def lookup_lot_equipment():
    """Look up which equipment processed given lots at a workcenter group.

    Expects JSON body:
    {
        "input_type": "lot_id" | "work_order",
        "values": ["LOT001", "LOT002"],
        "workcenter_groups": ["焊接_DB", "焊接_WB"]
    }

    Returns equipment IDs/names, observed date range, and trace_map
    for lots that were traced to parent lots.
    """
    data, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    input_type = data.get('input_type', 'lot_id')
    values = data.get('values', [])
    workcenter_groups = data.get('workcenter_groups', [])

    if not values:
        return validation_error('請輸入至少一筆查詢條件')

    if input_type not in ('lot_id', 'work_order'):
        return validation_error(f'不支援的輸入類型: {input_type}')

    if not workcenter_groups:
        return validation_error('請選擇站點群組')

    try:
        result = resolve_lot_equipment(input_type, values, workcenter_groups)
    except MemoryError as exc:
        return _memory_error_response("query_tool.lot_equipment_lookup", exc)

    return success_response(result)


# ============================================================
# Equipment Recent Jobs API (for suspect context panel)
# ============================================================

@query_tool_bp.route('/api/query-tool/equipment-recent-jobs/<equipment_id>', methods=['GET'])
def get_equipment_recent_jobs_route(equipment_id):
    """Get recent JOB records for a specific equipment (last 30 days, top 5).

    Used by the suspect machine context panel in mid-section-defect analysis.
    """
    from mes_dashboard.services.query_tool_service import get_equipment_recent_jobs

    try:
        result = get_equipment_recent_jobs(equipment_id)
        return success_response(result)
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception as exc:
        return internal_error(f'載入維修紀錄失敗: {str(exc)}')


# ============================================================
# CSV Export API
# ============================================================

@query_tool_bp.route('/api/query-tool/export-csv', methods=['POST'])
@_QUERY_TOOL_EXPORT_RATE_LIMIT
@map_service_errors
def export_csv():
    """Export query results as CSV.

    Expects JSON body:
    {
        "export_type": "lot_history" | "adjacent_lots" | "lot_materials" |
                       "lot_rejects" | "lot_holds" | "lot_jobs" |
                       "equipment_status_hours" | "equipment_lots" |
                       "equipment_materials" | "equipment_rejects" | "equipment_jobs",
        "params": { ... query parameters ... }
    }

    Returns streaming CSV response.
    """
    data, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    export_type = data.get('export_type')
    params = data.get('params', {})

    # Get data based on export type
    result = None
    filename = 'export.csv'

    try:
        if export_type == 'lot_history':
            cids = _resolve_export_cids(params)
            if not cids:
                return validation_error('請指定 CONTAINERID')
            if len(cids) > 1:
                result = get_lot_history_batch(cids)
            else:
                result = get_lot_history(cids[0])
            filename = f'lot_history_{cids[0]}.csv'

        elif export_type == 'adjacent_lots':
            result = get_adjacent_lots(
                params.get('equipment_id'),
                params.get('target_time'),
                params.get('time_window', 24)
            )
            filename = 'adjacent_lots.csv'

        elif export_type == 'lot_materials':
            cids = _resolve_export_cids(params)
            if not cids:
                return validation_error('請指定 CONTAINERID')
            if len(cids) > 1:
                result = get_lot_associations_batch(cids, 'materials')
            else:
                result = get_lot_materials(cids[0])
            filename = f'lot_raw_materials_{cids[0]}.csv'

        elif export_type == 'lot_rejects':
            cids = _resolve_export_cids(params)
            if not cids:
                return validation_error('請指定 CONTAINERID')
            if len(cids) > 1:
                result = get_lot_associations_batch(cids, 'rejects')
            else:
                result = get_lot_rejects(cids[0])
            filename = f'lot_rejects_{cids[0]}.csv'

        elif export_type == 'lot_holds':
            cids = _resolve_export_cids(params)
            if not cids:
                return validation_error('請指定 CONTAINERID')
            if len(cids) > 1:
                result = get_lot_associations_batch(cids, 'holds')
            else:
                result = get_lot_holds(cids[0])
            filename = f'lot_holds_{cids[0]}.csv'

        elif export_type == 'lot_splits':
            container_id = params.get('container_id')
            result = get_lot_splits(container_id)
            # Flatten nested structure for CSV
            if result and 'data' in result:
                flat_data = []
                for item in result['data']:
                    serial_number = item.get('serial_number', '')
                    txn_date = item.get('txn_date', '')
                    for lot in item.get('lots', []):
                        flat_data.append({
                            '成品流水號': serial_number,
                            'LOT ID': lot.get('lot_id', ''),
                            '規格': lot.get('spec_name', ''),
                            '數量': lot.get('qty', ''),
                            '合併序號': lot.get('combine_seq', ''),
                            '交易時間': txn_date,
                        })
                result['data'] = flat_data
            filename = f'lot_splits_{container_id}.csv'

        elif export_type == 'lot_jobs':
            result = get_lot_jobs_with_history(
                params.get('equipment_id'),
                params.get('time_start'),
                params.get('time_end')
            )
            filename = 'lot_jobs.csv'

        elif export_type == 'equipment_status_hours':
            result = get_equipment_status_hours(
                params.get('equipment_ids', []),
                params.get('start_date'),
                params.get('end_date')
            )
            filename = 'equipment_status_hours.csv'

        elif export_type == 'equipment_lots':
            result = get_equipment_lots(
                params.get('equipment_ids', []),
                params.get('start_date'),
                params.get('end_date')
            )
            filename = 'equipment_lots.csv'

        elif export_type == 'equipment_materials':
            result = get_equipment_materials(
                params.get('equipment_names', []),
                params.get('start_date'),
                params.get('end_date')
            )
            filename = 'equipment_materials.csv'

        elif export_type == 'equipment_rejects':
            result = get_equipment_rejects(
                equipment_ids=params.get('equipment_ids', []),
                start_date=params.get('start_date'),
                end_date=params.get('end_date'),
            )
            filename = 'equipment_rejects.csv'

        elif export_type == 'equipment_jobs':
            result = get_equipment_jobs(
                params.get('equipment_ids', []),
                params.get('start_date'),
                params.get('end_date')
            )
            filename = 'equipment_jobs.csv'

        else:
            return validation_error(f'不支援的匯出類型: {export_type}')

        export_data = result.get('data', []) if result else []
        if not export_data:
            return not_found_error('查無資料')

        if export_type == 'lot_materials':
            export_data = _format_lot_materials_export_rows(export_data)
        elif export_type == 'lot_holds':
            export_data = _format_lot_holds_export_rows(export_data)
        elif export_type == 'equipment_lots':
            export_data = _format_equipment_lots_export_rows(export_data)
        elif export_type == 'lot_history':
            export_data = _format_lot_history_export_rows(export_data)
        elif export_type == 'lot_rejects':
            export_data = _format_lot_rejects_export_rows(export_data)
        elif export_type == 'lot_jobs':
            export_data = _format_lot_jobs_export_rows(export_data)

        # Stream CSV response
        return Response(
            generate_csv_stream(export_data),
            mimetype='text/csv; charset=utf-8-sig',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )

    except MemoryError as exc:
        return _memory_error_response("query_tool.export_csv", exc)
