# -*- coding: utf-8 -*-
"""Material trace API routes."""

from __future__ import annotations

import logging

from flask import Blueprint, Response, stream_with_context

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.request_validation import parse_json_payload
from mes_dashboard.core.response import (
    internal_error,
    service_unavailable_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.container_resolution_policy import (
    validate_resolution_request,
)
from mes_dashboard.services.filter_cache import get_workcenter_groups
from mes_dashboard.services.material_trace_service import (
    export_csv,
    forward_query,
    reverse_query,
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
    """Execute material trace query (forward or reverse)."""
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return validation_error(payload_error.message)

    error, mode, values, workcenter_groups, page, per_page = _validate_query_params(body)
    if error:
        return validation_error(error)

    try:
        if mode in _FORWARD_MODES:
            result = forward_query(mode, values, workcenter_groups, page, per_page)
        else:
            result = reverse_query(values, workcenter_groups, page, per_page)

        return success_response(result)

    except MemoryError as exc:
        logger.warning("Material trace query memory guard: %s", exc)
        return validation_error(str(exc))
    except Exception:
        logger.exception("Material trace query failed: mode=%s", mode)
        return internal_error()


@material_trace_bp.route("/api/material-trace/export", methods=["POST"])
@_EXPORT_RATE_LIMIT
def api_material_trace_export():
    """Export material trace query results as CSV."""
    body, payload_error = parse_json_payload(require_non_empty_object=True)
    if payload_error is not None:
        return validation_error(payload_error.message)

    error, mode, values, workcenter_groups, _page, _per_page = _validate_query_params(body)
    if error:
        return validation_error(error)

    try:
        csv_stream, export_meta = export_csv(mode, values, workcenter_groups)
        meta = export_meta.get("meta") if isinstance(export_meta, dict) else {}
        quality_meta = export_meta.get("quality_meta") if isinstance(export_meta, dict) else {}
        status = str((quality_meta or {}).get("status", "complete")).strip().lower() or "complete"
        reasons = quality_meta.get("reasons") if isinstance(quality_meta, dict) else []
        reason_header = ",".join([str(r).strip() for r in (reasons or []) if str(r).strip()])

        response = Response(
            stream_with_context(csv_stream),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=material_trace.csv",
                "X-Query-Quality-Status": status,
                "X-Query-Quality-Reasons": reason_header,
            },
        )
        if isinstance(quality_meta, dict):
            observed_rows = quality_meta.get("observed_rows")
            max_rows = quality_meta.get("max_rows")
            if observed_rows is not None:
                response.headers["X-Query-Quality-Observed-Rows"] = str(observed_rows)
            if max_rows is not None:
                response.headers["X-Query-Quality-Max-Rows"] = str(max_rows)

        if status == "truncated" or (isinstance(meta, dict) and meta.get("truncated")):
            response.headers["X-Truncated"] = "true"
            response.headers["X-Max-Rows"] = str(
                (meta or {}).get("export_max_rows")
                or (quality_meta or {}).get("max_rows")
                or ""
            )
        return response

    except MemoryError as exc:
        logger.warning("Material trace export memory guard: %s", exc)
        return validation_error(str(exc))
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
