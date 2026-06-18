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
    }


def _get_spool_path(query_id: str) -> Optional[str]:
    """Resolve spool parquet path by query_id; returns None on miss/expiry."""
    try:
        from mes_dashboard.core.query_spool_store import get_spool_file_path
        return get_spool_file_path("eap_alarm", query_id)
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
    eqp_types_raw = body.get("eqp_types", [])
    if not isinstance(eqp_types_raw, list):
        eqp_types_raw = [eqp_types_raw] if eqp_types_raw else []
    eqp_types = [str(t).strip() for t in eqp_types_raw if str(t).strip()]

    # Validate params (EA-03, EA-07)
    try:
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params(date_from, date_to, eqp_types)
    except ValueError as exc:
        return validation_error(str(exc))

    # Build spool key to check for cache hit
    try:
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        spool_key = make_eap_alarm_spool_key(date_from, date_to, eqp_types)
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
        from mes_dashboard.services.async_query_job_service import is_async_available, enqueue_job
        from mes_dashboard.workers.eap_alarm_worker import (
            run_eap_alarm_query_job,
            EAP_ALARM_WORKER_QUEUE,
            EAP_ALARM_JOB_TIMEOUT_SECONDS,
            EAP_ALARM_JOB_TTL_SECONDS,
        )
        from mes_dashboard.core.permissions import get_owner_token

        job_id = f"eap-alarm-{uuid.uuid4().hex[:12]}"

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
            },
            prefix=_JOB_PREFIX,
            job_timeout=EAP_ALARM_JOB_TIMEOUT_SECONDS,
            result_ttl=EAP_ALARM_JOB_TTL_SECONDS,
        )

        if job_id_result is None:
            logger.warning("eap_alarm_routes: async enqueue failed: %s", err)
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
                "status_url": f"/api/eap-alarm/spool/status?query_id={spool_key}",
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
    """Return top-50 alarm_text Pareto from DuckDB spool."""
    query_id, err = _require_query_id()
    if err is not None:
        return err

    spool_path, err = _require_spool(query_id)
    if err is not None:
        return err

    filters = _parse_fine_filters()

    try:
        from mes_dashboard.services.eap_alarm_service import get_pareto
        result = get_pareto(spool_path, filters)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: pareto failed query_id=%s: %s", query_id, exc)
        return internal_error("Pareto 查詢失敗")


# ── GET /api/eap-alarm/trend ──────────────────────────────────────────────────

@eap_alarm_bp.route("/api/eap-alarm/trend", methods=["GET"])
def api_eap_alarm_trend():
    """Return stacked trend (by eqp_type) from DuckDB spool."""
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

    try:
        from mes_dashboard.services.eap_alarm_service import get_trend
        result = get_trend(spool_path, filters, granularity=granularity)
        return success_response(result)
    except Exception as exc:
        logger.error("eap_alarm_routes: trend failed query_id=%s: %s", query_id, exc)
        return internal_error("Trend 查詢失敗")


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
