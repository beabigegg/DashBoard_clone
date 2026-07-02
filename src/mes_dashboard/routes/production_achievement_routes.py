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

from flask import Blueprint, request

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
from mes_dashboard.core.permissions import (
    admin_required,
    can_edit_targets,
    get_owner_token,
    login_required,
    targets_edit_required,
)
from mes_dashboard.core.response import (
    forbidden_error,
    internal_error,
    service_unavailable_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.production_achievement_permission_service import (
    MySQLUnavailableError as PermissionMySQLUnavailableError,
    get_permissions,
    upsert_permission,
)
from mes_dashboard.services.production_achievement_service import (
    ProductionAchievementValidationError,
    get_achievement_report,
    get_filter_options,
)
from mes_dashboard.services.production_achievement_target_service import (
    MySQLUnavailableError as TargetMySQLUnavailableError,
    TargetValidationError,
    get_targets,
    upsert_target,
    validate_target_qty,
)

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


# ============================================================
# GET /api/production-achievement/report
# ============================================================


@production_achievement_bp.route("/report", methods=["GET"])
@login_required
def api_get_report():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    shift_code = request.args.get("shift_code") or None
    workcenter_group = request.args.get("workcenter_group") or None

    try:
        rows = get_achievement_report(
            start_date=start_date,
            end_date=end_date,
            shift_code=shift_code,
            workcenter_group=workcenter_group,
        )
    except ProductionAchievementValidationError as exc:
        return validation_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response(rows)


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
