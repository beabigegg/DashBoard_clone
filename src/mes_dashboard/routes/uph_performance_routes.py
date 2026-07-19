# -*- coding: utf-8 -*-
"""UPH Performance route Blueprint.

7 endpoints (api-contract.md lines 266-272):
  POST /api/uph-performance/spool               -- Type B async; 202 or spool-hit 200
  GET  /api/uph-performance/spool/status         -- poll job status
  GET  /api/uph-performance/filter-options       -- DuckDB-only fine filter options
  GET  /api/uph-performance/product-filter-options -- container_filter_cache (Oracle-free)
  GET  /api/uph-performance/trend                -- DuckDB-only hourly avg-UPH trend
  GET  /api/uph-performance/ranking              -- DuckDB-only per-equipment ranking
  GET  /api/uph-performance/detail               -- DuckDB-only paginated detail

All endpoints require auth (enforced by app.py before_request, mirrors eap_alarm_routes.py).
Fine-filter endpoints return 410 on spool miss (data-shape §3.29).
always_async=True, sync_fallback_allowed=False -- no sync fallback exists (UPH-ASYNC).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from flask import Blueprint, request

from mes_dashboard.core.response import (
    cache_expired_error,
    error_response,
    internal_error,
    success_response,
    validation_error,
    SERVICE_UNAVAILABLE,
)

uph_performance_bp = Blueprint("uph_performance", __name__, url_prefix="/api/uph-performance")
logger = logging.getLogger("mes_dashboard.uph_performance_routes")

_UPH_PERFORMANCE_RETRY_AFTER_SECONDS = int(
    os.getenv("UPH_PERFORMANCE_RETRY_AFTER_SECONDS", "30")
)
_JOB_PREFIX = "uph-performance"
_NAMESPACE = "uph_performance"

# Frozen at import time -- tests must use monkeypatch.setattr(), never setenv().
# No legacy code path exists behind "off" (clean pre-launch replacement, mirrors
# PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB): "off" is a pure kill switch -- the
# worker module is never lazy-imported, so its job type never registers, and a
# spool-miss on /spool falls straight through to the 503 branch below
# (env-contract.md UPH_PERFORMANCE_USE_UNIFIED_JOB). A spool-HIT request still
# succeeds even with the flag off.
_UPH_PERFORMANCE_USE_UNIFIED_JOB: bool = os.getenv(
    "UPH_PERFORMANCE_USE_UNIFIED_JOB", "on"
).strip().lower() in ("on", "true", "1")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    return [str(v).strip() for v in value if v is not None and str(v).strip()]


def _parse_list_param(name: str) -> List[str]:
    """Parse repeated query param (?name[]=x&name[]=y or ?name=x) from a GET request."""
    vals = request.args.getlist(f"{name}[]") or request.args.getlist(name)
    return [str(v).strip() for v in vals if v is not None and str(v).strip()]


def _parse_fine_filters() -> Dict[str, Any]:
    """Parse the shared fine-filter axes (data-shape §3.29): equipment_id,
    workcenter_name, package, pj_type."""
    return {
        "equipment_id": _parse_list_param("equipment_id") or None,
        "workcenter_name": _parse_list_param("workcenter_name") or None,
        "package": _parse_list_param("package") or None,
        "pj_type": _parse_list_param("pj_type") or None,
    }


def _get_spool_path(query_id: str) -> Optional[str]:
    """Resolve spool parquet path by query_id; returns None on miss/expiry."""
    try:
        from mes_dashboard.core.query_spool_store import get_spool_file_path
        path = get_spool_file_path(_NAMESPACE, query_id)
        if path is not None and not os.path.exists(path):
            logger.warning(
                "uph_performance_routes: parquet missing from disk (stale metadata) "
                "query_id=%s path=%s", query_id, path
            )
            return None
        return path
    except Exception as exc:
        logger.warning("uph_performance_routes: spool path lookup failed query_id=%s: %s", query_id, exc)
        return None


def _require_query_id() -> tuple[Optional[str], Optional[Any]]:
    query_id = (request.args.get("query_id") or "").strip()
    if not query_id:
        return None, validation_error("缺少必要參數: query_id")
    return query_id, None


def _require_spool(query_id: str) -> tuple[Optional[str], Optional[Any]]:
    spool_path = _get_spool_path(query_id)
    if spool_path is None:
        return None, cache_expired_error("UPH Performance spool 不存在或已過期，請重新提交查詢")
    return spool_path, None


# ── POST /api/uph-performance/spool ──────────────────────────────────────────

@uph_performance_bp.route("/spool", methods=["POST"])
def api_uph_performance_spool():
    """Trigger coarse spool query (always-async, no sync fallback -- UPH-ASYNC).

    On spool cache hit: returns 200 with existing query_id.
    On spool miss: enqueues RQ job, returns 202 with job_id + status_url + query_id.
    On worker unavailable (queue down, or flag off): returns 503, never a
    silent synchronous downgrade (ASYNC-06).
    """
    from mes_dashboard.core.request_validation import parse_json_payload

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(
            "VALIDATION_ERROR",
            payload_error.message,
            status_code=payload_error.status_code,
        )

    date_from = str(body.get("date_from") or "").strip()
    date_to = str(body.get("date_to") or "").strip()
    families = _clean_str_list(body.get("families"))
    models = _clean_str_list(body.get("models"))
    workcenter_names = _clean_str_list(body.get("workcenter_names"))
    packages = _clean_str_list(body.get("packages"))
    pj_types = _clean_str_list(body.get("pj_types"))
    equipment_ids = _clean_str_list(body.get("equipment_ids"))

    try:
        from mes_dashboard.services.uph_performance_service import validate_uph_performance_params
        validate_uph_performance_params(
            date_from, date_to, families=families, equipment_ids=equipment_ids,
        )
    except ValueError as exc:
        return validation_error(str(exc))

    try:
        from mes_dashboard.services.uph_performance_cache import make_uph_performance_spool_key
        spool_key = make_uph_performance_spool_key(
            date_from, date_to, families, workcenter_names, packages, pj_types, equipment_ids,
            models=models,
        )
    except ValueError as exc:
        return validation_error(str(exc))

    # Spool-hit: 200 regardless of flag state (UPH-ASYNC).
    spool_path = _get_spool_path(spool_key)
    if spool_path is not None:
        logger.info("uph_performance_routes: spool cache hit query_id=%s", spool_key)
        return success_response({"async": False, "query_id": spool_key})

    from mes_dashboard.services.async_query_job_service import enqueue_query_job, is_async_available

    # Queue unavailable (Redis down / no RQ workers) -> 503 regardless of the
    # flag state -- checked BEFORE the job-type lookup so a flag="off" cold
    # spool also degrades to 503 (no "Unknown job type" leak), mirroring
    # production_achievement_routes.py's api_get_report().
    if not is_async_available():
        return error_response(
            SERVICE_UNAVAILABLE,
            "背景查詢服務不可用，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": _UPH_PERFORMANCE_RETRY_AFTER_SECONDS},
            headers={"Retry-After": str(_UPH_PERFORMANCE_RETRY_AFTER_SECONDS)},
        )

    # Lazy import registers the job type (module-level register_job_type()
    # side-effect) -- gated by the kill switch, mirrors production_achievement_routes.py.
    if _UPH_PERFORMANCE_USE_UNIFIED_JOB:
        import mes_dashboard.workers.uph_performance_worker  # noqa: F401

    try:
        from mes_dashboard.core.permissions import get_owner_token

        job_id = f"uph-performance-{uuid.uuid4().hex[:12]}"
        job_id_result, err, status_hint = enqueue_query_job(
            "uph-performance",
            owner=get_owner_token(),
            params={
                "date_from": date_from,
                "date_to": date_to,
                "families": families,
                "models": models,
                "workcenter_names": workcenter_names,
                "packages": packages,
                "pj_types": pj_types,
                "equipment_ids": equipment_ids,
            },
            sync_fallback_allowed=False,
            job_id=job_id,
        )

        if job_id_result is None:
            logger.warning(
                "uph_performance_routes: async enqueue failed (hint=%s): %s", status_hint, err
            )
            return error_response(
                SERVICE_UNAVAILABLE,
                "背景查詢服務不可用，請稍後再試",
                status_code=status_hint or 503,
                meta={"retry_after_seconds": _UPH_PERFORMANCE_RETRY_AFTER_SECONDS},
                headers={"Retry-After": str(_UPH_PERFORMANCE_RETRY_AFTER_SECONDS)},
            )

        return success_response(
            {
                "async": True,
                "job_id": job_id_result,
                "status_url": f"/api/uph-performance/spool/status?job_id={job_id}",
                "query_id": spool_key,
            },
            status_code=202,
        )
    except Exception as exc:
        logger.error("uph_performance_routes: spool trigger failed: %s", exc, exc_info=True)
        return internal_error("UPH Performance 查詢觸發失敗")


# ── GET /api/uph-performance/spool/status ────────────────────────────────────

@uph_performance_bp.route("/spool/status", methods=["GET"])
def api_uph_performance_spool_status():
    """Poll async job status by job_id (proxy to /api/job/<job_id>?prefix=uph-performance)."""
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        query_id = (request.args.get("query_id") or "").strip()
        if query_id:
            spool_path = _get_spool_path(query_id)
            if spool_path is not None:
                return success_response({"status": "complete", "query_id": query_id})
            return cache_expired_error("UPH Performance spool 不存在")
        return validation_error("缺少必要參數: job_id 或 query_id")

    try:
        from mes_dashboard.services.async_query_job_service import get_job_status
        status = get_job_status(_JOB_PREFIX, job_id)
        if status is None:
            from mes_dashboard.core.response import not_found_error
            return not_found_error("Job not found")
        return success_response(status)
    except Exception as exc:
        logger.error("uph_performance_routes: status lookup failed job_id=%s: %s", job_id, exc)
        return internal_error("Job 狀態查詢失敗")


# ── GET /api/uph-performance/filter-options ──────────────────────────────────

@uph_performance_bp.route("/filter-options", methods=["GET"])
def api_uph_performance_filter_options():
    """Return distinct fine-filter options from the DuckDB spool."""
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.uph_performance_service import get_filter_options
        result = get_filter_options(spool_path, filters)
        return success_response(result)
    except Exception as exc:
        logger.error("uph_performance_routes: filter-options failed query_id=%s: %s", query_id, exc)
        return internal_error("Filter options 查詢失敗")


# ── GET /api/uph-performance/product-filter-options ──────────────────────────

@uph_performance_bp.route("/product-filter-options", methods=["GET"])
def api_uph_performance_product_filter_options():
    """Return Package/Type filter options (Oracle-free, container_filter_cache).

    Unlike eap-alarm's equivalent endpoint, a cache failure here returns a
    genuine HTTP 500 (api-contract.md errors column) -- the frontend shows an
    inline warning near the Package/Type dropdowns while other filters stay
    usable (interaction-design.md Confirmed #6).
    """
    try:
        from mes_dashboard.services.container_filter_cache import get_filter_options
        data = get_filter_options({})
    except Exception as exc:
        logger.error("uph_performance_routes: product-filter-options failed: %s", exc, exc_info=True)
        return internal_error("Product filter options 查詢失敗")

    return success_response({
        "pj_types": data.get("pj_types") or [],
        "product_lines": data.get("packages") or [],  # packages -> product_lines (PRODUCTLINENAME)
    })


# ── GET /api/uph-performance/machine-options ─────────────────────────────────

@uph_performance_bp.route("/machine-options", methods=["GET"])
def api_uph_performance_machine_options():
    """Return cascadable machine filter options (機型/工作站/機台) from the
    equipment master DW_MES_RESOURCE (Oracle, cached per-worker TTL).

    Feeds the pre-query filter-bar dropdowns (family/model/workcenter/equipment)
    -- replaces the old GDBA/GWBA-only 機型 select and the free-text 工作站 /
    機台 textareas. A cache/Oracle failure returns HTTP 500; the frontend shows
    an inline warning while the date range + Package/Type filters stay usable.
    """
    try:
        from mes_dashboard.services.uph_performance_machine_options import get_machine_options
        data = get_machine_options()
    except Exception as exc:
        logger.error("uph_performance_routes: machine-options failed: %s", exc, exc_info=True)
        return internal_error("機台選項查詢失敗")

    return success_response(data)


# ── GET /api/uph-performance/trend ───────────────────────────────────────────

@uph_performance_bp.route("/trend", methods=["GET"])
def api_uph_performance_trend():
    """Return hourly (native M[60]) avg-UPH trend from the DuckDB spool.

    ``group_by`` selects the stack dimension (default family); closed enum
    validated against service GROUP_DIMENSIONS -> 400 on unknown value.
    """
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    from mes_dashboard.services.uph_performance_service import GROUP_DIMENSIONS
    group_by = (request.args.get("group_by") or "family").strip().lower()
    if group_by not in GROUP_DIMENSIONS:
        return validation_error(
            f"無效的 group_by 參數: {group_by}（允許值: {', '.join(sorted(GROUP_DIMENSIONS))}）"
        )

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.uph_performance_service import get_trend
        result = get_trend(spool_path, filters, group_by=group_by)
        return success_response(result)
    except Exception as exc:
        logger.error("uph_performance_routes: trend failed query_id=%s: %s", query_id, exc)
        return internal_error("Trend 查詢失敗")


# ── GET /api/uph-performance/ranking ─────────────────────────────────────────

@uph_performance_bp.route("/ranking", methods=["GET"])
def api_uph_performance_ranking():
    """Return per-equipment avg-UPH ranking, ascending (lowest UPH first).

    ``pj_type[]`` is this endpoint's OWN filter axis, independent of the
    page's global filters (data-shape §3.29 Ranking) -- NOT read from
    _parse_fine_filters(), NOT part of the spool key.
    """
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    pj_types = _parse_list_param("pj_type")

    try:
        from mes_dashboard.services.uph_performance_service import get_ranking
        result = get_ranking(spool_path, pj_types=pj_types)
        return success_response(result)
    except Exception as exc:
        logger.error("uph_performance_routes: ranking failed query_id=%s: %s", query_id, exc)
        return internal_error("Ranking 查詢失敗")


# ── GET /api/uph-performance/detail ──────────────────────────────────────────

@uph_performance_bp.route("/detail", methods=["GET"])
def api_uph_performance_detail():
    """Return paginated detail rows from the DuckDB spool. per_page max 200."""
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page") or 50)
    except (TypeError, ValueError):
        per_page = 50

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.uph_performance_service import get_detail
        result = get_detail(spool_path, filters, page=page, per_page=per_page)
        return success_response(result)
    except Exception as exc:
        logger.error("uph_performance_routes: detail failed query_id=%s: %s", query_id, exc)
        return internal_error("Detail 查詢失敗")
