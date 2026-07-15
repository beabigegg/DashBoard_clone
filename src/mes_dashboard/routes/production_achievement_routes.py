# -*- coding: utf-8 -*-
"""Production Achievement Rate (生產達成率) API routes.

Endpoints per api-contract.md rows 256-261 and 273-282 (production-achievement-
overhaul adds 10 new rows):
  GET  /api/production-achievement/report
  GET  /api/production-achievement/filter-options
  GET  /api/production-achievement/targets
  PUT  /api/production-achievement/targets
  GET  /admin/api/production-achievement/permissions
  PUT  /admin/api/production-achievement/permissions/{user_identifier}
  GET/PUT/DELETE /api/production-achievement/package-lf-map[/{raw}]     (D1)
  GET/PUT/DELETE /api/production-achievement/workcenter-merge-map[/{raw}] (D2)
  GET/PUT        /api/production-achievement/daily-plans
  POST           /api/production-achievement/daily-plans/import/preview
  POST           /api/production-achievement/daily-plans/import/confirm
  GET            /api/production-achievement/known-package-lf-values
  GET            /api/production-achievement/known-workcenter-groups

Per-endpoint MySQL-failure behavior (design.md): report/targets/package-lf-map/
workcenter-merge-map/daily-plans reads degrade (empty array / null values,
HTTP 200, never 500) when MySQL OPS is off/unreachable. Writes return 503
SERVICE_UNAVAILABLE in that case. All 3 new tables' write endpoints are
gated by the SAME verbatim can_edit_targets permission (widened scope, no
new permission system) -- 403 FORBIDDEN when not whitelisted.
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
from mes_dashboard.core.query_spool_store import clear_spooled_df, get_spool_file_path
from mes_dashboard.core.response import (
    SERVICE_UNAVAILABLE,
    error_response,
    forbidden_error,
    internal_error,
    not_found_error,
    service_unavailable_error,
    success_response,
    validation_error,
)
from mes_dashboard.services.async_query_job_service import (
    enqueue_query_job,
    is_async_available,
)
from mes_dashboard.services.filter_cache import (
    get_known_package_lf_values,
    get_spec_workcenter_mapping,
)
from mes_dashboard.services.production_achievement_daily_plan_service import (
    DailyPlanValidationError,
    MySQLUnavailableError as DailyPlanMySQLUnavailableError,
    bulk_upsert_daily_plans,
    get_daily_plans,
    get_daily_plans_map,
    upsert_daily_plan,
    validate_daily_plan_qty,
)
from mes_dashboard.services.production_achievement_import_service import (
    ImportParseError,
    categorize_import_rows,
    parse_pjmes052_workbook,
)
from mes_dashboard.services.production_achievement_package_lf_service import (
    MySQLUnavailableError as PackageLfMySQLUnavailableError,
    delete_package_lf,
    get_package_lf_entries,
    get_package_lf_map,
    upsert_package_lf,
)
from mes_dashboard.services.production_achievement_permission_service import (
    MySQLUnavailableError as PermissionMySQLUnavailableError,
    get_permissions,
    upsert_permission,
)
from mes_dashboard.services.production_achievement_service import (
    ProductionAchievementValidationError,
    _validate_date_range,
    get_filter_options,
    get_known_workcenter_groups,
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
from mes_dashboard.services.production_achievement_workcenter_merge_service import (
    MySQLUnavailableError as WorkcenterMergeMySQLUnavailableError,
    delete_workcenter_merge,
    get_workcenter_merge_entries,
    get_workcenter_merge_map,
    upsert_workcenter_merge,
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

    ``force_refresh=true`` (manual 重新查詢 button, 當日/前日/當月 tabs):
    unconditionally discards any existing spool for this exact query_id
    BEFORE the hit check below, so the request always falls through to the
    enqueue branch and re-fetches Oracle -- the root-cause fix for
    production_achievement_daily_cache.py's staleness window still leaves a
    gap between scheduled warmup cycles; this gives the user an explicit
    "I don't trust the cached snapshot right now" escape hatch instead of
    waiting for the next cycle.
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    force_refresh = request.args.get("force_refresh", "").strip().lower() in ("1", "true", "yes", "on")

    try:
        _validate_date_range(start_date, end_date)
    except ProductionAchievementValidationError as exc:
        return validation_error(str(exc))

    query_id = make_canonical_pa_spool_id(start_date, end_date)

    if force_refresh:
        clear_spooled_df(_SPOOL_NAMESPACE, query_id)

    # ── Spool-hit: 200, inline maps injected unconditionally (Q1, not
    # row-count gated like resource_history's threshold). Grows from 2 to 5
    # inline arrays by production-achievement-overhaul (data-shape-contract.md
    # §3.28.4): +package_lf_map (D1), +workcenter_merge_map (D2),
    # +daily_plan_map. ─────────────────────────────────────────────────────
    spool_path = None if force_refresh else get_spool_file_path(_SPOOL_NAMESPACE, query_id)
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
            package_lf_map = [
                {"raw_package_lf": raw, "merged_group": merged}
                for raw, merged in get_package_lf_map().items()
            ]
            workcenter_merge_map = [
                {"raw_workcenter_group": raw, "merged_workcenter_group": merged}
                for raw, merged in get_workcenter_merge_map().items()
            ]
            daily_plan_map = [
                {"workcenter_group": wg, "package_lf_group": plg, "daily_plan_qty": qty}
                for (wg, plg), qty in get_daily_plans_map().items()
            ]
        except Exception as exc:
            return internal_error(str(exc))

        return success_response({
            "query_id": query_id,
            "spool_download_url": f"/api/spool/{_SPOOL_NAMESPACE}/{query_id}.parquet",
            "spec_workcenter_map": spec_workcenter_map,
            "targets_map": targets_map,
            "package_lf_map": package_lf_map,
            "workcenter_merge_map": workcenter_merge_map,
            "daily_plan_map": daily_plan_map,
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


# ============================================================
# GET/PUT/DELETE /api/production-achievement/package-lf-map[/{raw}] (D1)
# ============================================================


@production_achievement_bp.route("/package-lf-map", methods=["GET"])
@login_required
def api_get_package_lf_map():
    try:
        rows = get_package_lf_entries()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response(rows)


@production_achievement_bp.route("/package-lf-map", methods=["PUT"])
@login_required
def api_put_package_lf_map():
    if not can_edit_targets():
        return forbidden_error("無權限編輯 PACKAGE_LF 對應表")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    raw_package_lf = body.get("raw_package_lf")
    merged_group = body.get("merged_group")

    if not raw_package_lf or not merged_group:
        return validation_error("必須提供 raw_package_lf 和 merged_group")

    try:
        upsert_package_lf(
            raw_package_lf=raw_package_lf,
            merged_group=merged_group,
            updated_by=get_owner_token(),
        )
    except PackageLfMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True})


@production_achievement_bp.route("/package-lf-map/<raw>", methods=["DELETE"])
@login_required
def api_delete_package_lf_map(raw: str):
    if not can_edit_targets():
        return forbidden_error("無權限編輯 PACKAGE_LF 對應表")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    try:
        deleted = delete_package_lf(raw_package_lf=raw)
    except PackageLfMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    if not deleted:
        return not_found_error("找不到指定的 raw_package_lf")

    return success_response({"acknowledged": True})


# ============================================================
# GET/PUT/DELETE /api/production-achievement/workcenter-merge-map[/{raw}] (D2)
# ============================================================


@production_achievement_bp.route("/workcenter-merge-map", methods=["GET"])
@login_required
def api_get_workcenter_merge_map():
    try:
        rows = get_workcenter_merge_entries()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response(rows)


@production_achievement_bp.route("/workcenter-merge-map", methods=["PUT"])
@login_required
def api_put_workcenter_merge_map():
    if not can_edit_targets():
        return forbidden_error("無權限編輯站點合併對應表")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    raw_workcenter_group = body.get("raw_workcenter_group")
    merged_workcenter_group = body.get("merged_workcenter_group")

    if not raw_workcenter_group or not merged_workcenter_group:
        return validation_error("必須提供 raw_workcenter_group 和 merged_workcenter_group")

    try:
        upsert_workcenter_merge(
            raw_workcenter_group=raw_workcenter_group,
            merged_workcenter_group=merged_workcenter_group,
            updated_by=get_owner_token(),
        )
    except WorkcenterMergeMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True})


@production_achievement_bp.route("/workcenter-merge-map/<raw>", methods=["DELETE"])
@login_required
def api_delete_workcenter_merge_map(raw: str):
    if not can_edit_targets():
        return forbidden_error("無權限編輯站點合併對應表")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    try:
        deleted = delete_workcenter_merge(raw_workcenter_group=raw)
    except WorkcenterMergeMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    if not deleted:
        return not_found_error("找不到指定的 raw_workcenter_group")

    return success_response({"acknowledged": True})


# ============================================================
# GET/PUT /api/production-achievement/daily-plans
# ============================================================


@production_achievement_bp.route("/daily-plans", methods=["GET"])
@login_required
def api_get_daily_plans():
    try:
        rows = get_daily_plans()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response(rows)


@production_achievement_bp.route("/daily-plans", methods=["PUT"])
@login_required
def api_put_daily_plans():
    if not can_edit_targets():
        return forbidden_error("無權限編輯每日計畫")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    workcenter_group = body.get("workcenter_group")
    package_lf_group = body.get("package_lf_group")
    daily_plan_qty = body.get("daily_plan_qty")

    if not workcenter_group or not package_lf_group:
        return validation_error("必須提供 workcenter_group 和 package_lf_group")

    try:
        validated_qty = validate_daily_plan_qty(daily_plan_qty)
    except DailyPlanValidationError as exc:
        return validation_error(str(exc))

    try:
        upsert_daily_plan(
            workcenter_group=workcenter_group,
            package_lf_group=package_lf_group,
            daily_plan_qty=validated_qty,
            updated_by=get_owner_token(),
        )
    except DailyPlanMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True})


# ============================================================
# POST /api/production-achievement/daily-plans/import/preview
# POST /api/production-achievement/daily-plans/import/confirm
# (Excel-import for 每日計畫量設定, business-rules.md PA-16)
# ============================================================


@production_achievement_bp.route("/daily-plans/import/preview", methods=["POST"])
@login_required
def api_post_daily_plans_import_preview():
    if not can_edit_targets():
        return forbidden_error("無權限編輯每日計畫")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return validation_error("必須提供檔案")
    if not uploaded.filename.lower().endswith(".xlsx"):
        return validation_error("僅支援 .xlsx 檔案")

    try:
        parsed_rows = parse_pjmes052_workbook(uploaded.stream)
    except ImportParseError as exc:
        return validation_error(f"無法解析檔案：{exc}")
    except Exception as exc:
        return internal_error(str(exc))

    try:
        legal_workcenter_groups = set(get_workcenter_merge_map().values())
        legal_package_lf_map = get_package_lf_map()
        legal_package_lf_groups = set(legal_package_lf_map.values()) | (
            set(get_known_package_lf_values()) - set(legal_package_lf_map.keys())
        )
        preview = categorize_import_rows(
            parsed_rows,
            legal_workcenter_groups=legal_workcenter_groups,
            legal_package_lf_groups=legal_package_lf_groups,
            current_plans=get_daily_plans_map(),
        )
    except Exception as exc:
        return internal_error(str(exc))

    return success_response(preview)


@production_achievement_bp.route("/daily-plans/import/confirm", methods=["POST"])
@login_required
def api_post_daily_plans_import_confirm():
    if not can_edit_targets():
        return forbidden_error("無權限編輯每日計畫")

    if not MYSQL_OPS_ENABLED:
        return service_unavailable_error("MySQL OPS 未啟用")

    body = request.get_json(silent=True) or {}
    submitted_rows = body.get("rows")
    if not isinstance(submitted_rows, list) or not submitted_rows:
        return validation_error("必須提供 rows（至少一筆）")

    try:
        legal_workcenter_groups = set(get_workcenter_merge_map().values())
        legal_package_lf_map = get_package_lf_map()
        legal_package_lf_groups = set(legal_package_lf_map.values()) | (
            set(get_known_package_lf_values()) - set(legal_package_lf_map.keys())
        )
    except Exception as exc:
        return internal_error(str(exc))

    # Never trust the client's own preview categorization -- re-validate
    # every row server-side; reject the WHOLE batch on any failure so
    # confirm's result is unambiguous (never a partial import).
    validated_rows = []
    for row in submitted_rows:
        if not isinstance(row, dict):
            return validation_error("rows 格式錯誤")
        workcenter_group = row.get("workcenter_group")
        package_lf_group = row.get("package_lf_group")
        if not workcenter_group or not package_lf_group:
            return validation_error("每筆 row 必須提供 workcenter_group 和 package_lf_group")
        if workcenter_group not in legal_workcenter_groups:
            return validation_error(f"站點群組「{workcenter_group}」不在系統合法清單中")
        if package_lf_group not in legal_package_lf_groups:
            return validation_error(f"Package「{package_lf_group}」無法對應到現有 package_lf_group")
        try:
            validated_qty = validate_daily_plan_qty(row.get("daily_plan_qty"))
        except DailyPlanValidationError as exc:
            return validation_error(str(exc))
        validated_rows.append({
            "workcenter_group": workcenter_group,
            "package_lf_group": package_lf_group,
            "daily_plan_qty": validated_qty,
        })

    try:
        upserted = bulk_upsert_daily_plans(validated_rows, updated_by=get_owner_token())
    except DailyPlanMySQLUnavailableError as exc:
        return service_unavailable_error(str(exc))
    except Exception as exc:
        return internal_error(str(exc))

    return success_response({"acknowledged": True, "upserted": upserted})


# ============================================================
# GET /api/production-achievement/known-package-lf-values
# ============================================================


@production_achievement_bp.route("/known-package-lf-values", methods=["GET"])
@login_required
def api_get_known_package_lf_values():
    try:
        values = get_known_package_lf_values()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response({"package_lf_values": values})


# ============================================================
# GET /api/production-achievement/known-workcenter-groups (OD-8)
# ============================================================


@production_achievement_bp.route("/known-workcenter-groups", methods=["GET"])
@login_required
def api_get_known_workcenter_groups():
    try:
        groups = get_known_workcenter_groups()
    except Exception as exc:
        return internal_error(str(exc))
    return success_response({"raw_workcenter_groups": groups})
