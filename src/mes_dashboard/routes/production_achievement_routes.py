# -*- coding: utf-8 -*-
"""Production Achievement Rate (生產達成率) API routes.

Endpoints (production-achievement-oracle-plan-source removes the 3
Excel-import/daily-plans endpoints previously listed here -- targets are now
sourced from Oracle MES_WIP_OUTPUTPLAN via
``services/production_achievement_plan_service.py``, injected as ``plan_map``
in ``GET /report``, business-rules.md PA-11):
  GET  /api/production-achievement/report
  GET  /api/production-achievement/report/meta
  GET  /api/production-achievement/filter-options
  GET  /api/production-achievement/targets
  PUT  /api/production-achievement/targets
  GET  /api/production-achievement/permissions/me
  GET  /admin/api/production-achievement/permissions
  PUT  /admin/api/production-achievement/permissions/{user_identifier}
  GET/PUT/DELETE /api/production-achievement/package-lf-map[/{raw}]     (D1)
  GET/PUT/DELETE /api/production-achievement/workcenter-merge-map[/{raw}] (D2)
  GET            /api/production-achievement/known-package-lf-values
  GET            /api/production-achievement/known-workcenter-groups

Per-endpoint MySQL-failure behavior (design.md): report/targets/package-lf-map/
workcenter-merge-map reads degrade (empty array / null values, HTTP 200,
never 500) when MySQL OPS is off/unreachable. Writes return 503
SERVICE_UNAVAILABLE in that case. All new tables' write endpoints are
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
from mes_dashboard.core.query_spool_store import (
    clear_spooled_df,
    get_spool_file_path,
    get_spool_metadata,
)
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
from mes_dashboard.services.production_achievement_plan_service import (
    get_oracle_plan_rows,
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
    WorkcenterMergeValidationError,
    delete_workcenter_merge,
    get_workcenter_merge_entries,
    upsert_workcenter_merge,
    validate_plan_source_side,
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
# 轉出 (moveout) source counterparts (PA-18) -- distinct spool namespace + job
# type, same RQ queue (the moveout worker registers on the shared queue).
_MOVEOUT_SPOOL_NAMESPACE = "production_achievement_moveout"
_MOVEOUT_JOB_TYPE = "production-achievement-moveout"
_VALID_SOURCES = ("output", "moveout")


def _resolve_source(raw: "str | None") -> str:
    """Return a validated data source ('output' default | 'moveout', PA-18).

    Raises ProductionAchievementValidationError on any other value so the route
    can surface it as a 400 (never silently coerce an unknown source to a
    default -- that would serve the wrong dataset).
    """
    source = (raw or "output").strip().lower()
    if source not in _VALID_SOURCES:
        raise ProductionAchievementValidationError(
            f"source 必須為 {' 或 '.join(_VALID_SOURCES)}"
        )
    return source


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

    ``refresh_plan=true`` independently bypasses the Oracle plan/target
    caches -- PA-11's CACHE_TTL_PRODUCTION_ACHIEVEMENT_PLAN for `plan_map`,
    AND PA-09's CACHE_TTL_PRODUCTION_ACHIEVEMENT_PACKAGE_LF_ORACLE for the
    Oracle default layer folded into `package_lf_map` (D1). Kept SEPARATE
    from `force_refresh` on purpose: `force_refresh=true` ALWAYS
    takes the 202 enqueue branch below (spool_path is forced to None), so it
    never itself reaches the plan_map computation in this same request --
    the frontend's tail re-fetch after the job completes is what actually
    lands on the 200 branch, and that tail request must NOT resend
    `force_refresh=true` (it would re-clear the spool the job just finished
    computing and re-enqueue forever). The frontend instead carries
    `refresh_plan=true` through that tail request specifically so 重新查詢
    never leaves 實際產出 fresh while the achievement-rate denominator stays
    stale (useProductionAchievement.ts `_fetchReport`/`_pollForCompletion`).
    A bare `force_refresh=true` also implies `refresh_plan=true` (covers any
    other caller that never reaches the 202 branch, e.g. a warm-cache path).
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    force_refresh = request.args.get("force_refresh", "").strip().lower() in ("1", "true", "yes", "on")
    refresh_plan = force_refresh or request.args.get("refresh_plan", "").strip().lower() in ("1", "true", "yes", "on")

    try:
        _validate_date_range(start_date, end_date)
        source = _resolve_source(request.args.get("source"))
    except ProductionAchievementValidationError as exc:
        return validation_error(str(exc))

    is_moveout = source == "moveout"
    spool_namespace = _MOVEOUT_SPOOL_NAMESPACE if is_moveout else _SPOOL_NAMESPACE
    job_type = _MOVEOUT_JOB_TYPE if is_moveout else _JOB_TYPE

    query_id = make_canonical_pa_spool_id(start_date, end_date, source=source)

    if force_refresh:
        clear_spooled_df(spool_namespace, query_id)

    # ── Spool-hit: 200, inline maps injected unconditionally (Q1, not
    # row-count gated like resource_history's threshold). 5 inline arrays
    # (data-shape-contract.md §3.28.4): +package_lf_map (D1),
    # +workcenter_merge_map (D2, now carries plan_source_side per PA-20),
    # +plan_map (Oracle-sourced, replaces the old daily_plan_map,
    # production-achievement-oracle-plan-source). ────────────────────────────
    spool_path = None if force_refresh else get_spool_file_path(spool_namespace, query_id)
    if spool_path is not None:
        try:
            # spec_workcenter_map (SPECNAME->workcenter_group) is only meaningful
            # for the 產出 source (its spool is SPECNAME-grain). The 轉出 spool is
            # already raw_workcenter_group-grain, so this map is an empty array in
            # moveout mode (PA-18) -- the client's moveout Stage-1 rollup does not
            # join it.
            spec_workcenter_map = [] if is_moveout else [
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
                for raw, merged in get_package_lf_map(force_refresh=refresh_plan).items()
            ]
            # PA-19/PA-20: carry parent_group + plan_source_side in the inline
            # array so the client can build the raw->子站 (D2 INNER JOIN), the
            # 子站->大項 (detail-table expansion), AND the 大項->input/output
            # plan-column routing mappings from one payload.
            workcenter_merge_map = [
                {
                    "raw_workcenter_group": e["raw_workcenter_group"],
                    "merged_workcenter_group": e["merged_workcenter_group"],
                    "parent_group": e["parent_group"],
                    "plan_source_side": e["plan_source_side"],
                }
                for e in get_workcenter_merge_entries()
            ]
            plan_map = get_oracle_plan_rows(start_date, end_date, force_refresh=refresh_plan)
        except Exception as exc:
            return internal_error(str(exc))

        # Freshness indicators (defensive against metadata being None -- should
        # not normally happen since get_spool_file_path() just confirmed a hit,
        # but Redis metadata could expire/evict between the two calls):
        #   sync_time            -- epoch seconds this spool last finished a
        #                            real Oracle sync (metadata "created_at").
        #   latest_data_timestamp -- "%Y-%m-%d %H:%M:%S" string of the newest
        #                            underlying TRACKOUTTIMESTAMP/TXNDATE row
        #                            in that sync (worker-computed
        #                            "latest_data_ts"), independent of DW ETL
        #                            replication lag from sync_time.
        spool_metadata = get_spool_metadata(spool_namespace, query_id)
        sync_time = spool_metadata.get("created_at") if spool_metadata else None
        latest_data_timestamp = spool_metadata.get("latest_data_ts") if spool_metadata else None

        return success_response({
            "query_id": query_id,
            "spool_download_url": f"/api/spool/{spool_namespace}/{query_id}.parquet",
            "source": source,
            "spec_workcenter_map": spec_workcenter_map,
            "targets_map": targets_map,
            "package_lf_map": package_lf_map,
            "workcenter_merge_map": workcenter_merge_map,
            "plan_map": plan_map,
            "sync_time": sync_time,
            "latest_data_timestamp": latest_data_timestamp,
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
    # Same flag gates both sources; moveout imports its own worker module.
    if _PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB:
        if is_moveout:
            import mes_dashboard.workers.production_achievement_moveout_worker  # noqa: F401
        else:
            import mes_dashboard.workers.production_achievement_worker  # noqa: F401

    # enqueue_job_dynamic spreads `params` into the RQ call kwargs as
    # {"job_id": ..., **params}; the worker entry is
    # execute_production_achievement[_moveout]_unified_job(job_id, params), so
    # the query params must be nested under a "params" key (mirrors
    # production_history's `params={"params": body}`) — a flat dict here would
    # spread start_date/end_date as unexpected top-level kwargs and raise
    # TypeError in the worker.
    job_id_result, err, status_hint = enqueue_query_job(
        job_type,
        owner=get_owner_token(),
        params={"params": {"start_date": start_date, "end_date": end_date}},
        sync_fallback_allowed=False,
    )
    if job_id_result is None:
        logger.warning(
            "production_achievement: async enqueue failed (source=%s hint=%s): %s",
            source, status_hint, err,
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
            "status_url": f"/api/job/{job_id_result}?prefix={job_type}",
        },
        status_code=202,
    )


# ============================================================
# GET /api/production-achievement/report/meta
# ============================================================


@production_achievement_bp.route("/report/meta", methods=["GET"])
@login_required
def api_get_report_meta():
    """Cheap freshness-only probe for what GET /report would otherwise serve.

    Returns just sync_time/latest_data_timestamp via a direct Redis metadata
    read (get_spool_file_path + get_spool_metadata) -- skips
    get_targets_map()/get_workcenter_merge_entries()'s uncached MySQL
    round-trips and plan_map's Oracle-backed lookup that GET /report's
    spool-hit branch always pays for. Built for frontend polling (
    production-achievement's metadata-gated auto-refresh, see
    frontend/src/shared-composables/useFreshnessGate.ts): a poll here that
    returns an unchanged sync_time skips the expensive GET /report re-fetch
    entirely.

    Same start_date/end_date/source contract as GET /report. Never enqueues
    a background job and never errors on a spool miss -- returns null
    fields (200) so a poll before the first warmup cycle completes is a
    normal, not exceptional, response.
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        _validate_date_range(start_date, end_date)
        source = _resolve_source(request.args.get("source"))
    except ProductionAchievementValidationError as exc:
        return validation_error(str(exc))

    is_moveout = source == "moveout"
    spool_namespace = _MOVEOUT_SPOOL_NAMESPACE if is_moveout else _SPOOL_NAMESPACE
    query_id = make_canonical_pa_spool_id(start_date, end_date, source=source)

    sync_time = None
    latest_data_timestamp = None
    if get_spool_file_path(spool_namespace, query_id) is not None:
        spool_metadata = get_spool_metadata(spool_namespace, query_id)
        sync_time = spool_metadata.get("created_at") if spool_metadata else None
        latest_data_timestamp = spool_metadata.get("latest_data_ts") if spool_metadata else None

    return success_response({
        "query_id": query_id,
        "source": source,
        "sync_time": sync_time,
        "latest_data_timestamp": latest_data_timestamp,
    })


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
# GET /api/production-achievement/permissions/me (self-check, any logged-in
# user -- lets the report page's frontend decide whether to route into
# /production-achievement-settings BEFORE navigating, instead of only
# discovering the answer via a 403 on the first write inside that page.
# Deliberately login_required only, NOT can_edit_targets-gated: a
# not-whitelisted user must still be able to ask "am I whitelisted?".
# ============================================================


@production_achievement_bp.route("/permissions/me", methods=["GET"])
@login_required
def api_get_own_permission():
    return success_response({"can_edit_targets": can_edit_targets()})


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
    # parent_group (PA-19) optional; defaults to merged (single-layer) in the
    # service when omitted/blank.
    parent_group = body.get("parent_group") or None

    if not raw_workcenter_group or not merged_workcenter_group:
        return validation_error("必須提供 raw_workcenter_group 和 merged_workcenter_group")

    # plan_source_side (PA-20) required, not defaulted -- always submitted
    # together with parent_group by WorkcenterMergeMappingPanel.vue so a 大項
    # reassignment can never silently leave a stale input/output routing.
    try:
        plan_source_side = validate_plan_source_side(body.get("plan_source_side"))
    except WorkcenterMergeValidationError as exc:
        return validation_error(str(exc))

    try:
        upsert_workcenter_merge(
            raw_workcenter_group=raw_workcenter_group,
            merged_workcenter_group=merged_workcenter_group,
            parent_group=parent_group,
            plan_source_side=plan_source_side,
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
