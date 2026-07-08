# -*- coding: utf-8 -*-
"""Production Achievement Rate (生產達成率) API routes.

Endpoints per api-contract.md rows 256-261:
  GET  /api/production-achievement/report
  GET  /api/production-achievement/filter-options
  GET  /api/production-achievement/targets
  PUT  /api/production-achievement/targets
  GET  /admin/api/production-achievement/permissions
  PUT  /admin/api/production-achievement/permissions/{user_identifier}

Per-endpoint MySQL-failure behavior (design.md): report/targets reads
degrade (target_qty/achievement_rate -> null, HTTP 200, never 500) when
MySQL OPS is off/unreachable. Writes return 503 SERVICE_UNAVAILABLE in that
case. PUT targets is additionally gated by can_edit_targets (403 FORBIDDEN).
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, request

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
from mes_dashboard.core.permissions import (
    admin_required,
    can_edit_targets,
    get_owner_token,
    login_required,
)
from mes_dashboard.core.query_spool_store import get_spool_file_path
from mes_dashboard.core.response import (
    SERVICE_UNAVAILABLE,
    error_response,
    forbidden_error,
    internal_error,
    service_unavailable_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.async_query_job_service import (
    enqueue_query_job,
    is_async_available,
)
from mes_dashboard.services.filter_cache import get_spec_workcenter_mapping
from mes_dashboard.services.production_achievement_permission_service import (
    MySQLUnavailableError as PermissionMySQLUnavailableError,
    get_permissions,
    upsert_permission,
)
from mes_dashboard.services.production_achievement_service import (
    ProductionAchievementValidationError,
    _validate_date_range,
    get_filter_options,
    make_canonical_pa_spool_id,
)
from mes_dashboard.services.production_achievement_target_service import (
    MySQLUnavailableError as TargetMySQLUnavailableError,
    TargetValidationError,
    get_targets,
    get_targets_map,
    upsert_target,
    validate_target_qty,
)

logger = logging.getLogger("mes_dashboard.production_achievement_routes")

production_achievement_bp = Blueprint(
    "production_achievement",
    __name__,
    url_prefix="/api/production-achievement",
)

production_achievement_admin_bp = Blueprint(
    "production_achievement_admin",
    __name__,
    url_prefix="/admin/api/production-achievement",
)

# ── Async spool feature flag (production-achievement-async-spool) ────────────
# Frozen at import time -- tests must use monkeypatch.setattr(), never setenv().
# No legacy path exists behind "off" (clean pre-launch replacement): "off" is a
# pure kill switch -- the worker module is never lazy-imported, so its job type
# never registers, and a spool-miss on /report falls straight through to the
# 503 branch below (env-contract.md PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB). A
# spool-HIT request still succeeds even with the flag off.
_PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB: bool = os.getenv(
    "PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", "on"
).strip().lower() in ("on", "true", "1")

# Hyphen/underscore split (do not conflate): the spool namespace + spool
# download path use the underscore form; the RQ job_type + status_url prefix
# use the hyphen form (data-shape-contract.md §3.28.4).
_SPOOL_NAMESPACE = "production_achievement"
_JOB_TYPE = "production-achievement"


# ============================================================
# GET /api/production-achievement/report
# ============================================================


@production_achievement_bp.route("/report", methods=["GET"])
@login_required
def api_get_report():
    """Async spool-hit (200) / enqueue (202) / no-worker (503) report endpoint.

    always_async=True -- no synchronous Oracle fallback (production-achievement-
    async-spool, ADR-0016). shift_code/workcenter_group are no longer accepted
    as server-side filters: the canonical spool key is date-range only and
    PA-06/PA-07 narrowing now happens client-side in DuckDB-WASM.
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        _validate_date_range(start_date, end_date)
    except ProductionAchievementValidationError as exc:
        return validation_error(str(exc))

    query_id = make_canonical_pa_spool_id(start_date, end_date)

    # ── Spool-hit: 200, inline maps injected unconditionally (Q1, not
    # row-count gated like resource_history's threshold) ─────────────────────
    spool_path = get_spool_file_path(_SPOOL_NAMESPACE, query_id)
    if spool_path is not None:
        try:
            spec_workcenter_map = [
                {"SPECNAME": spec, "workcenter_group": info.get("group")}
                for spec, info in get_spec_workcenter_mapping().items()
                if info.get("group")
            ]
            targets_map = [
                {"shift_code": sc, "workcenter_group": wg, "target_qty": tq}
                for (sc, wg), tq in get_targets_map().items()
            ]
        except Exception as exc:
            return internal_error(str(exc))

        return success_response({
            "query_id": query_id,
            "spool_download_url": f"/api/spool/{_SPOOL_NAMESPACE}/{query_id}.parquet",
            "spec_workcenter_map": spec_workcenter_map,
            "targets_map": targets_map,
        })

    # ── Spool-miss + no worker available: 503, no sync fallback ─────────────
    if not is_async_available():
        return error_response(
            SERVICE_UNAVAILABLE,
            "背景查詢服務不可用，請稍後再試",
            status_code=503,
            meta={"retry_after_seconds": 30},
            headers={"Retry-After": "30"},
        )

    # Lazy import registers the job type (module-level register_job_type()
    # side-effect) -- gated by the kill switch, mirrors eap_alarm_routes.py.
    if _PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB:
        import mes_dashboard.workers.production_achievement_worker  # noqa: F401

    # enqueue_job_dynamic spreads `params` into the RQ call kwargs as
    # {"job_id": ..., **params}; the worker entry is
    # execute_production_achievement_unified_job(job_id, params), so the query
    # params must be nested under a "params" key (mirrors production_history's
    # `params={"params": body}`) — a flat dict here would spread start_date/
    # end_date as unexpected top-level kwargs and raise TypeError in the worker.
    job_id_result, err, status_hint = enqueue_query_job(
        _JOB_TYPE,
        owner=get_owner_token(),
        params={"params": {"start_date": start_date, "end_date": end_date}},
        sync_fallback_allowed=False,
    )
    if job_id_result is None:
        logger.warning(
            "production_achievement: async enqueue failed (hint=%s): %s", status_hint, err
        )
        return error_response(
            SERVICE_UNAVAILABLE,
            "背景查詢服務不可用，請稍後再試",
            status_code=status_hint or 503,
            meta={"retry_after_seconds": 30},
            headers={"Retry-After": "30"},
        )

    return success_response(
        {
            "async": True,
            "job_id": job_id_result,
            "status_url": f"/api/job/{job_id_result}?prefix={_JOB_TYPE}",
        },
        status_code=202,
    )


# ============================================================
# GET /api/production-achievement/filter-options
# ============================================================


@production_achievement_bp.route("/filter-options", methods=["GET"])
@login_required
def api_get_filter_options():
    try:
        options = get_filter_options()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response(options)


# ============================================================
# GET /api/production-achievement/targets (view-only, no permission gate)
# ============================================================


@production_achievement_bp.route("/targets", methods=["GET"])
@login_required
def api_get_targets():
    shift_code = request.args.get("shift_code") or None
    workcenter_group = request.args.get("workcenter_group") or None
    rows = get_targets(shift_code=shift_code, workcenter_group=workcenter_group)
    return success_response(rows)


# ============================================================
# PUT /api/production-achievement/targets (permission-gated write)
# ============================================================


@production_achievement_bp.route("/targets", methods=["PUT"])
@login_required
def api_put_targets():
    if not can_edit_targets():
        return forbidden_error("無權限編輯目標值")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    shift_code = body.get("shift_code")
    workcenter_group = body.get("workcenter_group")
    target_qty = body.get("target_qty")

    if not shift_code or not workcenter_group:
        return validation_error("必須提供 shift_code 和 workcenter_group")

    try:
        validated_qty = validate_target_qty(target_qty)
    except TargetValidationError as exc:
        return validation_error(str(exc))

    try:
        upsert_target(
            shift_code=shift_code,
            workcenter_group=workcenter_group,
            target_qty=validated_qty,
            updated_by=get_owner_token(),
        )
    except TargetMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True})


# ============================================================
# GET /admin/api/production-achievement/permissions
# ============================================================


@production_achievement_admin_bp.route("/permissions", methods=["GET"])
@admin_required
def api_admin_get_permissions():
    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")
    try:
        rows = get_permissions()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response(rows)


# ============================================================
# PUT /admin/api/production-achievement/permissions/{user_identifier}
# ============================================================


@production_achievement_admin_bp.route(
    "/permissions/<user_identifier>", methods=["PUT"]
)
@admin_required
def api_admin_put_permission(user_identifier: str):
    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    flag = body.get("can_edit_targets")
    if not isinstance(flag, bool):
        return validation_error("必須提供 can_edit_targets (boolean)")

    try:
        upsert_permission(
            user_identifier=user_identifier,
            can_edit_targets=flag,
            granted_by=get_owner_token(),
        )
    except PermissionMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True})
