# -*- coding: utf-8 -*-
"""Production History API routes.

Blueprint: production_history_bp
Prefix: /api/production-history

Endpoints:
  POST /query          — Oracle primary query → spool → first-page + matrix (200) or async job (202)
  GET  /job/<job_id>   — Async job status
  POST /page           — DuckDB detail page (dataset-backed)
  POST /matrix         — DuckDB matrix summary (dataset-backed)
  POST /options        — DuckDB distinct filter options (dataset-backed)
  GET  /export         — DuckDB full CSV stream (dataset-backed)
"""

from __future__ import annotations

import json
import logging
import os

from flask import Blueprint, Response, request, stream_with_context

from mes_dashboard.core.heavy_query_telemetry import (
    record_memory_error,
)
from mes_dashboard.core.query_spool_store import get_spool_file_path
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.response import (
    SERVICE_UNAVAILABLE,
    VALIDATION_ERROR,
    cache_expired_error,
    error_response,
    internal_error,
    not_found_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.production_history_service import (
    get_type_options,
    make_canonical_spool_id,
    query_production_history,
    validate_query_params,
)
from mes_dashboard.services.production_history_sql_runtime import (
    compute_detail_page,
    compute_filter_options,
    compute_matrix_view,
    stream_export,
)

logger = logging.getLogger("mes_dashboard.production_history_routes")

production_history_bp = Blueprint("production_history", __name__)

_SPOOL_NAMESPACE = "production_history"

_ENABLED = os.getenv("PROD_HISTORY_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_dataset(dataset_id: str):
    """Return spool path string or a 410 cache_expired_error Flask response."""
    if not dataset_id:
        return validation_error("缺少必要參數: dataset_id")
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, dataset_id)
    if spool_path is None:
        return cache_expired_error("dataset_expired")
    return spool_path


def _parse_filter_params(source: dict) -> dict:
    """Extract shared filter params (matrix singular + supplementary arrays)."""
    result = {
        "workcenter_group": str(source.get("workcenter_group") or "").strip(),
        "spec": str(source.get("spec") or "").strip(),
        "equipment_id": str(source.get("equipment_id") or "").strip(),
        "month": str(source.get("month") or "").strip(),
    }
    # Supplementary multi-select filters (arrays of strings)
    for key in ("work_orders", "lot_ids", "packages", "bop_codes", "workcenter_groups", "equipment_ids"):
        raw = source.get(key)
        if isinstance(raw, list) and raw:
            result[key] = [str(v).strip() for v in raw if str(v).strip()]
    return result


# ── GET /api/production-history/filter-options ────────────────────────────────

@production_history_bp.route("/api/production-history/filter-options", methods=["GET"])
def api_production_history_filter_options():
    """Cross-filter cached options for production-history first-tier filters.

    Query param ``selected`` is URL-encoded JSON of the form::

        {"pj_types": [...], "packages": [...],
         "bops": [...], "pj_functions": [...]}

    Empty / omitted → returns the full distinct set for each field
    (data-shape §2.7 / AC-1). Unknown keys are silently ignored;
    selection values not present in the cache are silently dropped
    (fail-open picker).
    """
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    raw_selected = request.args.get("selected")
    selected: dict | None = None
    if raw_selected:
        try:
            parsed = json.loads(raw_selected)
        except (TypeError, ValueError):
            return validation_error("selected 參數需為合法 JSON")
        if not isinstance(parsed, dict):
            return validation_error("selected 參數需為 JSON 物件")
        selected = parsed

    try:
        from mes_dashboard.services.container_filter_cache import (
            SCHEMA_VERSION,
            get_filter_options,
        )
        opts = get_filter_options(selected)
        return success_response(
            {
                "pj_types": opts.get("pj_types") or [],
                "packages": opts.get("packages") or [],
                "bops": opts.get("bops") or [],
                "pj_functions": opts.get("pj_functions") or [],
            },
            meta={
                "updated_at": opts.get("updated_at"),
                "schema_version": opts.get("schema_version", SCHEMA_VERSION),
            },
        )
    except Exception:
        logger.exception("production_history filter-options failed")
        return internal_error("篩選選項查詢失敗")


# ── GET /api/production-history/type-options ──────────────────────────────────

@production_history_bp.route("/api/production-history/type-options", methods=["GET"])
def api_production_history_type_options():
    if not _ENABLED:
        return not_found_error("production_history_disabled")
    try:
        items = get_type_options()
        return success_response({"items": items})
    except Exception:
        logger.exception("production_history type-options failed")
        return internal_error("Type 選項查詢失敗")


# ── GET /api/production-history/count ────────────────────────────────────────

@production_history_bp.route("/api/production-history/count", methods=["GET"])
def api_production_history_count():
    """Row-count baseline for data integrity probes.

    Returns COUNT(*) of grouped production records for the given date range,
    running a single-pass query without chunking.  Used to detect truncation
    in the chunk-merge pipeline.  pj_types is optional (all types if omitted).
    """
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    start_date = (request.args.get("start_date") or "").strip()
    end_date = (request.args.get("end_date") or "").strip()
    if not start_date or not end_date:
        return validation_error("缺少必要參數: start_date, end_date")

    # Accept repeated ?pj_types=X&pj_types=Y OR single comma-separated value
    pj_types_raw = request.args.getlist("pj_types")
    if len(pj_types_raw) == 1 and "," in pj_types_raw[0]:
        pj_types_raw = [t.strip() for t in pj_types_raw[0].split(",") if t.strip()]
    pj_types = [t.strip() for t in pj_types_raw if t.strip()]

    try:
        from mes_dashboard.services.production_history_service import query_row_count
        count = query_row_count(
            start_date=start_date,
            end_date=end_date,
            pj_types=pj_types or None,
        )
        return success_response({"count": count})
    except ValueError as exc:
        return validation_error(str(exc))
    except Exception:
        logger.exception("production_history count query failed")
        return internal_error("count query failed")


# ── POST /api/production-history/query ───────────────────────────────────────

@production_history_bp.route("/api/production-history/query", methods=["POST"])
def api_production_history_query():
    """Primary query: execute Oracle → spool → return results.

    Supports two response codes:
      200 - existing spooled result served immediately
      202 - spool miss enqueued to RQ for background execution
    """
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    try:
        validate_query_params(body)
    except ValueError as exc:
        return error_response(VALIDATION_ERROR, str(exc), status_code=400)

    # Check if spool already exists for these params — serve immediately if so
    dataset_id = make_canonical_spool_id(body)

    if dataset_id and get_spool_file_path(_SPOOL_NAMESPACE, dataset_id) is not None:
        try:
            result = query_production_history(body)
            return success_response(result, meta=result.pop("meta", None))
        except MemoryError:
            record_memory_error("production_history.query", reason="rss_guard")
            return error_response(
                SERVICE_UNAVAILABLE,
                "伺服器記憶體不足，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": 60, "error_code": "memory_guard_rejected"},
                headers={"Retry-After": "60"},
            )
        except ValueError as exc:
            return error_response(VALIDATION_ERROR, str(exc), status_code=400)
        except Exception:
            logger.exception("production_history primary query failed (spool hit path)")
            return internal_error("生產歷程查詢失敗")

    # Spool miss — try async path
    from mes_dashboard.services.async_query_job_service import is_async_available
    from mes_dashboard.services.production_history_job_service import (
        PRODUCTION_HISTORY_ASYNC_ENABLED,
        enqueue_production_history_query,
    )

    if PRODUCTION_HISTORY_ASYNC_ENABLED and is_async_available():
        from mes_dashboard.core.permissions import get_owner_token
        job_id, err = enqueue_production_history_query(body, owner=get_owner_token())
        if job_id is None:
            logger.warning("production_history async enqueue failed (%s)", err)
            return error_response(
                SERVICE_UNAVAILABLE,
                "背景查詢服務不可用，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": 30},
                headers={"Retry-After": "30"},
            )
        return success_response(
            {
                "async": True,
                "job_id": job_id,
                "status_url": f"/api/production-history/job/{job_id}",
                "dataset_id": dataset_id or "",
            },
            status_code=202,
        )

    # Sync fallback (RQ unavailable or async disabled)
    try:
        result = query_production_history(body)
        return success_response(result, meta=result.pop("meta", None))
    except MemoryError:
        record_memory_error("production_history.query", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            "伺服器記憶體不足，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": 60, "error_code": "memory_guard_rejected"},
            headers={"Retry-After": "60"},
        )
    except RuntimeError as exc:
        if "heavy_query_overloaded" in str(exc):
            return error_response(
                SERVICE_UNAVAILABLE,
                "查詢伺服器負載過高，請稍後再試",
                status_code=503,
                meta={"retry_after_seconds": 30, "error_code": "heavy_query_overloaded"},
                headers={"Retry-After": "30"},
            )
        logger.exception("production_history primary query failed")
        return internal_error("生產歷程查詢失敗")
    except ValueError as exc:
        return error_response(VALIDATION_ERROR, str(exc), status_code=400)
    except Exception:
        logger.exception("production_history primary query failed")
        return internal_error("生產歷程查詢失敗")


# ── GET /api/production-history/job/<job_id> ─────────────────────────────────

@production_history_bp.route("/api/production-history/job/<job_id>", methods=["GET"])
def api_production_history_job_status(job_id: str):
    """Get async query job status."""
    from mes_dashboard.services.async_query_job_service import get_job_status
    status = get_job_status("production_history", job_id)
    if status is None:
        return not_found_error("Job not found")
    return success_response(status)


# ── POST /api/production-history/page ────────────────────────────────────────

@production_history_bp.route("/api/production-history/page", methods=["POST"])
def api_production_history_page():
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    dataset_id = str(body.get("dataset_id") or "").strip()
    spool_or_err = _require_dataset(dataset_id)
    if not isinstance(spool_or_err, str):
        return spool_or_err
    spool_path = spool_or_err

    try:
        page = max(1, int(body.get("page") or 1))
    except (TypeError, ValueError):
        return validation_error("page 必須為正整數")
    try:
        per_page = max(1, min(int(body.get("per_page") or 25), 200))
    except (TypeError, ValueError):
        return validation_error("per_page 必須為正整數")

    filter_params = _parse_filter_params(body)

    sort_by = str(body.get("sort_by") or "trackin_time").strip()
    sort_dir = str(body.get("sort_dir") or "asc").strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    try:
        result = compute_detail_page(
            spool_path, filter_params,
            page=page, per_page=per_page,
            sort_by=sort_by, sort_dir=sort_dir,
        )
        return success_response(result)
    except MemoryError:
        record_memory_error("production_history.page", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            "伺服器記憶體不足，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": 30, "error_code": "memory_guard_rejected"},
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("production_history page view failed")
        return internal_error("分頁查詢失敗")


# ── POST /api/production-history/matrix ──────────────────────────────────────

@production_history_bp.route("/api/production-history/matrix", methods=["POST"])
def api_production_history_matrix():
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    dataset_id = str(body.get("dataset_id") or "").strip()
    spool_or_err = _require_dataset(dataset_id)
    if not isinstance(spool_or_err, str):
        return spool_or_err
    spool_path = spool_or_err

    filter_params = _parse_filter_params(body)

    try:
        result = compute_matrix_view(spool_path, filter_params)
        return success_response(result)
    except MemoryError:
        record_memory_error("production_history.matrix", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            "伺服器記憶體不足，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": 30, "error_code": "memory_guard_rejected"},
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("production_history matrix view failed")
        return internal_error("Matrix 查詢失敗")


# ── POST /api/production-history/options ─────────────────────────────────────

@production_history_bp.route("/api/production-history/options", methods=["POST"])
def api_production_history_options():
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return error_response(VALIDATION_ERROR, payload_error.message, status_code=payload_error.status_code)

    dataset_id = str(body.get("dataset_id") or "").strip()
    spool_or_err = _require_dataset(dataset_id)
    if not isinstance(spool_or_err, str):
        return spool_or_err
    spool_path = spool_or_err

    filter_params = _parse_filter_params(body)

    try:
        result = compute_filter_options(spool_path, filter_params)
        return success_response(result)
    except MemoryError:
        record_memory_error("production_history.options", reason="rss_guard")
        return error_response(
            SERVICE_UNAVAILABLE,
            "伺服器記憶體不足，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": 30, "error_code": "memory_guard_rejected"},
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("production_history options failed")
        return internal_error("篩選選項查詢失敗")


# ── GET /api/production-history/export ───────────────────────────────────────

@production_history_bp.route("/api/production-history/export", methods=["GET", "POST"])
def api_production_history_export():
    if not _ENABLED:
        return not_found_error("production_history_disabled")

    # Parse parameters from JSON body (POST) or query string (GET)
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        dataset_id = str(body.get("dataset_id") or "").strip()
        spool_or_err = _require_dataset(dataset_id)
        if not isinstance(spool_or_err, str):
            return spool_or_err
        spool_path = spool_or_err
        filter_params = _parse_filter_params(body)
    else:
        dataset_id = str(request.args.get("dataset_id") or "").strip()
        spool_or_err = _require_dataset(dataset_id)
        if not isinstance(spool_or_err, str):
            return spool_or_err
        spool_path = spool_or_err
        filter_params = {
            "workcenter_group": str(request.args.get("workcenter_group") or "").strip(),
            "spec": str(request.args.get("spec") or "").strip(),
            "equipment_id": str(request.args.get("equipment_id") or "").strip(),
            "month": str(request.args.get("month") or "").strip(),
        }
        # Supplementary multi-select filters (comma-separated in query string)
        for key in ("work_orders", "lot_ids", "packages", "bop_codes", "workcenter_groups", "equipment_ids"):
            raw = str(request.args.get(key) or "").strip()
            if raw:
                filter_params[key] = [v.strip() for v in raw.split(",") if v.strip()]

    def _generate():
        try:
            yield from stream_export(spool_path, filter_params)
        except MemoryError:
            record_memory_error("production_history.export", reason="rss_guard")
            logger.exception("production_history export MemoryError")
        except Exception:
            logger.exception("production_history export stream error")

    return Response(
        stream_with_context(_generate()),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="production-history-{dataset_id}.csv"',
        },
    )
