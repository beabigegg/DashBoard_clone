# -*- coding: utf-8 -*-
"""Resource (Equipment) API routes for MES Dashboard.

Contains Flask Blueprint for resource/equipment-related API endpoints.
"""

import math
import logging
from flask import Blueprint, jsonify, request

from mes_dashboard.core.database import (
    get_db_connection,
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import INTERNAL_ERROR, error_response
from mes_dashboard.core.utils import get_days_back, parse_bool_query


def _clean_nan_values(data):
    """Convert NaN/NaT values to None for JSON serialization (depth-safe).

    Args:
        data: List of dicts or single dict.

    Returns:
        Cleaned data with NaN/NaT replaced by None.
    """
    def _normalize_scalar(value):
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, str) and value == 'NaT':
            return None
        try:
            if value != value:  # NaN check (NaN != NaN)
                return None
        except Exception:
            pass
        return value

    if isinstance(data, list):
        root: list = []
    elif isinstance(data, dict):
        root = {}
    else:
        return _normalize_scalar(data)

    stack = [(data, root)]
    seen: set[int] = {id(data)}

    while stack:
        source, target = stack.pop()
        if isinstance(source, list):
            for item in source:
                if isinstance(item, list):
                    item_id = id(item)
                    if item_id in seen:
                        target.append(None)
                        continue
                    child = []
                    target.append(child)
                    seen.add(item_id)
                    stack.append((item, child))
                elif isinstance(item, dict):
                    item_id = id(item)
                    if item_id in seen:
                        target.append(None)
                        continue
                    child = {}
                    target.append(child)
                    seen.add(item_id)
                    stack.append((item, child))
                else:
                    target.append(_normalize_scalar(item))
            continue

        for key, value in source.items():
            if isinstance(value, list):
                value_id = id(value)
                if value_id in seen:
                    target[key] = None
                    continue
                child = []
                target[key] = child
                seen.add(value_id)
                stack.append((value, child))
            elif isinstance(value, dict):
                value_id = id(value)
                if value_id in seen:
                    target[key] = None
                    continue
                child = {}
                target[key] = child
                seen.add(value_id)
                stack.append((value, child))
            else:
                target[key] = _normalize_scalar(value)
    return root

from mes_dashboard.services.resource_service import (
    query_resource_by_status,
    query_resource_by_workcenter,
    query_resource_detail,
    query_resource_workcenter_status_matrix,
    query_resource_filter_options,
    get_merged_resource_status,
    get_resource_status_summary,
    get_workcenter_status_matrix,
)
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.services.resource_cache import (
    get_resource_families,
    get_resource_cascade_metadata,
)
from mes_dashboard.config.constants import STATUS_CATEGORIES

# Create Blueprint
resource_bp = Blueprint('resource', __name__, url_prefix='/api/resource')
logger = logging.getLogger('mes_dashboard.resource_routes')

_RESOURCE_DETAIL_RATE_LIMIT = configured_rate_limit(
    bucket="resource-detail",
    max_attempts_env="RESOURCE_DETAIL_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="RESOURCE_DETAIL_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)

_RESOURCE_STATUS_RATE_LIMIT = configured_rate_limit(
    bucket="resource-status",
    max_attempts_env="RESOURCE_STATUS_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="RESOURCE_STATUS_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=90,
    default_window_seconds=60,
)


def _optional_bool_arg(name: str):
    raw = request.args.get(name)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return parse_bool_query(text)


@resource_bp.route('/by_status')
def api_resource_by_status():
    """API: Resource count by status."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_status", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_status(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/by_workcenter')
def api_resource_by_workcenter():
    """API: Resource count by workcenter."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_workcenter", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_workcenter(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/workcenter_status_matrix')
def api_resource_workcenter_status_matrix():
    """API: Resource count matrix by workcenter and status category."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_workcenter_matrix", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_workcenter_status_matrix(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/detail', methods=['POST'])
@_RESOURCE_DETAIL_RATE_LIMIT
def api_resource_detail():
    """API: Resource detail with filters."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = data.get('limit', 500)
    offset = data.get('offset', 0)
    days_back = get_days_back(filters)

    df = query_resource_detail(filters, limit, offset, days_back)
    if df is not None:
        records = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': records, 'count': len(records), 'offset': offset})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/filter_options')
def api_resource_filter_options():
    """API: Get filter options."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_filter_options", days_back)
    options = cache_get(cache_key)
    if options is None:
        options = query_resource_filter_options(days_back)
        if options:
            cache_set(cache_key, options)
    if options:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@resource_bp.route('/status_values')
def api_resource_status_values():
    """API: Get all distinct status values with counts (for verification)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': '數據庫連接失敗'}), 500

    try:
        sql = """
            SELECT DISTINCT NEWSTATUSNAME, COUNT(*) as CNT
            FROM DWH.DW_MES_RESOURCESTATUS
            WHERE NEWSTATUSNAME IS NOT NULL
              AND LASTSTATUSCHANGEDATE >= SYSDATE - 30
            GROUP BY NEWSTATUSNAME
            ORDER BY CNT DESC
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        data = [{'status': row[0], 'count': row[1]} for row in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        if connection:
            connection.close()
        logger.exception("Failed to load resource status values: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )


# ============================================================
# Realtime Equipment Status APIs (New)
# ============================================================

@resource_bp.route('/status')
@_RESOURCE_STATUS_RATE_LIMIT
def api_resource_status():
    """API: Get merged resource status from realtime cache.

    Query params:
        workcenter_groups: Comma-separated group names (e.g., '焊接,成型')
        is_production: '1' or 'true' to filter production equipment
        is_key: '1' or 'true' to filter key equipment
        is_monitor: '1' or 'true' to filter monitor equipment
        status_categories: Comma-separated categories (e.g., 'PRODUCTIVE,DOWN')
    """
    # Parse filters
    wc_groups_param = request.args.get('workcenter_groups')
    workcenter_groups = wc_groups_param.split(',') if wc_groups_param else None

    is_production = _optional_bool_arg('is_production')
    is_key = _optional_bool_arg('is_key')
    is_monitor = _optional_bool_arg('is_monitor')

    status_cats_param = request.args.get('status_categories')
    status_categories = status_cats_param.split(',') if status_cats_param else None

    families_param = request.args.get('families')
    families = families_param.split(',') if families_param else None
    resource_ids_param = request.args.get('resource_ids')
    resource_ids = resource_ids_param.split(',') if resource_ids_param else None

    try:
        data = get_merged_resource_status(
            workcenter_groups=workcenter_groups,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
            status_categories=status_categories,
            families=families,
            resource_ids=resource_ids,
        )
        # Clean NaN/NaT values for valid JSON
        cleaned_data = _clean_nan_values(data)
        return jsonify({
            'success': True,
            'data': cleaned_data,
            'count': len(cleaned_data),
        })
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.exception("Failed to load realtime resource status: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )


@resource_bp.route('/status/options')
def api_resource_status_options():
    """API: Get filter options for realtime status queries.

    Returns workcenter_groups, status_categories, families, and resources
    metadata for client-side cascade filtering.
    """
    try:
        cache_key = make_cache_key("resource_status_options")
        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify({'success': True, 'data': cached})

        wc_groups = get_workcenter_groups() or []

        data = {
            'workcenter_groups': [g['name'] for g in wc_groups],
            'status_categories': STATUS_CATEGORIES,
            'families': get_resource_families(),
            'resources': get_resource_cascade_metadata(),
        }
        cache_set(cache_key, data, ttl=300)

        return jsonify({'success': True, 'data': data})
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.exception("Failed to load realtime resource options: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )


@resource_bp.route('/status/summary')
@_RESOURCE_STATUS_RATE_LIMIT
def api_resource_status_summary():
    """API: Get resource status summary statistics.

    Query params: same as /status
    """
    # Parse filters (same as /status)
    wc_groups_param = request.args.get('workcenter_groups')
    workcenter_groups = wc_groups_param.split(',') if wc_groups_param else None

    is_production = _optional_bool_arg('is_production')
    is_key = _optional_bool_arg('is_key')
    is_monitor = _optional_bool_arg('is_monitor')

    families_param = request.args.get('families')
    families = families_param.split(',') if families_param else None
    resource_ids_param = request.args.get('resource_ids')
    resource_ids = resource_ids_param.split(',') if resource_ids_param else None

    try:
        data = get_resource_status_summary(
            workcenter_groups=workcenter_groups,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
            families=families,
            resource_ids=resource_ids,
        )
        # Clean NaN/NaT values for valid JSON
        cleaned_data = _clean_nan_values(data)
        return jsonify({'success': True, 'data': cleaned_data})
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.exception("Failed to load realtime resource summary: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )


@resource_bp.route('/status/matrix')
@_RESOURCE_STATUS_RATE_LIMIT
def api_resource_status_matrix():
    """API: Get workcenter × status matrix.

    Query params:
        is_production: Filter by production equipment
        is_key: Filter by key equipment
        is_monitor: Filter by monitor equipment
    """
    is_production = _optional_bool_arg('is_production')
    is_key = _optional_bool_arg('is_key')
    is_monitor = _optional_bool_arg('is_monitor')

    families_param = request.args.get('families')
    families = families_param.split(',') if families_param else None
    resource_ids_param = request.args.get('resource_ids')
    resource_ids = resource_ids_param.split(',') if resource_ids_param else None

    try:
        data = get_workcenter_status_matrix(
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
            families=families,
            resource_ids=resource_ids,
        )
        # Clean NaN/NaT values for valid JSON
        cleaned_data = _clean_nan_values(data)
        return jsonify({'success': True, 'data': cleaned_data})
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.exception("Failed to load realtime resource matrix: %s", exc)
        return error_response(
            INTERNAL_ERROR,
            "服務暫時無法使用",
            status_code=500,
        )
