# -*- coding: utf-8 -*-
"""Downtime Analysis API routes.

Blueprint for historical downtime analysis endpoints.
Type-A spool pattern: POST /query (Oracle → spool) + GET /view (spool → views).

Endpoints per api-contract.md §10:
  GET  /api/downtime-analysis/options
  POST /api/downtime-analysis/query
  GET  /api/downtime-analysis/view
  GET  /api/downtime-analysis/equipment-detail
  GET  /api/downtime-analysis/event-detail
  GET  /api/downtime-analysis/export-equipment-detail
  GET  /api/downtime-analysis/export-event-detail
"""

from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, Response, request
from flask import stream_with_context

from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    success_response,
    validation_error,
)

from mes_dashboard.services.downtime_analysis_service import (
    apply_view,
    export_equipment_detail_csv,
    export_event_detail_csv,
    get_filter_options,
    query_downtime_dataset,
    query_downtime_dataset_raw,
)
from mes_dashboard.services.async_query_job_service import (
    enqueue_job_dynamic,
    is_async_available,
)
from mes_dashboard.core.query_cost_policy import classify_query_cost as _classify_query_cost
from mes_dashboard.core.permissions import get_owner_token

downtime_analysis_bp = Blueprint(
    'downtime_analysis',
    __name__,
    url_prefix='/api/downtime-analysis',
)

# ── Maximum allowed date range (SYS-04) ──────────────────────────────────────
_MAX_DAYS = 730
# _MAX_ORACLE_DAYS (90) and _DUCKDB_WINDOW_DAYS (93) are intentionally removed.
# The OOM risk for wide Oracle-path queries is eliminated by the browser-DuckDB
# path: the server writes raw parquets and all pandas reductions run in the browser.
# Only the SYS-04 730-day hard cap remains (DA-09, AC-6).

# ── Feature flag: browser-DuckDB response path (env-contract 1.0.7) ──────────
# Default false at initial ship; operators cut over by setting
# DOWNTIME_BROWSER_DUCKDB=true and reloading gunicorn.  This constant is frozen
# at import time — tests must use monkeypatch.setattr, never os.environ.
_BROWSER_DUCKDB_ENABLED: bool = os.getenv(
    "DOWNTIME_BROWSER_DUCKDB", "false"
).lower() in ("1", "true", "yes")

# ── Async RQ path — env-contract §Async Worker — Downtime Query ───────────────
# All four constants are frozen at import time (module-level).
# Tests must use monkeypatch.setattr(), never monkeypatch.setenv().
_ASYNC_ENABLED: bool = os.getenv(
    "DOWNTIME_ASYNC_ENABLED", "true"
).lower() in ("1", "true", "yes", "on")
_ASYNC_WORKER_QUEUE: str = os.getenv("DOWNTIME_WORKER_QUEUE", "downtime-query")
_JOB_TIMEOUT: int = int(os.getenv("DOWNTIME_JOB_TIMEOUT_SECONDS", "1800"))

# ── Unified DuckDB job flag (downtime-duckdb-join-migration, P5) ──────────────
# DOWNTIME_USE_UNIFIED_JOB=on → enqueue DowntimeJob (BaseChunkedDuckDBJob) via
# the 'downtime-unified' job type (DuckDB bridge JOIN, OOM elimination).
# DOWNTIME_USE_UNIFIED_JOB=off (default) → legacy query_downtime_dataset path.
# Frozen at import time; tests must use monkeypatch.setattr().
# Legacy _bridge_jobid Path B is NOT deleted while this flag exists (AC-8).
from mes_dashboard.core.feature_flags import resolve_bool_flag as _resolve_bool_flag  # noqa: E402
_DOWNTIME_USE_UNIFIED_JOB: bool = _resolve_bool_flag(
    "DOWNTIME_USE_UNIFIED_JOB", default=False
)


# ============================================================
# Validation helpers
# ============================================================


def _validate_dates(start_date: str, end_date: str) -> None:
    """Raise ValueError on invalid/missing dates or range > _MAX_DAYS (SYS-04).

    Only the 730-day hard cap is enforced (DA-09, AC-6).  The prior 90-day
    Oracle-path guard (_MAX_ORACLE_DAYS) is intentionally removed — the OOM
    risk is eliminated by the browser-DuckDB path (design.md D3, DA-10).
    """
    if not start_date or not end_date:
        raise ValueError("必須提供 start_date 和 end_date 參數")
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if ed < sd:
        raise ValueError("end_date 不可早於 start_date")
    days = (ed - sd).days
    if days > _MAX_DAYS:
        raise ValueError(f"查詢範圍不可超過 {_MAX_DAYS} 天")


def _csv_param(val: str | None) -> list[str] | None:
    """Parse comma-separated query param into list, or None when empty."""
    if not val:
        return None
    parts = [v.strip() for v in val.split(',') if v.strip()]
    return parts if parts else None


# ============================================================
# GET /api/downtime-analysis/options
# ============================================================


@downtime_analysis_bp.route('/options', methods=['GET'])
def api_downtime_options():
    """API: Get filter options for downtime-analysis page.

    Query Parameters (optional, for cross-narrow):
        workcenter_groups: comma-separated
        families:          comma-separated
        resource_ids:      comma-separated
        package_groups:    comma-separated

    Returns:
        JSON with workcenter_groups, families, resources, package_groups,
              big_categories, reasons lists.
    """
    workcenter_groups = _csv_param(request.args.get('workcenter_groups', ''))
    families = _csv_param(request.args.get('families', ''))
    resource_ids = _csv_param(request.args.get('resource_ids', ''))
    package_groups = _csv_param(request.args.get('package_groups', ''))
    is_production = request.args.get('is_production', '').lower() in ('1', 'true')
    is_key = request.args.get('is_key', '').lower() in ('1', 'true')
    is_monitor = request.args.get('is_monitor', '').lower() in ('1', 'true')

    options = get_filter_options(
        workcenter_groups=workcenter_groups,
        families=families,
        resource_ids=resource_ids,
        package_groups=package_groups,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
    )
    if options is None:
        return internal_error("篩選條件選項載入失敗")
    return success_response(options)


# ============================================================
# POST /api/downtime-analysis/query
# ============================================================


@downtime_analysis_bp.route('/query', methods=['POST'])
def api_downtime_query():
    """API: Primary query — Oracle → spool → return query_id + summary views.

    JSON Body:
        start_date:       str (YYYY-MM-DD, required)
        end_date:         str (YYYY-MM-DD, required)
        workcenter_groups: list[str] (optional)
        families:          list[str] (optional)
        resource_ids:      list[str] (optional)
        package_groups:    list[str] (optional)
        big_categories:    list[str] (optional)
        status_types:      list[str] (optional, e.g. ['UDT','SDT'])

    Returns:
        JSON { success, data: { query_id, summary, daily_trend, big_category, top_reasons } }
    """
    body = request.get_json(silent=True) or {}
    start_date = body.get('start_date', '')
    end_date = body.get('end_date', '')

    try:
        _validate_dates(start_date, end_date)
    except ValueError as exc:
        return validation_error(str(exc))

    workcenter_groups = body.get('workcenter_groups') or None
    families = body.get('families') or None
    resource_ids = body.get('resource_ids') or None
    package_groups = body.get('package_groups') or None
    big_categories = body.get('big_categories') or None
    status_types = body.get('status_types') or None
    is_production = bool(body.get('is_production', False))
    is_key = bool(body.get('is_key', False))
    is_monitor = bool(body.get('is_monitor', False))

    # ── Spool cache check (browser-DuckDB path only) ──────────────────────────
    # When both raw parquets already exist for this date range + resource filter
    # combination, serve them directly without Oracle or a new RQ job.  Changing
    # non-key filter params (big_categories, status_types, is_production, etc.)
    # hits this path because the spool key only covers the data-acquisition dims.
    if _BROWSER_DUCKDB_ENABLED:
        from mes_dashboard.services.downtime_analysis_service import (
            make_raw_spool_query_id,
        )
        from mes_dashboard.services.downtime_analysis_cache import (
            has_downtime_base_events,
            has_downtime_job_bridge,
            _BASE_EVENTS_NAMESPACE,
            _JOB_BRIDGE_NAMESPACE,
        )
        from mes_dashboard.services.downtime_analysis_service import (
            _build_taxonomy_json,
            _build_resource_lookup,
        )
        _spool_key_params = {
            'start_date': start_date,
            'end_date': end_date,
            'workcenter_groups': sorted(workcenter_groups or []),
            'families': sorted(families or []),
            'resource_ids': sorted(resource_ids or []),
            'package_groups': sorted(package_groups or []),
        }
        _spool_qid = make_raw_spool_query_id(_spool_key_params)
        if has_downtime_base_events(_spool_qid) and has_downtime_job_bridge(_spool_qid):
            return success_response({
                'base_spool_url': f'/api/spool/{_BASE_EVENTS_NAMESPACE}/{_spool_qid}.parquet',
                'jobs_spool_url': f'/api/spool/{_JOB_BRIDGE_NAMESPACE}/{_spool_qid}.parquet',
                'query_id': _spool_qid,
                'taxonomy': _build_taxonomy_json(),
                'resource_lookup': _build_resource_lookup(),
            })

    # ── Async RQ branch (DOWNTIME_ASYNC_ENABLED + threshold + worker available) ──
    # Only enter when: browser-DuckDB flag is ON (raw-spool path), AND the async
    # flag is enabled, AND the date span meets the threshold, AND a worker is live.
    # Falls through to the sync path on any false condition (ASYNC-02/ASYNC-DA-01).
    if _BROWSER_DUCKDB_ENABLED and _ASYNC_ENABLED:
        _downtime_cost = _classify_query_cost(
            domain="downtime",
            params={"date_from": start_date, "date_to": end_date},
        )
        if _downtime_cost == "ASYNC":
            if is_async_available():
                query_params = dict(
                    start_date=start_date,
                    end_date=end_date,
                    workcenter_groups=workcenter_groups,
                    families=families,
                    resource_ids=resource_ids,
                    package_groups=package_groups,
                    big_categories=big_categories,
                    status_types=status_types,
                    is_production=is_production,
                    is_key=is_key,
                    is_monitor=is_monitor,
                    owner=get_owner_token(),
                )
                job_id, err = enqueue_job_dynamic(
                    "downtime",
                    owner=get_owner_token(),
                    params=query_params,
                )
                if job_id is not None:
                    return success_response(
                        {
                            "async": True,
                            "job_id": job_id,
                            "status_url": f"/api/job/{job_id}?prefix=downtime",
                        },
                        status_code=202,
                    )
                # enqueue failed — fall through to sync path

    try:
        if _BROWSER_DUCKDB_ENABLED:
            # Browser-DuckDB path (AC-1, DA-12): write two raw spool parquets;
            # return URLs + taxonomy; no server-side reductions.
            result = query_downtime_dataset_raw(
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=workcenter_groups,
                families=families,
                resource_ids=resource_ids,
                package_groups=package_groups,
                big_categories=big_categories,
                status_types=status_types,
                is_production=is_production,
                is_key=is_key,
                is_monitor=is_monitor,
            )
        elif _DOWNTIME_USE_UNIFIED_JOB:
            # Unified DuckDB job path (DOWNTIME_USE_UNIFIED_JOB=on):
            # Enqueue DowntimeJob (BaseChunkedDuckDBJob) via 'downtime-unified'.
            # This path requires is_async_available() because DowntimeJob always_async=True.
            if not is_async_available():
                return internal_error(
                    "DOWNTIME_USE_UNIFIED_JOB=on requires RQ worker; "
                    "no worker available (503)."
                )
            query_params = dict(
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=workcenter_groups,
                families=families,
                resource_ids=resource_ids,
                package_groups=package_groups,
                big_categories=big_categories,
                status_types=status_types,
                is_production=is_production,
                is_key=is_key,
                is_monitor=is_monitor,
            )
            job_id, err = enqueue_job_dynamic(
                "downtime-unified",
                owner=get_owner_token(),
                params=query_params,
            )
            if job_id is None:
                return internal_error(err or "Failed to enqueue downtime-unified job")
            return success_response(
                {
                    "async": True,
                    "job_id": job_id,
                    "status_url": f"/api/job/{job_id}?prefix=downtime",
                },
                status_code=202,
            )
        else:
            # Legacy enriched-spool path (flag OFF / rollback target, AC-8):
            # returns {query_id, summary, daily_trend, big_category, top_reasons}.
            result = query_downtime_dataset(
                start_date=start_date,
                end_date=end_date,
                workcenter_groups=workcenter_groups,
                families=families,
                resource_ids=resource_ids,
                package_groups=package_groups,
                big_categories=big_categories,
                status_types=status_types,
                is_production=is_production,
                is_key=is_key,
                is_monitor=is_monitor,
            )
        return success_response(result)
    except Exception as exc:
        return internal_error(str(exc))


# ============================================================
# GET /api/downtime-analysis/view
# ============================================================


@downtime_analysis_bp.route('/view', methods=['GET'])
def api_downtime_view():
    """API: Re-group spool for summary/trend/big-category/top-reasons view.

    Query Parameters:
        query_id:     str (required)
        granularity:  str (day|week|month, default: day)
        top_n:        int (default: 10)
        status_types: str (optional; CSV e.g. 'UDT,SDT'; filter big_category and top_reasons)

    Returns:
        JSON { success, data: { summary, daily_trend, big_category, top_reasons } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    granularity = request.args.get('granularity', 'day').strip()
    top_n = request.args.get('top_n', 10, type=int)
    status_types = _csv_param(request.args.get('status_types', ''))

    if not query_id:
        return validation_error("必須提供 query_id")

    if granularity != 'day':
        return validation_error('granularity must be "day" (week/month not yet implemented)')

    result = apply_view(
        view_name='summary',
        query_id=query_id,
        granularity=granularity,
        top_n=top_n,
        status_types=status_types,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# GET /api/downtime-analysis/equipment-detail
# ============================================================


@downtime_analysis_bp.route('/equipment-detail', methods=['GET'])
def api_downtime_equipment_detail():
    """API: Paginated per-equipment summary from spool.

    Query Parameters:
        query_id:     str (required)
        page:         int (default: 1)
        page_size:    int (default: 20, max: 1000; raised from 200 for three-tier full-load — DQ-2)
        big_category: str (optional; filter to machines with events in this category)
        status_types: str (optional; CSV e.g. 'UDT,SDT'; filter by status type)
        resource_id:  str (optional; filter to single machine for Tier 3 lazy-load)

    Returns:
        JSON { success, data: { equipment_detail: EquipmentDetailRow[], pagination: {...} } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if not query_id:
        return validation_error("必須提供 query_id")

    page_size = min(max(page_size, 1), 1000)  # cap raised to 1000 (DQ-2)
    page = max(page, 1)

    big_category = request.args.get('big_category', '').strip() or None
    status_types = _csv_param(request.args.get('status_types', ''))
    resource_id = request.args.get('resource_id', '').strip() or None

    # Build resource lookup for display names
    resource_lookup = _get_resource_lookup_safe()

    result = apply_view(
        view_name='equipment_detail',
        query_id=query_id,
        page=page,
        page_size=page_size,
        resource_lookup=resource_lookup,
        big_category=big_category,
        status_types=status_types,
        resource_id=resource_id,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# GET /api/downtime-analysis/event-detail
# ============================================================


@downtime_analysis_bp.route('/event-detail', methods=['GET'])
def api_downtime_event_detail():
    """API: Paginated per-event detail from spool.

    Query Parameters:
        query_id:  str (required)
        page:      int (default: 1)
        page_size: int (default: 20, max: 200)

    Returns:
        JSON { success, data: { events: EventDetailRow[], pagination: {...} } }
        or 410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    if not query_id:
        return validation_error("必須提供 query_id")

    page_size = min(max(page_size, 1), 200)
    page = max(page, 1)

    big_category = request.args.get('big_category', '').strip() or None
    status_types = _csv_param(request.args.get('status_types', ''))
    resource_id = request.args.get('resource_id', '').strip() or None

    resource_lookup = _get_resource_lookup_safe()

    result = apply_view(
        view_name='event_detail',
        query_id=query_id,
        page=page,
        page_size=page_size,
        resource_lookup=resource_lookup,
        big_category=big_category,
        status_types=status_types,
        resource_id=resource_id,
    )
    if result is None:
        return cache_expired_error()
    return success_response(result)


# ============================================================
# GET /api/downtime-analysis/export-equipment-detail
# ============================================================


@downtime_analysis_bp.route('/export-equipment-detail', methods=['GET'])
def api_export_equipment_detail():
    """GET /export-equipment-detail — stream equipment detail as CSV.

    Query Parameters:
        query_id: str (required)

    Returns:
        CSV file download (utf-8-sig, Excel-compatible).
        410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    if not query_id:
        return validation_error("必須提供 query_id")

    gen = export_equipment_detail_csv(query_id)
    if gen is None:
        return cache_expired_error()

    return Response(
        stream_with_context(gen),
        content_type='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename=downtime_equipment_detail.csv',
            'X-Accel-Buffering': 'no',
        },
    )


# ============================================================
# GET /api/downtime-analysis/export-event-detail
# ============================================================


@downtime_analysis_bp.route('/export-event-detail', methods=['GET'])
def api_export_event_detail():
    """GET /export-event-detail — stream event detail as CSV.

    Query Parameters:
        query_id: str (required)

    Returns:
        CSV file download (utf-8-sig, Excel-compatible).
        410 on spool miss.
    """
    query_id = request.args.get('query_id', '').strip()
    if not query_id:
        return validation_error("必須提供 query_id")

    gen = export_event_detail_csv(query_id)
    if gen is None:
        return cache_expired_error()

    return Response(
        stream_with_context(gen),
        content_type='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename=downtime_event_detail.csv',
            'X-Accel-Buffering': 'no',
        },
    )


# ============================================================
# Resource lookup helper
# ============================================================


def _get_resource_lookup_safe() -> dict:
    """Return resource lookup dict {historyid: info}; empty dict on error."""
    try:
        from mes_dashboard.services.resource_cache import get_all_resources
        resources = get_all_resources() or []
        return {
            str(r.get('RESOURCEID', '')).strip(): r
            for r in resources
            if r.get('RESOURCEID')
        }
    except Exception:
        return {}
