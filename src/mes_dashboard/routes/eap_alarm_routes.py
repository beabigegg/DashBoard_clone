# -*- coding: utf-8 -*-
"""EAP ALARM Analysis route Blueprint.

7 endpoints (api-contract.md rows 248-254):
  POST /api/eap-alarm/spool             — Type B async; 202 or spool-hit 200
  GET  /api/eap-alarm/spool/status      — poll job status
  GET  /api/eap-alarm/filter-options    — DuckDB-only fine filter options
  GET  /api/eap-alarm/summary           — DuckDB-only summary stats
  GET  /api/eap-alarm/pareto            — DuckDB-only top-50 Pareto
  GET  /api/eap-alarm/trend             — DuckDB-only stacked trend
  GET  /api/eap-alarm/detail            — DuckDB-only paginated detail

All endpoints require auth (enforced by app.py before_request).
Fine-filter endpoints return 410 on spool miss (EA-02/ASYNC-01).
No sync fallback path (design.md "Always-async, no sync fallback").
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

eap_alarm_bp = Blueprint("eap_alarm", __name__)
logger = logging.getLogger("mes_dashboard.eap_alarm_routes")

_EAP_ALARM_RETRY_AFTER_SECONDS = int(
    os.getenv("EAP_ALARM_RETRY_AFTER_SECONDS", "30")
)
_JOB_PREFIX = "eap-alarm"
_EAP_ALARM_USE_UNIFIED_JOB: bool = os.getenv(
    "EAP_ALARM_USE_UNIFIED_JOB", "on"
).lower().strip() in ("on", "true", "1")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_list_param(name: str) -> List[str]:
    """Parse repeated query param or JSON array from request."""
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        val = body.get(name)
        if isinstance(val, list):
            return [str(v).strip() for v in val if v is not None and str(v).strip()]
        if val is not None:
            return [str(val).strip()]
        return []
    # GET: getlist handles ?name[]=x&name[]=y and ?name=x
    vals = request.args.getlist(f"{name}[]") or request.args.getlist(name)
    return [str(v).strip() for v in vals if v is not None and str(v).strip()]


def _parse_fine_filters() -> Dict[str, Any]:
    """Parse fine filter params from request (GET query string)."""
    alarm_texts = _parse_list_param("alarm_text")
    alarm_category_codes_raw = _parse_list_param("alarm_category")
    equipment_ids = _parse_list_param("equipment_id")
    lot_ids = _parse_list_param("lot_id")
    pj_types = _parse_list_param("pj_type")
    product_lines = _parse_list_param("product_line")
    pj_bops = _parse_list_param("pj_bop")

    alarm_category_codes = []
    for c in alarm_category_codes_raw:
        try:
            alarm_category_codes.append(int(c))
        except (ValueError, TypeError):
            pass

    return {
        "alarm_text": alarm_texts or None,
        "alarm_category_code": alarm_category_codes or None,
        "equipment_id": equipment_ids or None,
        "lot_id": lot_ids or None,
        "pj_type": pj_types or None,
        "product_line": product_lines or None,
        "pj_bop": pj_bops or None,
    }


def _get_spool_path(query_id: str) -> Optional[str]:
    """Resolve spool parquet path by query_id; returns None on miss/expiry."""
    try:
        from mes_dashboard.core.query_spool_store import get_spool_file_path
        path = get_spool_file_path("eap_alarm", query_id)
        if path is not None and not os.path.exists(path):
            logger.warning(
                "eap_alarm_routes: parquet missing from disk (stale metadata) "
                "query_id=%s path=%s", query_id, path
            )
            return None
        return path
    except Exception as exc:
        logger.warning("eap_alarm_routes: spool path lookup failed query_id=%s: %s", query_id, exc)
        return None


def _require_query_id() -> tuple[Optional[str], Optional[Any]]:
    """Parse and validate query_id from request; return (query_id, error_response)."""
    query_id = (request.args.get("query_id") or "").strip()
    if not query_id:
        return None, validation_error("缺少必要參數: query_id")
    return query_id, None


def _require_spool(query_id: str) -> tuple[Optional[str], Optional[Any]]:
    """Resolve spool path; return (spool_path, error_response) on miss."""
    spool_path = _get_spool_path(query_id)
    if spool_path is None:
        return None, cache_expired_error("EAP ALARM spool 不存在或已過期，請重新提交查詢")
    return spool_path, None


# ── POST /api/eap-alarm/spool ─────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/spool", methods=["POST"])
def api_eap_alarm_spool():
    """Trigger coarse spool query (Type B async, always-async, no sync fallback).

    On spool cache hit: returns 200 with existing query_id.
    On spool miss: enqueues RQ job, returns 202 with job_id + status_url + query_id.
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

    # Parse eqp_types (formerly 'machines'; accept both keys for backward compat)
    eqp_types_raw = body.get("eqp_types") or body.get("machines") or []
    if not isinstance(eqp_types_raw, list):
        eqp_types_raw = [eqp_types_raw] if eqp_types_raw else []
    eqp_types = [str(m).strip() for m in eqp_types_raw if str(m).strip()]

    # Parse new coarse dims
    lot_ids_raw = body.get("lot_ids") or []
    if not isinstance(lot_ids_raw, list):
        lot_ids_raw = [lot_ids_raw] if lot_ids_raw else []
    lot_ids = [str(v).strip() for v in lot_ids_raw if str(v).strip()]

    pj_types_raw = body.get("pj_types") or []
    if not isinstance(pj_types_raw, list):
        pj_types_raw = [pj_types_raw] if pj_types_raw else []
    pj_types = [str(v).strip() for v in pj_types_raw if str(v).strip()]

    product_lines_raw = body.get("product_lines") or []
    if not isinstance(product_lines_raw, list):
        product_lines_raw = [product_lines_raw] if product_lines_raw else []
    product_lines = [str(v).strip() for v in product_lines_raw if str(v).strip()]

    pj_bops_raw = body.get("pj_bops") or []
    if not isinstance(pj_bops_raw, list):
        pj_bops_raw = [pj_bops_raw] if pj_bops_raw else []
    pj_bops = [str(v).strip() for v in pj_bops_raw if str(v).strip()]

    # Validate params (EA-03, EA-07, EA-08, EA-09)
    try:
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params(
            date_from, date_to,
            eqp_types=eqp_types,
            lot_ids=lot_ids,
            pj_types=pj_types,
            product_lines=product_lines,
            pj_bops=pj_bops,
        )
    except ValueError as exc:
        return validation_error(str(exc))

    # Build spool key to check for cache hit
    try:
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        spool_key = make_eap_alarm_spool_key(
            date_from, date_to, eqp_types, lot_ids, pj_types, product_lines, pj_bops
        )
    except ValueError as exc:
        return validation_error(str(exc))

    # Check spool hit — if parquet exists and is valid, return immediately
    spool_path = _get_spool_path(spool_key)
    if spool_path is not None:
        logger.info("eap_alarm_routes: spool cache hit query_id=%s", spool_key)
        return success_response({
            "async": False,
            "query_id": spool_key,
            "spool_path": None,  # not exposed to client
        })

    # Enqueue RQ job
    try:
        from mes_dashboard.core.permissions import get_owner_token

        job_id = f"eap-alarm-{uuid.uuid4().hex[:12]}"

        if _EAP_ALARM_USE_UNIFIED_JOB:
            from mes_dashboard.services.async_query_job_service import enqueue_query_job
            import mes_dashboard.workers.eap_alarm_worker  # noqa: F401 — triggers registration

            job_id_result, err, status_hint = enqueue_query_job(
                "eap-alarm",
                owner=get_owner_token(),
                params={
                    "job_id": job_id,
                    "date_from": date_from,
                    "date_to": date_to,
                    "eqp_types": eqp_types,
                    "lot_ids": lot_ids,
                    "pj_types": pj_types,
                    "product_lines": product_lines,
                    "pj_bops": pj_bops,
                },
                sync_fallback_allowed=False,
                job_id=job_id,
            )
        else:
            from mes_dashboard.services.async_query_job_service import enqueue_job
            from mes_dashboard.workers.eap_alarm_worker import (
                run_eap_alarm_query_job,
                EAP_ALARM_WORKER_QUEUE,
                EAP_ALARM_JOB_TIMEOUT_SECONDS,
                EAP_ALARM_JOB_TTL_SECONDS,
            )
            job_id_result, err = enqueue_job(
                queue_name=EAP_ALARM_WORKER_QUEUE,
                worker_fn=run_eap_alarm_query_job,
                owner=get_owner_token(),
                job_id=job_id,
                kwargs={
                    "job_id": job_id,
                    "date_from": date_from,
                    "date_to": date_to,
                    "eqp_types": eqp_types,
                    "lot_ids": lot_ids,
                    "pj_types": pj_types,
                    "product_lines": product_lines,
                    "pj_bops": pj_bops,
                },
                prefix=_JOB_PREFIX,
                job_timeout=EAP_ALARM_JOB_TIMEOUT_SECONDS,
                result_ttl=EAP_ALARM_JOB_TTL_SECONDS,
            )
            status_hint = None

        if job_id_result is None:
            logger.warning(
                "eap_alarm_routes: async enqueue failed (hint=%s): %s", status_hint, err
            )
            return error_response(
                SERVICE_UNAVAILABLE,
                "背景查詢服務不可用，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": _EAP_ALARM_RETRY_AFTER_SECONDS},
                headers={"Retry-After": str(_EAP_ALARM_RETRY_AFTER_SECONDS)},
            )

        return success_response(
            {
                "async": True,
                "job_id": job_id_result,
                "status_url": f"/api/eap-alarm/spool/status?job_id={job_id}",
                "query_id": spool_key,
            },
            status_code=202,
        )

    except Exception as exc:
        logger.error("eap_alarm_routes: spool trigger failed: %s", exc, exc_info=True)
        return internal_error("EAP ALARM 查詢觸發失敗")


# ── GET /api/eap-alarm/spool/status ──────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/spool/status", methods=["GET"])
def api_eap_alarm_spool_status():
    """Poll async job status by job_id (proxy to /api/job/<job_id>?prefix=eap-alarm)."""
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        # Also allow polling by query_id for spool-hit case
        query_id = (request.args.get("query_id") or "").strip()
        if query_id:
            spool_path = _get_spool_path(query_id)
            if spool_path is not None:
                return success_response({"status": "complete", "query_id": query_id})
            return cache_expired_error("EAP ALARM spool 不存在")
        return validation_error("缺少必要參數: job_id 或 query_id")

    try:
        from mes_dashboard.services.async_query_job_service import get_job_status
        status = get_job_status(_JOB_PREFIX, job_id)
        if status is None:
            from mes_dashboard.core.response import not_found_error
            return not_found_error("Job not found")
        return success_response(status)
    except Exception as exc:
        logger.error("eap_alarm_routes: status lookup failed job_id=%s: %s", job_id, exc)
        return internal_error("Job 狀態查詢失敗")


# ── GET /api/eap-alarm/filter-options ────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/filter-options", methods=["GET"])
def api_eap_alarm_filter_options():
    """Return distinct fine-filter options from DuckDB spool (EA-02)."""
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.eap_alarm_service import get_filter_options
        result = get_filter_options(spool_path, filters)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: filter-options failed query_id=%s: %s", query_id, exc)
        return internal_error("Filter options 查詢失敗")


# ── GET /api/eap-alarm/summary ────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/summary", methods=["GET"])
def api_eap_alarm_summary():
    """Return summary stats from DuckDB spool."""
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.eap_alarm_service import get_summary
        result = get_summary(spool_path, filters)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: summary failed query_id=%s: %s", query_id, exc)
        return internal_error("Summary 查詢失敗")


# ── GET /api/eap-alarm/pareto ─────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/pareto", methods=["GET"])
def api_eap_alarm_pareto():
    """Return top-50 Pareto from DuckDB spool.

    ``dim`` selects the group dimension (default alarm_text); closed enum
    validated against service GROUP_DIMENSIONS → 400 on unknown value.
    """
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()

    from mes_dashboard.services.eap_alarm_service import GROUP_DIMENSIONS
    dim = (request.args.get("dim") or "alarm_text").strip().lower()
    if dim not in GROUP_DIMENSIONS:
        return validation_error(
            f"無效的 dim 參數: {dim}（允許值: {', '.join(sorted(GROUP_DIMENSIONS))}）"
        )

    try:
        from mes_dashboard.services.eap_alarm_service import get_pareto
        result = get_pareto(spool_path, filters, dim=dim)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: pareto failed query_id=%s: %s", query_id, exc)
        return internal_error("Pareto 查詢失敗")


# ── GET /api/eap-alarm/trend ──────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/trend", methods=["GET"])
def api_eap_alarm_trend():
    """Return stacked trend from DuckDB spool.

    ``group_by`` selects the stack dimension (default alarm_text); closed enum
    validated against service GROUP_DIMENSIONS → 400 on unknown value.
    """
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()
    granularity = (request.args.get("granularity") or "day").strip().lower()
    if granularity not in ("day", "hour"):
        granularity = "day"

    from mes_dashboard.services.eap_alarm_service import GROUP_DIMENSIONS
    group_by = (request.args.get("group_by") or "alarm_text").strip().lower()
    if group_by not in GROUP_DIMENSIONS:
        return validation_error(
            f"無效的 group_by 參數: {group_by}（允許值: {', '.join(sorted(GROUP_DIMENSIONS))}）"
        )

    try:
        from mes_dashboard.services.eap_alarm_service import get_trend
        result = get_trend(spool_path, filters, granularity=granularity, group_by=group_by)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: trend failed query_id=%s: %s", query_id, exc)
        return internal_error("Trend 查詢失敗")


# ── GET /api/eap-alarm/product-filter-options ────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/product-filter-options", methods=["GET"])
def api_eap_alarm_product_filter_options():
    """Return EAP alarm product-dim filter options (EA-10, D-2, §3.17).

    Wraps container_filter_cache (shared with production-history).
    Cold-cache path: returns empty arrays + updated_at=null — never 500.
    Key mapping: cache ``packages`` → response ``product_lines``;
                 cache ``bops``    → response ``pj_bops``.
    """
    try:
        from mes_dashboard.services.container_filter_cache import get_filter_options
        data = get_filter_options({})
    except Exception as exc:
        logger.warning("eap_alarm_routes: container_filter_cache failed, returning empty: %s", exc)
        data = {}

    return success_response({
        "pj_types":      data.get("pj_types") or [],
        "product_lines": data.get("packages") or [],   # packages → product_lines (PRODUCTLINENAME)
        "pj_bops":       data.get("bops") or [],        # bops → pj_bops (PJ_BOP)
        "updated_at":    data.get("updated_at"),
    })


# ── GET /api/eap-alarm/detail ─────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/detail", methods=["GET"])
def api_eap_alarm_detail():
    """Return paginated detail rows from DuckDB spool (EA-04). per_page max 200."""
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
        from mes_dashboard.services.eap_alarm_service import get_detail
        result = get_detail(spool_path, filters, page=page, per_page=per_page)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: detail failed query_id=%s: %s", query_id, exc)
        return internal_error("Detail 查詢失敗")
