# -*- coding: utf-8 -*-
"""Material Consumption API routes — 料號用量報表.

Blueprint: material_consumption_bp
URL prefix: /api/material-consumption

7 endpoints per api-contract.md line 305:
  GET  /filter-options
  POST /query              — summary (always sync)
  GET  /view               — granularity regroup from spool (MC-03, no Oracle)
  POST /detail             — detail (sync ≤ SYNC_ROW_LIMIT, else 202 async)
  GET  /detail/page        — paginated detail from spool
  GET  /detail/job/<job_id> — RQ job status poll
  POST /export             — chunked CSV stream (no full memory load)

Per CLAUDE.md route discipline:
- Keep routes thin: validation + service call + response envelope.
- Per-kwarg forwarding: each route reads params individually, no request.args pass-through.
- 400 VALIDATION_ERROR on MC-02 violations.
- 410 CACHE_EXPIRED on spool miss for /view.
"""

from __future__ import annotations

import logging

from flask import Blueprint, Response, stream_with_context

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.response import (
    cache_expired_error,
    internal_error,
    success_response,
    validation_error,
)

logger = logging.getLogger("mes_dashboard.material_consumption_routes")

material_consumption_bp = Blueprint(
    "material_consumption",
    __name__,
    url_prefix="/api/material-consumption",
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket="material-consumption-query",
    max_attempts_env="MATERIAL_CONSUMPTION_QUERY_RATE_LIMIT_MAX",
    window_seconds_env="MATERIAL_CONSUMPTION_QUERY_RATE_LIMIT_WINDOW",
    default_max_attempts=30,
    default_window_seconds=60,
)

_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="material-consumption-export",
    max_attempts_env="MATERIAL_CONSUMPTION_EXPORT_RATE_LIMIT_MAX",
    window_seconds_env="MATERIAL_CONSUMPTION_EXPORT_RATE_LIMIT_WINDOW",
    default_max_attempts=10,
    default_window_seconds=60,
)

# ---------------------------------------------------------------------------
# Helper: lazy import service (avoids startup circular import)
# ---------------------------------------------------------------------------


def _svc():
    import mes_dashboard.services.material_consumption_service as s
    return s


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@material_consumption_bp.route("/filter-options", methods=["GET"])
def get_filter_options():
    """GET /filter-options → {parts, pj_types}."""
    try:
        result = _svc().get_filter_options()
        return success_response(result)
    except Exception as exc:
        logger.error("get_filter_options failed: %s", exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/query", methods=["POST"])
@_QUERY_RATE_LIMIT
def query_summary():
    """POST /query — summary sync query.

    Body: {material_parts, start_date, end_date, granularity}
    Returns: {query_id, kpi, trend, type_breakdown}
    pj_type filtering is applied via GET /view?types=.
    """
    body, parse_err = parse_json_payload()
    if parse_err:
        return validation_error(parse_err.message), parse_err.status_code

    material_parts = body.get("material_parts")
    start_date = str(body.get("start_date") or "").strip()
    end_date = str(body.get("end_date") or "").strip()
    granularity = str(body.get("granularity") or "month").strip()

    # Required field checks
    if not material_parts:
        return validation_error("material_parts 必填")
    if not start_date or not end_date:
        return validation_error("start_date / end_date 必填")
    if granularity not in ("day", "week", "month", "quarter"):
        return validation_error("granularity 必須為 day / week / month / quarter")

    svc = _svc()
    try:
        result = svc.get_summary(
            material_parts=material_parts,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
        return success_response(result)
    except svc.ValidationError as exc:
        return validation_error(exc.message)
    except Exception as exc:
        logger.error("query_summary failed: %s", exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/view", methods=["GET"])
def view_summary():
    """GET /view?query_id=X&granularity=Y&types=T1&types=T2 — DuckDB regroup from spool (MC-03).

    Returns: {kpi, trend, type_breakdown}
    410 on spool miss (CacheExpiredError).
    types: optional repeated query param to filter by pj_type in DuckDB.
    """
    from flask import request

    query_id = request.args.get("query_id", "").strip()
    granularity = request.args.get("granularity", "month").strip()
    types = request.args.getlist("types") or None

    if not query_id:
        return validation_error("query_id 必填")
    if granularity not in ("day", "week", "month", "quarter"):
        return validation_error("granularity 必須為 day / week / month / quarter")

    svc = _svc()
    try:
        result = svc.apply_view(query_id=query_id, granularity=granularity, types=types)
        return success_response(result)
    except svc.CacheExpiredError as exc:
        return cache_expired_error(str(exc))
    except Exception as exc:
        logger.error("view_summary failed (query_id=%s): %s", query_id, exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/detail", methods=["POST"])
@_QUERY_RATE_LIMIT
def query_detail():
    """POST /detail — detail query (sync 200 or async 202 per MC-04).

    Body: {material_parts, start_date, end_date}
    Sync 200: {async: False, query_id, rows, pagination}
    Async 202: {async: True, job_id, query_id}
    """
    body, parse_err = parse_json_payload()
    if parse_err:
        return validation_error(parse_err.message), parse_err.status_code

    material_parts = body.get("material_parts")
    start_date = str(body.get("start_date") or "").strip()
    end_date = str(body.get("end_date") or "").strip()

    if not material_parts:
        return validation_error("material_parts 必填")
    if not start_date or not end_date:
        return validation_error("start_date / end_date 必填")

    svc = _svc()
    try:
        result = svc.get_detail_summary(
            material_parts=material_parts,
            start_date=start_date,
            end_date=end_date,
        )
        if result.get("async"):
            job_id = result.get("job_id")
            result["status_url"] = f"/api/material-consumption/detail/job/{job_id}"
            return success_response(result, status_code=202)
        return success_response(result, status_code=200)
    except svc.ValidationError as exc:
        return validation_error(exc.message)
    except Exception as exc:
        logger.error("query_detail failed: %s", exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/detail/page", methods=["GET"])
def get_detail_page():
    """GET /detail/page?query_id=X&page=N&sort_key=Y&sort_dir=asc — paginated detail from spool."""
    from flask import request

    query_id = request.args.get("query_id", "").strip()
    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        page = 1

    sort_key = request.args.get("sort_key", "").strip()
    sort_dir = request.args.get("sort_dir", "asc").strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    if not query_id:
        return validation_error("query_id 必填")

    svc = _svc()
    try:
        result = svc.get_detail_page(
            query_id=query_id,
            page=page,
            sort_key=sort_key,
            sort_dir=sort_dir,
        )
        if result is None:
            return cache_expired_error("查詢已過期，請重新查詢")
        return success_response(result)
    except Exception as exc:
        logger.error("get_detail_page failed (query_id=%s): %s", query_id, exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/detail/job/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """GET /detail/job/<job_id> → {status, query_id?}."""
    svc = _svc()
    try:
        result = svc.get_job_status(job_id=job_id)
        return success_response(result)
    except Exception as exc:
        logger.error("get_job_status failed (job_id=%s): %s", job_id, exc, exc_info=True)
        return internal_error(str(exc))


@material_consumption_bp.route("/export", methods=["POST"])
@_EXPORT_RATE_LIMIT
def export_csv():
    """POST /export — chunked CSV stream from detail spool (no full memory load)."""
    body, parse_err = parse_json_payload()
    if parse_err:
        return validation_error(parse_err.message), parse_err.status_code

    query_id = str(body.get("query_id") or "").strip()
    if not query_id:
        return validation_error("query_id 必填")

    svc = _svc()
    try:
        gen = svc.export_csv_stream(query_id=query_id)
        return Response(
            stream_with_context(gen),
            content_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=material_consumption.csv",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        logger.error("export_csv failed (query_id=%s): %s", query_id, exc, exc_info=True)
        return internal_error(str(exc))
