# -*- coding: utf-8 -*-
"""Async lineage job service for staged trace flows."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job,
    get_job_status as _get_job_status,
    update_job_progress,
)
from mes_dashboard.services.lineage_engine import LineageEngine

logger = logging.getLogger("mes_dashboard.trace_lineage_job_service")

TRACE_LINEAGE_QUEUE = os.getenv(
    "TRACE_LINEAGE_QUEUE",
    os.getenv("TRACE_WORKER_QUEUE", "trace-events"),
)
TRACE_LINEAGE_JOB_TIMEOUT_SECONDS = int(
    os.getenv(
        "TRACE_LINEAGE_JOB_TIMEOUT_SECONDS",
        os.getenv("TRACE_JOB_TIMEOUT_SECONDS", "1800"),
    )
)
TRACE_LINEAGE_JOB_TTL_SECONDS = int(
    os.getenv(
        "TRACE_LINEAGE_JOB_TTL_SECONDS",
        os.getenv("TRACE_JOB_TTL_SECONDS", "3600"),
    )
)

_JOB_PREFIX = "trace-lineage"
_PROFILE_QUERY_TOOL_REVERSE = "query_tool_reverse"
_PROFILE_MID_SECTION_DEFECT = "mid_section_defect"

_TRACE_LINEAGE_SPOOL_NS = "trace_lineage"


def _normalize_container_ids(container_ids: List[str]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for container_id in container_ids or []:
        value = str(container_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def make_trace_lineage_query_id(
    profile: str,
    container_ids: List[str],
    params: Optional[Dict[str, Any]] = None,
) -> str:
    normalized_ids = sorted(_normalize_container_ids(container_ids))
    identity: Dict[str, Any] = {
        "profile": str(profile or "").strip(),
        "container_ids": normalized_ids,
    }
    if str(profile or "").strip() == _PROFILE_MID_SECTION_DEFECT:
        direction = str((params or {}).get("direction") or "backward").strip()
        identity["direction"] = direction or "backward"

    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    safe_profile = str(profile or "lineage").strip().replace("_", "-") or "lineage"
    return f"trace-lineage-{safe_profile}-{digest}"[:128]


def load_trace_lineage_result(query_id: str) -> Optional[Dict[str, Any]]:
    """Load trace lineage result from spool-backed storage."""
    from mes_dashboard.core.query_spool_store import load_spooled_df
    try:
        df = load_spooled_df(_TRACE_LINEAGE_SPOOL_NS, query_id)
        if df is None or df.empty:
            return None
        json_str = df["payload"].iloc[0]
        payload = json.loads(json_str)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("trace lineage result load failed query_id=%s: %s", query_id, exc)
        return None


def _store_trace_lineage_result(query_id: str, payload: Dict[str, Any]) -> bool:
    """Store trace lineage result to spool-backed storage.

    Serializes the lineage graph as a single-row Parquet spool so Redis
    retains only job metadata and progress, not the full result body.
    """
    import pandas as pd
    from mes_dashboard.core.query_spool_store import store_spooled_df
    try:
        json_str = json.dumps(payload, ensure_ascii=False, default=str)
        df = pd.DataFrame({"payload": [json_str]})
        store_spooled_df(
            _TRACE_LINEAGE_SPOOL_NS,
            query_id,
            df,
            ttl_seconds=max(TRACE_LINEAGE_JOB_TTL_SECONDS, 60),
        )
        return True
    except Exception as exc:
        logger.warning("trace lineage result store failed query_id=%s: %s", query_id, exc)
        return False


def get_trace_lineage_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    return _get_job_status(_JOB_PREFIX, job_id)


def get_trace_lineage_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    status = get_trace_lineage_job_status(job_id)
    if status is None:
        return None
    query_id = str(status.get("query_id") or "").strip()
    if not query_id:
        return None
    return load_trace_lineage_result(query_id)


def enqueue_trace_lineage(
    *,
    profile: str,
    container_ids: List[str],
    owner: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    query_id = make_trace_lineage_query_id(profile, container_ids, params=params)
    job_id = f"trace-lineage-{uuid.uuid4().hex[:12]}"
    enqueued_job_id, error = enqueue_job(
        queue_name=TRACE_LINEAGE_QUEUE,
        worker_fn=_execute_trace_lineage_job,
        owner=owner,
        job_id=job_id,
        kwargs={
            "job_id": job_id,
            "profile": profile,
            "container_ids": list(container_ids or []),
            "params": dict(params or {}),
            "query_id": query_id,
        },
        prefix=_JOB_PREFIX,
        job_timeout=TRACE_LINEAGE_JOB_TIMEOUT_SECONDS,
        result_ttl=TRACE_LINEAGE_JOB_TTL_SECONDS,
    )
    if enqueued_job_id:
        update_job_progress(_JOB_PREFIX, enqueued_job_id, profile=profile)
    return enqueued_job_id, error, query_id


def _resolve_direction(profile: str, params: Optional[Dict[str, Any]]) -> str:
    if profile == _PROFILE_QUERY_TOOL_REVERSE:
        return "backward"
    if profile == _PROFILE_MID_SECTION_DEFECT:
        direction = str((params or {}).get("direction") or "backward").strip()
        return direction or "backward"
    return "forward"


def _build_backward_response(
    container_ids: List[str],
    reverse_graph: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_ancestors: Dict[str, List[str]] = {}
    all_nodes = set(container_ids)
    ancestors_raw = reverse_graph.get("ancestors", {}) if isinstance(reverse_graph, dict) else {}
    for seed in container_ids:
        raw_values = ancestors_raw.get(seed, set())
        values = raw_values if isinstance(raw_values, (set, list, tuple)) else []
        normalized = sorted({
            str(item).strip()
            for item in values
            if isinstance(item, str) and str(item).strip()
        })
        normalized_ancestors[seed] = normalized
        all_nodes.update(normalized)

    seed_set = set(container_ids)
    response: Dict[str, Any] = {
        "stage": "lineage",
        "roots": list(container_ids),
        "ancestors": normalized_ancestors,
        "merges": {},
        "total_nodes": len(all_nodes),
        "total_ancestor_count": len(all_nodes - seed_set),
        "parent_map": reverse_graph.get("parent_map", {}) if isinstance(reverse_graph, dict) else {},
        "merge_edges": reverse_graph.get("merge_edges", {}) if isinstance(reverse_graph, dict) else {},
        "nodes": reverse_graph.get("nodes", {}) if isinstance(reverse_graph, dict) else {},
        "edges": reverse_graph.get("edges", []) if isinstance(reverse_graph, dict) else [],
    }

    cid_to_name = reverse_graph.get("cid_to_name") if isinstance(reverse_graph, dict) else None
    if isinstance(cid_to_name, dict):
        response["names"] = {
            cid: name for cid, name in cid_to_name.items() if cid in all_nodes and name
        }

    seed_roots = reverse_graph.get("seed_roots") if isinstance(reverse_graph, dict) else None
    if isinstance(seed_roots, dict) and seed_roots:
        response["seed_roots"] = seed_roots

    return response


def _build_forward_response(forward_tree: Dict[str, Any]) -> Dict[str, Any]:
    cid_to_name = forward_tree.get("cid_to_name") or {}
    return {
        "stage": "lineage",
        "roots": forward_tree.get("roots", []),
        "children_map": forward_tree.get("children_map", {}),
        "leaf_serials": forward_tree.get("leaf_serials", {}),
        "names": {cid: name for cid, name in cid_to_name.items() if name},
        "total_nodes": forward_tree.get("total_nodes", 0),
        "nodes": forward_tree.get("nodes", {}),
        "edges": forward_tree.get("edges", []),
    }


def _execute_trace_lineage_job(
    *,
    job_id: str,
    profile: str,
    container_ids: List[str],
    params: Optional[Dict[str, Any]] = None,
    query_id: str,
) -> None:
    from mes_dashboard.rq_worker_preload import ensure_rq_logging

    ensure_rq_logging()
    normalized_ids = _normalize_container_ids(container_ids)
    if not normalized_ids:
        complete_job(_JOB_PREFIX, job_id, error="no container_ids provided")
        return

    update_job_progress(
        _JOB_PREFIX,
        job_id,
        status="running",
        stage="lineage",
        progress="resolving lineage",
        pct="10",
    )

    direction = _resolve_direction(profile, params)
    try:
        started = time.monotonic()
        if direction == "backward":
            result = LineageEngine.resolve_full_genealogy(normalized_ids)
            response = _build_backward_response(normalized_ids, result)
        else:
            result = LineageEngine.resolve_forward_tree(normalized_ids)
            response = _build_forward_response(result)

        update_job_progress(
            _JOB_PREFIX,
            job_id,
            status="running",
            stage="lineage",
            progress="storing result",
            pct="90",
            completed_stages="lineage",
        )
        if not _store_trace_lineage_result(query_id, response):
            complete_job(_JOB_PREFIX, job_id, error="failed to store lineage result")
            return

        complete_job(_JOB_PREFIX, job_id, query_id=query_id)
        logger.info(
            "trace lineage job completed job_id=%s query_id=%s profile=%s seeds=%s elapsed=%.2fs",
            job_id,
            query_id,
            profile,
            len(normalized_ids),
            time.monotonic() - started,
        )
    except Exception as exc:
        logger.error("trace lineage job failed job_id=%s: %s", job_id, exc, exc_info=True)
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Central job registry — job-registry-central
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="trace-lineage",
    queue_name="trace-events",
    worker_fn=_execute_trace_lineage_job,
))
