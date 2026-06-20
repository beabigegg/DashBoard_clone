# -*- coding: utf-8 -*-
"""WIP detail async job service.

Bridges WIP detail primary queries to the RQ background worker.

Public API:
  execute_wip_detail_job(*, job_id, owner, **query_params)  <- RQ worker entry point
  enqueue_wip_detail_query(params: dict, owner: str) -> (job_id, err)
  execute_wip_detail_oracle_query(**query_params) -> dict

Design decisions (wip-rq-worker-chunks-cleanup):
  D1: No routing flag — routing is gated solely by is_async_available() +
      classify_query_cost(domain="wip", ...) in wip_routes.py.
  D2: heavy_query_slot wraps only the Oracle phase (pct 15→90). No nullcontext()
      guard — slot is unconditional inside the worker (no flag to guard on).
  D3: Per-query spool (namespace wip_dataset). No warmup-superset reuse.
      Each distinct filter set is its own spool key.
  D5: Coarse-bracket milestones: 5 (start) → 15 (Oracle) → 90 (spool) → 100 (done).
  D6: register_job_type at module bottom; app.py import is deferred (inert until
      activation per ci-gates.md Promotion Policy).

AC-7 (resolved): Column assembly layer (_ORACLE_TO_CAMEL + wipStatus) applied before
  writing to parquet so async spool columns match the sync API camelCase shape.
  Summary fields (totalLots, etc.) must still be recomputed from parquet rows at
  async-result serve time.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mes_dashboard.core.global_concurrency import heavy_query_slot
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job_dynamic,
    update_job_progress,
)

logger = logging.getLogger("mes_dashboard.wip_query_job_service")

# ---------------------------------------------------------------------------
# Configuration — all frozen at import time; tests must use monkeypatch.setattr
# ---------------------------------------------------------------------------

WIP_WORKER_QUEUE: str = os.getenv("WIP_WORKER_QUEUE", "wip-detail-query")

WIP_JOB_TIMEOUT_SECONDS: int = int(os.getenv("WIP_JOB_TIMEOUT_SECONDS", "1800"))

WIP_SPOOL_TTL: int = int(os.getenv("WIP_SPOOL_TTL", "72000"))

# Prefix used for Redis meta keys: wip-detail:job:{job_id}:meta
_JOB_PREFIX = "wip-detail"

# Spool namespace for parquet result files
_SPOOL_NAMESPACE = "wip_dataset"

# ---------------------------------------------------------------------------
# Oracle column → camelCase key mapping (AC-7 assembly layer)
# Mirrors the key names used by the sync get_wip_detail/_assemble_lot_dict path.
# Applied to lots_df before writing to parquet so async spool columns match sync API.
# ---------------------------------------------------------------------------
_ORACLE_TO_CAMEL: dict = {
    "LOTID": "lotId",
    "WORKORDER": "workorder",
    "QTY": "qty",
    "QTY2": "qty2",
    "STATUS": "status",
    "HOLDREASONNAME": "holdReason",
    "CURRENTHOLDCOUNT": "holdCount",
    "OWNER": "owner",
    "STARTDATE": "startDate",
    "UTS": "uts",
    "PRODUCT": "product",
    "PRODUCTLINENAME": "productLine",
    "PACKAGE_LEF": "packageLef",
    "PJ_FUNCTION": "pjFunction",
    "PJ_TYPE": "pjType",
    "BOP": "bop",
    "FIRSTNAME": "waferLotId",
    "WAFERNAME": "waferPn",
    "WAFERLOT": "waferLotPrefix",
    "SPECNAME": "spec",
    "SPECSEQUENCE": "specSequence",
    "WORKCENTERNAME": "workcenter",
    "WORKCENTERSEQUENCE": "workcenterSequence",
    "WORKCENTER_GROUP": "workcenterGroup",
    "WORKCENTER_SHORT": "workcenterShort",
    "AGEBYDAYS": "ageByDays",
    "EQUIPMENTS": "equipment",
    "EQUIPMENTCOUNT": "equipmentCount",
    "WORKFLOWNAME": "workflow",
    "DATECODE": "dateCode",
    "LEADFRAMENAME": "leadframeName",
    "LEADFRAMEOPTION": "leadframeOption",
    "LEADFRAMEDESC": "leadframeDesc",
    "COMNAME": "compoundName",
    "WAFERDESC": "waferDesc",
    "LOCATIONNAME": "location",
    "EVENTNAME": "ncrId",
    "OCCURRENCEDATE": "ncrDate",
    "RELEASETIME": "releaseTime",
    "RELEASEEMP": "releaseEmp",
    "RELEASEREASON": "releaseComment",
    "COMMENT_HOLD": "holdComment",
    "CONTAINERCOMMENTS": "comment",
    "COMMENT_DATE": "commentDate",
    "COMMENT_EMP": "commentEmp",
    "COMMENT_FUTURE": "futureHoldComment",
    "HOLDEMP": "holdEmp",
    "DEPTNAME": "holdDept",
    "PJ_PRODUCEREGION": "produceRegion",
    "PRIORITYCODENAME": "priority",
    "TMTT_R": "tmttRemaining",
    "WAFER_FACTOR": "dieConsumption",
    "SYS_DATE": "dataUpdateDate",
}


def _compute_wip_status(equipment_count: int, hold_count: int) -> str:
    """Derive wipStatus from raw Oracle EQUIPMENTCOUNT / CURRENTHOLDCOUNT."""
    if equipment_count > 0:
        return "RUN"
    if hold_count > 0:
        return "HOLD"
    return "QUEUE"


# ---------------------------------------------------------------------------
# Oracle query helper (wrapped by the worker; sync path unchanged)
# ---------------------------------------------------------------------------

def execute_wip_detail_oracle_query(**query_params: Any) -> dict:
    """Run the full WIP detail Oracle query and materialise a parquet spool.

    Called ONLY from inside execute_wip_detail_job, within the heavy_query_slot.
    The sync get_wip_detail() (paged dict) is NOT called here — this function
    issues the full unpaged Oracle query and writes raw lot rows to a parquet file.

    Returns:
        dict with keys:
          query_id (str)   — canonical spool key (SHA256 hash of filter params)
          spool_path (str | None) — absolute path of the written parquet, or None on error
          row_count (int)  — number of rows written
    """
    import pandas as pd

    from mes_dashboard.services.batch_query_engine import compute_query_hash
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR, register_spool_file
    from mes_dashboard.services.wip_service import (
        _build_base_conditions_builder,
        _add_exact_filter_conditions,
        _add_hold_type_conditions,
    )
    from mes_dashboard.core.database import read_sql_df
    from mes_dashboard.sql import SQLLoader

    # Extract filter params
    workcenter = query_params.get("workcenter", "")
    package = query_params.get("package")
    pj_type = query_params.get("pj_type")
    firstname = query_params.get("firstname")
    waferdesc = query_params.get("waferdesc")
    status = query_params.get("status")
    hold_type = query_params.get("hold_type")
    workorder = query_params.get("workorder")
    lotid = query_params.get("lotid")
    include_dummy = query_params.get("include_dummy", False)
    workflow = query_params.get("workflow", "")
    bop = query_params.get("bop", "")
    pj_function = query_params.get("pj_function", "")

    # Build canonical query_id from the filter set (no page/page_size — always full)
    canonical_params = {
        "workcenter": workcenter,
        "package": package,
        "pj_type": pj_type,
        "firstname": firstname,
        "waferdesc": waferdesc,
        "status": status,
        "hold_type": hold_type,
        "workorder": workorder,
        "lotid": lotid,
        "include_dummy": include_dummy,
        "workflow": workflow,
        "bop": bop,
        "pj_function": pj_function,
    }
    query_id = compute_query_hash(canonical_params)

    # Build WHERE conditions (mirrors _get_wip_detail_from_oracle)
    builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
    builder.add_param_condition("WORKCENTER_GROUP", workcenter)

    _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
    _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
    _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
    _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)
    _add_exact_filter_conditions(builder, "WORKFLOWNAME", workflow)
    _add_exact_filter_conditions(builder, "BOP", bop)
    _add_exact_filter_conditions(builder, "PJ_FUNCTION", pj_function)

    if status:
        status_upper = status.upper()
        if status_upper == "RUN":
            builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) > 0")
        elif status_upper == "HOLD":
            builder.add_condition(
                "COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0"
            )
            if hold_type:
                _add_hold_type_conditions(builder, hold_type)
        elif status_upper == "QUEUE":
            builder.add_condition(
                "COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0"
            )

    where_clause, params = builder.build_where_only()

    # Run the full (unpaged) detail SQL — same SQL file as sync path, no OFFSET/ROWNUM
    base_detail_sql = SQLLoader.load("wip/detail")
    # Replace pagination template: no OFFSET/LIMIT for async full-scan
    # The SQL template has {{ WHERE_CLAUSE }} and uses :offset/:limit bind vars
    detail_sql = base_detail_sql.replace("{{ WHERE_CLAUSE }}", where_clause)
    # Remove pagination constraints for async full-scan
    # Supply large limit to get all rows (Oracle ROWNUM semantics)
    detail_params = params.copy()
    detail_params["offset"] = 0
    detail_params["limit"] = 10_000_000  # effectively unbounded

    lots_df = read_sql_df(
        detail_sql,
        detail_params,
        caller="wip_query_job_service:execute_wip_detail_oracle_query",
    )

    if lots_df is None:
        lots_df = pd.DataFrame()

    row_count = len(lots_df)

    if row_count == 0:
        return {"query_id": query_id, "spool_path": None, "row_count": 0}

    # AC-7 assembly layer: compute wipStatus + rename Oracle columns → camelCase
    # before writing to parquet so async spool schema matches the sync API shape.
    lots_df["wipStatus"] = lots_df.apply(
        lambda r: _compute_wip_status(
            int(r.get("EQUIPMENTCOUNT") or 0),
            int(r.get("CURRENTHOLDCOUNT") or 0),
        ),
        axis=1,
    )
    lots_df = lots_df.rename(columns=_ORACLE_TO_CAMEL)

    # Write parquet spool to a temp file then register
    spool_dir = QUERY_SPOOL_DIR
    spool_dir_resolved = spool_dir if isinstance(spool_dir, Path) else Path(str(spool_dir))
    spool_dir_resolved.mkdir(parents=True, exist_ok=True)

    tmp_path = spool_dir_resolved / f"wip_dataset_{query_id}.parquet.tmp"
    try:
        lots_df.to_parquet(str(tmp_path), index=False, engine="pyarrow")
        registered = register_spool_file(
            _SPOOL_NAMESPACE,
            query_id,
            tmp_path,
            row_count,
            ttl_seconds=WIP_SPOOL_TTL,
        )
        if registered:
            logger.info(
                "wip_query_job_service: spool written query_id=%s rows=%d",
                query_id,
                row_count,
            )
        else:
            logger.warning(
                "wip_query_job_service: register_spool_file returned False (Redis unavailable?) "
                "query_id=%s",
                query_id,
            )
    except Exception as exc:
        logger.error(
            "wip_query_job_service: spool write failed query_id=%s: %s", query_id, exc
        )
        # Clean up temp file on failure
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {"query_id": query_id, "spool_path": None, "row_count": 0}

    return {
        "query_id": query_id,
        "spool_path": str(tmp_path),
        "row_count": row_count,
    }


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------

def enqueue_wip_detail_query(params: dict, owner: str):
    """Enqueue a WIP detail primary query to the RQ worker.

    Delegates to enqueue_job_dynamic("wip-detail", ...) which picks up the
    JobTypeConfig registered at module bottom.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    return enqueue_job_dynamic(
        "wip-detail",
        owner=owner,
        params=params,
    )


# ---------------------------------------------------------------------------
# RQ worker entry point
# ---------------------------------------------------------------------------

def execute_wip_detail_job(*, job_id: str, owner: str, **query_params: Any) -> None:
    """RQ worker entry point: execute WIP detail primary query and spool result.

    Runs in the dedicated wip-detail worker process — outside Gunicorn —
    with its own DB connections and memory space.

    Milestone implementation: coarse bracket (D5 — lowest risk).
    execute_wip_detail_oracle_query() runs the full Oracle query and writes the
    parquet spool. It is wrapped unmodified (no progress_callback injection).

      5   = starting  (job received, Oracle not yet issued)
      15  = querying  (about to call Oracle)
      90  = returned  (Oracle returned, about to complete)
      100 = complete  (spool written, job marked done)

    Design notes:
      - AC-4: heavy_query_slot wraps Oracle phase only (pct 15→90); slot is
        unconditional — D1 introduces no routing flag, so no nullcontext() guard.
      - D3: spool write and complete_job are OUTSIDE the slot.
      - D2: one slot per job (no fan-out; WIP detail is a single primary query).
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    logger.info("wip-detail job started job_id=%s owner=%s", job_id, owner)
    update_job_progress(
        _JOB_PREFIX, job_id,
        status="started", progress="initializing", pct=5, stage="starting",
    )

    try:
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="querying Oracle", pct=15, stage="querying",
        )

        # Wrap execute_wip_detail_oracle_query with heavy_query_slot (D2).
        # Slot acquired unconditionally — no flag guard (D1 / D2 rejected alternative).
        # complete_job and spool write are OUTSIDE the slot (D3 / AC-4).
        _slot_owner = f"wip-detail:{job_id}"
        with heavy_query_slot(_slot_owner):
            result = execute_wip_detail_oracle_query(**query_params)

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="finalizing", pct=90, stage="finalizing",
        )

        query_id = result["query_id"]

        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running", progress="complete", pct=100, stage="complete",
        )
        complete_job(_JOB_PREFIX, job_id, query_id=query_id)

    except Exception as exc:
        logger.error(
            "wip-detail job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — register at import time (D6)
#
# NOTE: This module is NOT imported in app.py in this change (worker ships
# inert). See ci-gates.md §Promotion Policy for the activation sequence.
# Activation = add the import line below to app.py alongside sibling workers:
#
#   import mes_dashboard.services.wip_query_job_service  # noqa: F401
#
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="wip-detail",
    queue_name=WIP_WORKER_QUEUE,
    worker_fn=execute_wip_detail_job,
    timeout_seconds=WIP_JOB_TIMEOUT_SECONDS,
    ttl_seconds=WIP_SPOOL_TTL,
    always_async=False,
))
