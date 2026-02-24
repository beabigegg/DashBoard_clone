# -*- coding: utf-8 -*-
"""Query Tool API routes.

Contains Flask Blueprint for batch tracing and equipment period query endpoints:
- LOT resolution (LOT ID / Serial Number / Work Order → CONTAINERID)
- LOT production history and adjacent lots
- LOT associations (materials, rejects, holds, jobs)
- Equipment period queries (status hours, lots, materials, rejects, jobs)
- CSV export functionality
"""

import hashlib

from flask import Blueprint, jsonify, request, Response, render_template, current_app

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.modernization_policy import maybe_redirect_to_canonical_shell
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
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
    export_to_csv,
    generate_csv_stream,
    validate_date_range,
    validate_lot_input,
    validate_equipment_input,
)


def _resolve_export_cids(params: dict) -> list[str]:
    """Extract container_ids from export params, supporting both batch and single."""
    cids = params.get('container_ids') or []
    if isinstance(cids, list) and cids:
        return [c for c in cids if c]
    single = params.get('container_id')
    return [single] if single else []

# Create Blueprint
query_tool_bp = Blueprint('query_tool', __name__)

_QUERY_TOOL_RESOLVE_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-resolve",
    max_attempts_env="QT_RESOLVE_RATE_MAX_REQUESTS",
    window_seconds_env="QT_RESOLVE_RATE_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)
_QUERY_TOOL_HISTORY_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-history",
    max_attempts_env="QT_HISTORY_RATE_MAX_REQUESTS",
    window_seconds_env="QT_HISTORY_RATE_WINDOW_SECONDS",
    default_max_attempts=20,
    default_window_seconds=60,
)
_QUERY_TOOL_ASSOC_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-association",
    max_attempts_env="QT_ASSOC_RATE_MAX_REQUESTS",
    window_seconds_env="QT_ASSOC_RATE_WINDOW_SECONDS",
    default_max_attempts=20,
    default_window_seconds=60,
)
_QUERY_TOOL_ADJACENT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-adjacent",
    max_attempts_env="QT_ADJACENT_RATE_MAX_REQUESTS",
    window_seconds_env="QT_ADJACENT_RATE_WINDOW_SECONDS",
    default_max_attempts=20,
    default_window_seconds=60,
)
_QUERY_TOOL_EQUIPMENT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-equipment",
    max_attempts_env="QT_EQUIP_RATE_MAX_REQUESTS",
    window_seconds_env="QT_EQUIP_RATE_WINDOW_SECONDS",
    default_max_attempts=5,
    default_window_seconds=60,
)
_QUERY_TOOL_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="query-tool-export",
    max_attempts_env="QT_EXPORT_RATE_MAX_REQUESTS",
    window_seconds_env="QT_EXPORT_RATE_WINDOW_SECONDS",
    default_max_attempts=3,
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
    return jsonify({'error': f'container_ids 數量不可超過 {max_ids} 筆'}), 413


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
        return jsonify({'error': payload_error.message}), payload_error.status_code

    input_type = data.get('input_type')
    values = data.get('values', [])

    # Validate input type
    valid_types = ['lot_id', 'wafer_lot', 'serial_number', 'work_order', 'gd_work_order', 'gd_lot_id']
    if input_type not in valid_types:
        return jsonify({'error': f'不支援的查詢類型: {input_type}'}), 400

    # Validate values
    validation_error = validate_lot_input(input_type, values)
    if validation_error:
        return jsonify({'error': validation_error}), 400

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
            return jsonify(cached)

    result = resolve_lots(input_type, values)

    if 'error' in result:
        return jsonify(result), 400

    if cache_key is not None:
        cache_set(cache_key, result, ttl=60)

    return jsonify(result)


# ============================================================
# LOT History API
# ============================================================

@query_tool_bp.route('/api/query-tool/lot-history', methods=['GET'])
@_QUERY_TOOL_HISTORY_RATE_LIMIT
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

    # Batch mode: container_ids takes precedence
    if container_ids_param:
        cids = [c.strip() for c in container_ids_param.split(',') if c.strip()]
        if not cids:
            return jsonify({'error': '請指定 CONTAINERID'}), 400
        too_large = _reject_if_batch_too_large(cids)
        if too_large is not None:
            return too_large
        result = get_lot_history_batch(cids, workcenter_groups=workcenter_groups)
    elif container_id:
        result = get_lot_history(container_id, workcenter_groups=workcenter_groups)
    else:
        return jsonify({'error': '請指定 CONTAINERID'}), 400

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


# ============================================================
# Adjacent Lots API
# ============================================================

@query_tool_bp.route('/api/query-tool/adjacent-lots', methods=['GET'])
@_QUERY_TOOL_ADJACENT_RATE_LIMIT
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
        return jsonify({'error': '請指定設備和目標時間'}), 400

    result = get_adjacent_lots(equipment_id, target_time, time_window)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


# ============================================================
# LOT Associations API
# ============================================================

@query_tool_bp.route('/api/query-tool/lot-associations', methods=['GET'])
@_QUERY_TOOL_ASSOC_RATE_LIMIT
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

    valid_types = ['materials', 'rejects', 'holds', 'splits', 'jobs']
    if assoc_type not in valid_types:
        return jsonify({'error': f'不支援的關聯類型: {assoc_type}'}), 400

    # Batch mode for materials/rejects/holds
    batch_types = {'materials', 'rejects', 'holds'}
    if container_ids_param and assoc_type in batch_types:
        cids = [c.strip() for c in container_ids_param.split(',') if c.strip()]
        if not cids:
            return jsonify({'error': '請指定 CONTAINERID'}), 400
        too_large = _reject_if_batch_too_large(cids)
        if too_large is not None:
            return too_large
        result = get_lot_associations_batch(cids, assoc_type)
    else:
        if not container_id:
            return jsonify({'error': '請指定 CONTAINERID'}), 400

        if assoc_type == 'materials':
            result = get_lot_materials(container_id)
        elif assoc_type == 'rejects':
            result = get_lot_rejects(container_id)
        elif assoc_type == 'holds':
            result = get_lot_holds(container_id)
        elif assoc_type == 'splits':
            full_history = str(request.args.get('full_history', '')).strip().lower() in {'1', 'true', 'yes'}
            result = get_lot_splits(container_id, full_history=full_history)
        elif assoc_type == 'jobs':
            equipment_id = request.args.get('equipment_id')
            time_start = request.args.get('time_start')
            time_end = request.args.get('time_end')

            if not all([equipment_id, time_start, time_end]):
                return jsonify({'error': '查詢 JOB 需指定設備和時間範圍'}), 400

            result = get_lot_jobs(equipment_id, time_start, time_end)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


# ============================================================
# Equipment Period Query API
# ============================================================

@query_tool_bp.route('/api/query-tool/equipment-period', methods=['POST'])
@_QUERY_TOOL_EQUIPMENT_RATE_LIMIT
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
        return jsonify({'error': payload_error.message}), payload_error.status_code

    equipment_ids = data.get('equipment_ids', [])
    equipment_names = data.get('equipment_names', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    query_type = data.get('query_type')

    # Validate date range
    if not start_date or not end_date:
        return jsonify({'error': '請指定日期範圍'}), 400

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return jsonify({'error': validation_error}), 400

    # Validate query type
    valid_types = ['status_hours', 'lots', 'materials', 'rejects', 'jobs']
    if query_type not in valid_types:
        return jsonify({'error': f'不支援的查詢類型: {query_type}'}), 400

    # Execute query based on type
    if query_type == 'status_hours':
        if not equipment_ids:
            return jsonify({'error': '請選擇至少一台設備'}), 400
        result = get_equipment_status_hours(equipment_ids, start_date, end_date)

    elif query_type == 'lots':
        if not equipment_ids:
            return jsonify({'error': '請選擇至少一台設備'}), 400
        result = get_equipment_lots(equipment_ids, start_date, end_date)

    elif query_type == 'materials':
        if not equipment_names:
            return jsonify({'error': '請選擇至少一台設備'}), 400
        result = get_equipment_materials(equipment_names, start_date, end_date)

    elif query_type == 'rejects':
        if not equipment_names:
            return jsonify({'error': '請選擇至少一台設備'}), 400
        result = get_equipment_rejects(equipment_names, start_date, end_date)

    elif query_type == 'jobs':
        if not equipment_ids:
            return jsonify({'error': '請選擇至少一台設備'}), 400
        result = get_equipment_jobs(equipment_ids, start_date, end_date)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


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
            return jsonify({'error': '無法載入設備資料'}), 500

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

        return jsonify({
            'data': data,
            'total': len(data)
        })

    except Exception as exc:
        return jsonify({'error': f'載入設備資料失敗: {str(exc)}'}), 500


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
            return jsonify({'error': '無法載入站點群組資料'}), 500

        return jsonify({
            'data': groups,
            'total': len(groups)
        })

    except Exception as exc:
        return jsonify({'error': f'載入站點群組失敗: {str(exc)}'}), 500


# ============================================================
# CSV Export API
# ============================================================

@query_tool_bp.route('/api/query-tool/export-csv', methods=['POST'])
@_QUERY_TOOL_EXPORT_RATE_LIMIT
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
        return jsonify({'error': payload_error.message}), payload_error.status_code

    export_type = data.get('export_type')
    params = data.get('params', {})

    # Get data based on export type
    result = None
    filename = 'export.csv'

    try:
        if export_type == 'lot_history':
            cids = _resolve_export_cids(params)
            if not cids:
                return jsonify({'error': '請指定 CONTAINERID'}), 400
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
                return jsonify({'error': '請指定 CONTAINERID'}), 400
            if len(cids) > 1:
                result = get_lot_associations_batch(cids, 'materials')
            else:
                result = get_lot_materials(cids[0])
            filename = f'lot_raw_materials_{cids[0]}.csv'

        elif export_type == 'lot_rejects':
            cids = _resolve_export_cids(params)
            if not cids:
                return jsonify({'error': '請指定 CONTAINERID'}), 400
            if len(cids) > 1:
                result = get_lot_associations_batch(cids, 'rejects')
            else:
                result = get_lot_rejects(cids[0])
            filename = f'lot_rejects_{cids[0]}.csv'

        elif export_type == 'lot_holds':
            cids = _resolve_export_cids(params)
            if not cids:
                return jsonify({'error': '請指定 CONTAINERID'}), 400
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
                params.get('equipment_names', []),
                params.get('start_date'),
                params.get('end_date')
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
            return jsonify({'error': f'不支援的匯出類型: {export_type}'}), 400

        if result is None or 'error' in result:
            error_msg = result.get('error', '查詢失敗') if result else '查詢失敗'
            return jsonify({'error': error_msg}), 400

        export_data = result.get('data', [])
        if not export_data:
            return jsonify({'error': '查無資料'}), 404

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

        # Stream CSV response
        return Response(
            generate_csv_stream(export_data),
            mimetype='text/csv; charset=utf-8-sig',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )

    except Exception as exc:
        return jsonify({'error': f'匯出失敗: {str(exc)}'}), 500
