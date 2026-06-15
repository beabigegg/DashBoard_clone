# -*- coding: utf-8 -*-
"""Resource History Analysis API routes.

Contains Flask Blueprint for historical equipment performance analysis endpoints.
Two-phase flow: POST /query (Oracle → cache) + GET /view (cache → derived views).
"""

import os
from datetime import datetime

from flask import Blueprint, request, redirect, Response

from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.config.constants import CACHE_TTL_FILTER_OPTIONS
from mes_dashboard.core.permissions import login_required, get_owner_token
from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    not_found_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.async_query_job_service import (
    enqueue_job_dynamic,
    is_async_available,
)
from mes_dashboard.services.batch_query_engine import get_batch_progress
from mes_dashboard.services.resource_history_service import (
    get_filter_options,
    export_csv,
)
from mes_dashboard.services.resource_dataset_cache import (
    execute_primary_query,
    apply_view,
)
import mes_dashboard.services.resource_query_job_service  # noqa: F401 — forces register_job_type() side-effect

# ── Local-compute feature flags (Task 1.3) ────────────────────────────────────

_RESOURCE_LOCAL_COMPUTE_ENABLED = os.environ.get(
    "RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED", "true"
).strip().lower() in ("1", "true", "yes")

_RESOURCE_SPOOL_THRESHOLD = int(os.environ.get("RESOURCE_SPOOL_THRESHOLD", "5000"))
_RESOURCE_SPOOL_NAMESPACE = "resource_dataset"

# ── Async RQ path — env-contract §Async Worker — Resource History Query ───────
# All four constants are frozen at import time (module-level).
# Tests must use monkeypatch.setattr(), never monkeypatch.setenv().
RESOURCE_ASYNC_ENABLED: bool = os.getenv(
    "RESOURCE_ASYNC_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")
RESOURCE_ASYNC_DAY_THRESHOLD: int = int(os.getenv("RESOURCE_ASYNC_DAY_THRESHOLD", "90"))
RESOURCE_WORKER_QUEUE: str = os.getenv("RESOURCE_WORKER_QUEUE", "resource-history-query")
RESOURCE_JOB_TIMEOUT_SECONDS: int = int(os.getenv("RESOURCE_JOB_TIMEOUT_SECONDS", "1800"))

# Create Blueprint
resource_history_bp = Blueprint(
    'resource_history',
    __name__,
    url_prefix='/api/resource/history'
)


# ── Spool metadata injection helpers (Tasks 1.1, 1.4) ────────────────────────


def _inject_resource_spool_info(data: dict, query_id: str) -> None:
    """Inject spool_download_url, total_row_count, and resource_metadata when eligible."""
    if not _RESOURCE_LOCAL_COMPUTE_ENABLED:
        return
    try:
        from mes_dashboard.core.query_spool_store import get_spool_metadata
        metadata = get_spool_metadata(_RESOURCE_SPOOL_NAMESPACE, query_id)
        if metadata is None:
            return
        row_count = int(metadata.get("row_count") or 0)
        data["total_row_count"] = row_count
        if row_count >= _RESOURCE_SPOOL_THRESHOLD:
            data["spool_download_url"] = (
                f"/api/spool/{_RESOURCE_SPOOL_NAMESPACE}/{query_id}.parquet"
            )
            _inject_resource_metadata(data)
    except Exception:
        pass  # Best-effort; must not break the view response


def _inject_resource_metadata(data: dict) -> None:
    """Attach resource dimension lookup for frontend local view derivation."""
    try:
        from mes_dashboard.services.resource_dataset_cache import (
            _get_resource_lookup,
            _get_workcenter_mapping,
        )
        resource_lookup = _get_resource_lookup()
        wc_mapping = _get_workcenter_mapping()
        resource_metadata = {}
        for historyid, info in resource_lookup.items():
            wc_name = info.get("WORKCENTERNAME", "")
            wc_info = wc_mapping.get(wc_name, {})
            resource_metadata[historyid] = {
                "workcenter": wc_info.get("group", wc_name) or wc_name,
                "workcenter_seq": int(wc_info.get("sequence", 999)),
                "family": info.get("RESOURCEFAMILYNAME", "") or "",
                "resource": info.get("RESOURCENAME", "") or "",
            }
        data["resource_metadata"] = resource_metadata
    except Exception:
        pass


# ============================================================
# Page Route (for template rendering)
# ============================================================

@resource_history_bp.route('/page', methods=['GET'], endpoint='page_alias')
def api_resource_history_page():
    """Backward-compatible alias for the migrated /resource-history page route."""
    return redirect('/resource-history')


# ============================================================
# API Endpoints
# ============================================================

@resource_history_bp.route('/options', methods=['GET'])
def api_resource_history_options():
    """API: Get filter options (workcenters and families).

    Returns:
        JSON with workcenters and families lists.
    """
    cache_key = make_cache_key("resource_history_options_v2")
    options = cache_get(cache_key)

    if options is None:
        options = get_filter_options()
        if options is not None:
            cache_set(cache_key, options, ttl=CACHE_TTL_FILTER_OPTIONS)

    if options is not None:
        return success_response(options)
    return internal_error()


# ============================================================
# Two-phase dataset cache endpoints
# ============================================================

def _validate_dates(start_date: str, end_date: str):
    """Validate and return parsed dates, or raise ValueError."""
    if not start_date or not end_date:
        raise ValueError("必須提供 start_date 和 end_date 參數")
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if ed < sd:
        raise ValueError("end_date 不可早於 start_date")
    return sd, ed


def _parse_resource_filters(data: dict) -> dict:
    """Extract resource filter params from dict (request body or query params)."""
    return {
        "workcenter_groups": data.get("workcenter_groups") or None,
        "families": data.get("families") or None,
        "resource_ids": data.get("resource_ids") or None,
        "is_production": _bool_param(data.get("is_production")),
        "is_key": _bool_param(data.get("is_key")),
        "is_monitor": _bool_param(data.get("is_monitor")),
        "package_groups": data.get("package_groups") or None,
    }


def _bool_param(val) -> bool:
    """Normalize bool-ish values from JSON body or query string."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val in ("1", "true", "True")
    return bool(val) if val is not None else False


@resource_history_bp.route('/query', methods=['POST'])
def api_resource_history_query():
    """API: Primary query — Oracle → cache → return query_id + initial view.

    JSON Body:
        start_date: str (YYYY-MM-DD)
        end_date: str (YYYY-MM-DD)
        granularity: str (day|week|month|year, default: day)
        workcenter_groups: list[str] (optional)
        families: list[str] (optional)
        resource_ids: list[str] (optional)
        is_production: bool (optional)
        is_key: bool (optional)
        is_monitor: bool (optional)

    Returns:
        JSON { success, query_id, summary, detail }
    """
    body = request.get_json(silent=True) or {}
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    granularity = body.get("granularity", "day")

    try:
        _validate_dates(start_date, end_date)
    except ValueError as exc:
        return validation_error(str(exc))

    filters = _parse_resource_filters(body)

    try:
        # ── Canonical spool check — BEFORE async dispatch ─────────────────────
        # Serves any request (short or long date range) from the pre-warmed or
        # previously-built canonical spool via DuckDB filter, with zero Oracle
        # cost.  The RQ worker primes the canonical spool after its first Oracle
        # fetch, so subsequent filter changes on the same date range are fast.
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_query_from_canonical_spool,
        )
        canonical_result, _canonical_meta = try_compute_query_from_canonical_spool(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            workcenter_groups=filters.get("workcenter_groups"),
            families=filters.get("families"),
            resource_ids=filters.get("resource_ids"),
            is_production=filters.get("is_production", False),
            is_key=filters.get("is_key", False),
            is_monitor=filters.get("is_monitor", False),
            package_groups=filters.get("package_groups"),
        )
        if canonical_result is not None:
            _inject_resource_spool_info(canonical_result, canonical_result.get("query_id", ""))
            return success_response(canonical_result)
    except Exception:
        pass  # Canonical miss or runtime error — fall through to async/sync path

    # ── Async RQ branch (RESOURCE_ASYNC_ENABLED + threshold + worker available) ──
    # Falls through to the sync 200 path on any false condition (AC-2, AC-6).
    if RESOURCE_ASYNC_ENABLED:
        from datetime import datetime as _dt
        try:
            sd = _dt.strptime(start_date, "%Y-%m-%d")
            ed = _dt.strptime(end_date, "%Y-%m-%d")
            day_span = (ed - sd).days
        except (ValueError, TypeError):
            day_span = 0
        if day_span >= RESOURCE_ASYNC_DAY_THRESHOLD:
            if is_async_available():
                _owner = get_owner_token()
                # owner MUST be inside _params (AC-7: enqueue_job forwards only kwargs
                # to the worker fn; worker signature requires owner=)
                _params = dict(
                    owner=_owner,
                    start_date=start_date,
                    end_date=end_date,
                    granularity=granularity,
                    **filters,
                )
                try:
                    job_id, err = enqueue_job_dynamic(
                        "resource-history",
                        owner=_owner,
                        params=_params,
                    )
                    if job_id is not None:
                        return success_response(
                            {
                                "async": True,
                                "job_id": job_id,
                                "status_url": f"/api/job/{job_id}?prefix=resource-history",
                            },
                            status_code=202,
                        )
                    # enqueue returned None — fall through to sync path
                except Exception:
                    pass  # Degradable async failure — fall through silently (AC-6)

    try:
        result = execute_primary_query(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            **filters,
        )
        _inject_resource_spool_info(result, result.get("query_id", ""))
        return success_response(result)
    except Exception as exc:
        return internal_error(str(exc))


@resource_history_bp.route('/view', methods=['GET'])
def api_resource_history_view():
    """API: Supplementary view — read cache, derive views. No Oracle query.

    Query Parameters:
        query_id: str (required)
        granularity: str (day|week|month|year, default: day)

    Returns:
        JSON { success, summary, detail } or 410 on cache miss.
    """
    query_id = request.args.get("query_id", "")
    granularity = request.args.get("granularity", "day")

    if not query_id:
        return validation_error("必須提供 query_id")

    result = apply_view(query_id=query_id, granularity=granularity)
    if result is None:
        return cache_expired_error()

    _inject_resource_spool_info(result, query_id)
    return success_response(result)


# ============================================================
# Batch query progress endpoint (resource-history-perf)
# ============================================================

@resource_history_bp.route('/query/progress', methods=['GET'])
@login_required
def api_resource_history_query_progress():
    """API: Batch query progress — return progress metadata for an in-flight or completed batch.

    Query Parameters:
        query_id: str (required) — hash returned by POST /query

    Returns:
        JSON { query_id, total_chunks, completed_chunks, percent, status }
        Status enum: running | done | error
        400 if query_id is missing; 404 if not found in Redis.
    """
    query_id = request.args.get("query_id", "").strip()
    if not query_id:
        return validation_error("必須提供 query_id")

    raw = get_batch_progress("resource_history", query_id)
    if raw is None:
        return not_found_error("找不到指定的查詢進度，可能已過期或尚未建立")

    # Decode bytes keys/values produced by Redis hgetall
    def _decode(v) -> str:
        return v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else str(v)

    total_chunks = int(_decode(raw.get(b"total", raw.get("total", 0))))
    completed_chunks = int(_decode(raw.get(b"completed", raw.get("completed", 0))))
    percent = float(_decode(raw.get(b"pct", raw.get("pct", 0))))
    raw_status = _decode(raw.get(b"status", raw.get("status", "running")))

    # Map batch_query_engine status enum → API status enum (AC-5)
    # batch statuses: running | completed | partial | failed
    # API statuses:   running | done      | done    | error
    if raw_status in ("completed", "partial"):
        status = "done"
    elif raw_status == "failed":
        status = "error"
    else:
        status = "running"

    return success_response({
        "query_id": query_id,
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "percent": percent,
        "status": status,
    })


# ============================================================
# Export (kept — uses existing service directly)
# ============================================================

@resource_history_bp.route('/export', methods=['GET', 'POST'])
def api_resource_history_export():
    """API: Export detail data as CSV.

    Query Parameters:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        granularity: day|week|month|year (default: day)
        workcenter_groups: Optional workcenter group filter (multi-select)
        families: Optional resource family filter (multi-select)
        is_production: 1 to filter production equipment
        is_key: 1 to filter key equipment
        is_monitor: 1 to filter monitored equipment

    Returns:
        CSV file download.
    """
    # Parse parameters from JSON body (POST) or query string (GET)
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        granularity = data.get('granularity', 'day')
        workcenter_groups = data.get('workcenter_groups') or None
        families = data.get('families') or None
        resource_ids = data.get('resource_ids') or None
        is_production = bool(data.get('is_production'))
        is_key = bool(data.get('is_key'))
        is_monitor = bool(data.get('is_monitor'))
    else:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        granularity = request.args.get('granularity', 'day')
        workcenter_groups = request.args.getlist('workcenter_groups') or None
        families = request.args.getlist('families') or None
        resource_ids = request.args.getlist('resource_ids') or None
        is_production = request.args.get('is_production') == '1'
        is_key = request.args.get('is_key') == '1'
        is_monitor = request.args.get('is_monitor') == '1'

    # Validate required parameters
    if not start_date or not end_date:
        return validation_error('必須提供 start_date 和 end_date 參數')

    # Validate export date range (max 365 days)
    try:
        sd = datetime.strptime(start_date, '%Y-%m-%d')
        ed = datetime.strptime(end_date, '%Y-%m-%d')
        if (ed - sd).days > 365:
            return validation_error('CSV 匯出範圍不可超過一年 (365 天)')
    except ValueError:
        return validation_error('日期格式錯誤，請使用 YYYY-MM-DD')

    # Generate filename
    filename = f"resource_history_{start_date}_to_{end_date}.csv"

    # Stream CSV response
    return Response(
        export_csv(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        ),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
