# -*- coding: utf-8 -*-
"""Material trace API routes."""

from __future__ import annotations

import logging
import uuid

from flask import Blueprint, Response, stream_with_context

from mes_dashboard.core.heavy_query_telemetry import record_memory_error
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.response import (
    SERVICE_UNAVAILABLE,
    error_response,
    internal_error,
    not_found_error,
    service_unavailable_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.container_resolution_policy import (
    validate_resolution_request,
)
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.services.async_query_job_service import enqueue_job, get_job_status
from mes_dashboard.services.material_trace_duckdb_runtime import MaterialTraceDuckdbRuntime
from mes_dashboard.services.material_trace_service import (
    MATERIAL_TRACE_QUEUE,
    make_route_query_hash,
    rq_material_trace_job,
)

logger = logging.getLogger("mes_dashboard.material_trace")

material_trace_bp = Blueprint("material_trace", __name__)

# ============================================================
# Constants
# ============================================================

_VALID_MODES = {"lot", "workorder", "material_lot"}
_FORWARD_MODES = {"lot", "workorder"}
_FORWARD_INPUT_LIMIT = 200
_REVERSE_INPUT_LIMIT = 50
_MAX_PER_PAGE = 200

# ============================================================
# Rate Limiting
# ============================================================

_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket="material-trace-query",
    max_attempts_env="MATERIAL_TRACE_QUERY_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="MATERIAL_TRACE_QUERY_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=30,
    default_window_seconds=60,
)

_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="material-trace-export",
    max_attempts_env="MATERIAL_TRACE_EXPORT_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="MATERIAL_TRACE_EXPORT_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)

# ============================================================
# Helpers
# ============================================================


def _validate_query_params(body: dict) -> tuple[str | None, str, list[str], list[str] | None, int, int]:
    """Validate and extract query parameters.

    Returns:
        (error_message, mode, values, workcenter_groups, page, per_page)
    """
    mode = str(body.get("mode", "")).strip()
    if mode not in _VALID_MODES:
        return f"無效的查詢模式，可用值: {', '.join(sorted(_VALID_MODES))}", "", [], None, 1, 50

    raw_values = body.get("values")
    if not isinstance(raw_values, list):
        return "values 必須為陣列", mode, [], None, 1, 50

    values = [str(v).strip() for v in raw_values if str(v).strip()]
    if not values:
        return "請輸入至少一筆查詢條件", mode, [], None, 1, 50

    # Input count limits
    if mode in _FORWARD_MODES and len(values) > _FORWARD_INPUT_LIMIT:
        return f"正向查詢上限 {_FORWARD_INPUT_LIMIT} 筆", mode, values, None, 1, 50
    if mode == "material_lot" and len(values) > _REVERSE_INPUT_LIMIT:
        return f"反向查詢上限 {_REVERSE_INPUT_LIMIT} 筆", mode, values, None, 1, 50

    # Wildcard prefix safety (reuse container_resolution_policy guardrails)
    _INPUT_TYPE_LABELS = {"lot": "LOT ID", "workorder": "工單", "material_lot": "原物料批號"}
    wildcard_error = validate_resolution_request(_INPUT_TYPE_LABELS.get(mode, mode), values)
    if wildcard_error:
        return wildcard_error, mode, values, None, 1, 50

    # Optional workcenter groups
    raw_groups = body.get("workcenter_groups")
    workcenter_groups = None
    if isinstance(raw_groups, list) and raw_groups:
        workcenter_groups = [str(g).strip() for g in raw_groups if str(g).strip()]
        if not workcenter_groups:
            workcenter_groups = None

    page = max(1, int(body.get("page", 1) or 1))
    per_page = min(max(1, int(body.get("per_page", 50) or 50)), _MAX_PER_PAGE)

    return None, mode, values, workcenter_groups, page, per_page


# ============================================================
# Routes
# ============================================================


@material_trace_bp.route("/api/material-trace/query", methods=["POST"])
@_QUERY_RATE_LIMIT
def api_material_trace_query():
    """Execute material trace query (forward or reverse).

    Task 8.3/8.4: Checks spool first (DuckDB hit), enqueues async RQ job on
    miss, and fails closed if the background worker path is unavailable.
    """
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return validation_error(payload_error.message)

    error, mode, values, workcenter_groups, page, per_page = _validate_query_params(body)
    if error:
        return validation_error(error)

    try:
        # ── Task 8.3: Try spool hit first (DuckDB, no Oracle) ──────────────
        query_hash = make_route_query_hash(mode, values, workcenter_groups)
        try:
            rt = MaterialTraceDuckdbRuntime(query_hash)
            if rt.is_available():
                duckdb_result = rt.get_page(page, per_page)
                if duckdb_result is not None:
                    return success_response(duckdb_result)
        except Exception as _spool_exc:
            logger.debug("material_trace spool hit check failed: %s", _spool_exc)

        # ── Spool miss — enqueue async RQ job ───────────────────────────────
        try:
            from mes_dashboard.core.permissions import get_owner_token
            generated_job_id = f"mtrace-{uuid.uuid4().hex[:12]}"
            job_id, err = enqueue_job(
                queue_name=MATERIAL_TRACE_QUEUE,
                worker_fn=rq_material_trace_job,
                owner=get_owner_token(),
                prefix="material_trace",
                job_id=generated_job_id,
                kwargs={
                    "job_id": generated_job_id,
                    "mode": mode,
                    "values": values,
                    "workcenter_groups": workcenter_groups,
                },
            )
            if job_id is not None:
                return success_response(
                    {
                        "async": True,
                        "job_id": job_id,
                        "status_url": f"/api/material-trace/job/{job_id}",
                        "query_hash": query_hash,
                    },
                    status_code=202,
                )
            logger.warning("material_trace async enqueue failed (%s)", err)
        except Exception as _enqueue_exc:
            logger.warning("material_trace enqueue error: %s", _enqueue_exc)
        return error_response(
            SERVICE_UNAVAILABLE,
            "背景查詢服務不可用，請稍後再試",
            status_code=503,
            headers={"Retry-After": "30"},
        )

    except MemoryError as exc:
        logger.warning("Material trace query memory guard: %s", exc)
        record_memory_error("material_trace.query", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            str(exc),
            status_code=503,
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("Material trace query failed: mode=%s", mode)
        return internal_error()


@material_trace_bp.route("/api/material-trace/job/<job_id>", methods=["GET"])
@_QUERY_RATE_LIMIT
def api_material_trace_job_status(job_id: str):
    """Get async material trace job status (task 8.3)."""
    status = get_job_status("material_trace", job_id)
    if status is None:
        return not_found_error("Job not found")
    return success_response(status)


@material_trace_bp.route("/api/material-trace/export", methods=["POST"])
@_EXPORT_RATE_LIMIT
def api_material_trace_export():
    """Export material trace query results as CSV.

    Task 8.3/8.4: Requires ``query_hash`` from a completed query and streams
    directly from DuckDB parquet. No legacy Oracle export fallback remains.
    """
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return validation_error(payload_error.message)

    query_hash = str(body.get("query_hash") or "").strip()
    if not query_hash:
        return validation_error("匯出需提供 query_hash，請先完成查詢")

    error, mode, values, workcenter_groups, _page, _per_page = _validate_query_params(body)
    if error:
        return validation_error(error)

    try:
        rt = MaterialTraceDuckdbRuntime(query_hash)
        if not rt.is_available():
            return error_response(
                "QUERY_NOT_READY",
                "查詢結果尚未就緒，請先完成查詢",
                status_code=409,
            )

        return Response(
            stream_with_context(rt.export_csv()),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=material_trace.csv",
                "X-Query-Quality-Status": "complete",
            },
        )

    except MemoryError as exc:
        logger.warning("Material trace export memory guard: %s", exc)
        record_memory_error("material_trace.export", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            str(exc),
            status_code=503,
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("Material trace export failed: mode=%s", mode)
        return internal_error()


@material_trace_bp.route("/api/material-trace/filter-options", methods=["GET"])
def api_material_trace_filter_options():
    """Return workcenter group options for filter dropdown."""
    groups = get_workcenter_groups()
    if groups is None:
        return service_unavailable_error("站群組資料載入中")

    return success_response({
        "workcenter_groups": [g["name"] for g in groups],
    })
