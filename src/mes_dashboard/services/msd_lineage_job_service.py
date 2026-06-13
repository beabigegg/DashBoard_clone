# -*- coding: utf-8 -*-
"""Async job service for MSD lineage resolution.

Handles large-scale lineage queries by decomposing seeds into batches,
running them in an RQ worker, and spooling results to parquet.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mes_dashboard.core.query_spool_store import load_spooled_df, store_spooled_df
from mes_dashboard.services.async_query_job_service import (
    complete_job,
    enqueue_job,
    get_job_status as _get_job_status,
    update_job_progress,
)
from mes_dashboard.services.lineage_engine import (
    ORACLE_IN_BATCH_SIZE,
    LineageEngine,
    MAX_SPLIT_DEPTH,
    _normalize_list,
    _safe_str,
)

logger = logging.getLogger("mes_dashboard.msd_lineage_job_service")

MSD_LINEAGE_QUEUE = os.getenv("MSD_WORKER_QUEUE", "msd-analysis")
MSD_LINEAGE_JOB_TIMEOUT_SECONDS = int(os.getenv("MSD_LINEAGE_JOB_TIMEOUT_SECONDS", "1800"))
MSD_LINEAGE_JOB_TTL_SECONDS = int(os.getenv("MSD_JOB_TTL_SECONDS", "3600"))

_JOB_PREFIX = "msd-lineage"
_SPOOL_NAMESPACE = "msd-lineage"


def enqueue_msd_lineage(
    *,
    container_ids: List[str],
    owner: str,
    direction: str = "backward",
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue a lineage resolution job to the MSD RQ worker.

    Args:
        owner: Caller identity from the Flask session (see get_owner_token).

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    job_id = f"msd-lineage-{uuid.uuid4().hex[:12]}"
    return enqueue_job(
        queue_name=MSD_LINEAGE_QUEUE,
        worker_fn=_execute_msd_lineage_job,
        owner=owner,
        job_id=job_id,
        kwargs={
            "job_id": job_id,
            "container_ids": list(container_ids),
            "direction": direction,
        },
        prefix=_JOB_PREFIX,
        job_timeout=MSD_LINEAGE_JOB_TIMEOUT_SECONDS,
        result_ttl=MSD_LINEAGE_JOB_TTL_SECONDS,
    )


def get_msd_lineage_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Return job status dict from Redis, or None if not found."""
    return _get_job_status(_JOB_PREFIX, job_id)


def get_msd_lineage_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    """Load lineage result from parquet spool and reconstruct response format.

    Returns a dict compatible with the sync /lineage response format.
    """
    status = get_msd_lineage_job_status(job_id)
    if status is None:
        return None
    query_id = status.get("query_id")
    if not query_id:
        return None

    df = load_spooled_df(_SPOOL_NAMESPACE, str(query_id))
    if df is None or df.empty:
        return None

    return _reconstruct_lineage_response(df)


def _reconstruct_lineage_response(df: pd.DataFrame) -> Dict[str, Any]:
    """Reconstruct lineage response dict from edge-list parquet.

    Parquet schema: (seed_cid, ancestor_cid, edge_type, cid_name)
      - edge_type ∈ {split_from, merge_source}: seed→ancestor mapping
      - edge_type == '__root__': ancestor_cid field holds root name for this seed
    """
    ancestors: Dict[str, List[str]] = defaultdict(list)
    cid_to_name: Dict[str, str] = {}
    seed_roots: Dict[str, str] = {}
    all_nodes = set()
    seed_cids = set()

    for _, row in df.iterrows():
        seed_cid = _safe_str(str(row.get("seed_cid") or ""))
        ancestor_cid = _safe_str(str(row.get("ancestor_cid") or ""))
        edge_type = str(row.get("edge_type") or "").strip()
        cid_name = str(row.get("cid_name") or "").strip()

        if not seed_cid:
            continue

        seed_cids.add(seed_cid)
        all_nodes.add(seed_cid)

        if edge_type == "__root__":
            # ancestor_cid stores the root name for this seed
            seed_roots[seed_cid] = ancestor_cid or seed_cid
            continue

        if not ancestor_cid:
            continue

        all_nodes.add(ancestor_cid)
        if ancestor_cid not in ancestors[seed_cid]:
            ancestors[seed_cid].append(ancestor_cid)
        if cid_name:
            cid_to_name[ancestor_cid] = cid_name

    seed_set = set(seed_cids)
    ancestor_only = all_nodes - seed_set
    total_ancestor_count = len(ancestor_only)

    return {
        "stage": "lineage",
        "ancestors": {seed: ancs for seed, ancs in ancestors.items()},
        "names": cid_to_name,
        "seed_roots": seed_roots,
        "roots": sorted(seed_cids),
        "total_nodes": len(all_nodes),
        "total_ancestor_count": total_ancestor_count,
        "parent_map": {},
        "merge_edges": {},
        "nodes": {},
        "edges": [],
    }


def _execute_msd_lineage_job(
    *,
    job_id: str,
    container_ids: List[str],
    direction: str = "backward",
) -> None:
    """RQ worker entry point for MSD lineage resolution.

    Processes seeds in batches, accumulates the lineage graph,
    and spools results to parquet.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging

    ensure_rq_logging()
    update_job_progress(_JOB_PREFIX, job_id, status="running", progress="starting")

    seed_cids = _normalize_list(container_ids)
    if not seed_cids:
        complete_job(_JOB_PREFIX, job_id, error="no container_ids provided")
        return

    total_batches = (len(seed_cids) + ORACLE_IN_BATCH_SIZE - 1) // ORACLE_IN_BATCH_SIZE
    logger.info(
        "msd lineage job started job_id=%s seeds=%s batches=%s direction=%s",
        job_id, len(seed_cids), total_batches, direction,
    )

    try:
        if direction == "backward":
            result = _resolve_backward_lineage(job_id, seed_cids, total_batches)
        else:
            raise ValueError(f"unsupported async lineage direction: {direction!r}")

        query_id = f"msd-lineage-{job_id}"
        stored = store_spooled_df(
            _SPOOL_NAMESPACE,
            query_id,
            result,
            ttl_seconds=MSD_LINEAGE_JOB_TTL_SECONDS,
        )
        if not stored:
            complete_job(_JOB_PREFIX, job_id, error="failed to store lineage spool")
            return

        complete_job(_JOB_PREFIX, job_id, query_id=query_id)
        logger.info(
            "msd lineage job completed job_id=%s query_id=%s rows=%s",
            job_id, query_id, len(result),
        )
    except Exception as exc:
        logger.error("msd lineage job failed job_id=%s: %s", job_id, exc, exc_info=True)
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


def _resolve_backward_lineage(
    job_id: str,
    seed_cids: List[str],
    total_batches: int,
) -> pd.DataFrame:
    """Resolve backward lineage (split ancestors + merge sources) in batches.

    Returns an edge-list DataFrame with columns:
        seed_cid, ancestor_cid, edge_type, cid_name
    """
    # Phase 1: batched split ancestor resolution
    accumulated_child_to_parent: Dict[str, str] = {}
    accumulated_cid_to_name: Dict[str, str] = {}

    for batch_num, batch_start in enumerate(range(0, len(seed_cids), ORACLE_IN_BATCH_SIZE)):
        batch = seed_cids[batch_start:batch_start + ORACLE_IN_BATCH_SIZE]
        split_result = LineageEngine.resolve_split_ancestors(batch)
        accumulated_child_to_parent.update(split_result["child_to_parent"])
        accumulated_cid_to_name.update(split_result["cid_to_name"])

        pct = int((batch_num + 1) / total_batches * 60)
        update_job_progress(
            _JOB_PREFIX, job_id,
            status="running",
            progress=f"{batch_num + 1}/{total_batches} split batches",
            pct=str(pct),
        )

    # Phase 2: merge source resolution on all discovered CIDs
    update_job_progress(_JOB_PREFIX, job_id, status="running", progress="resolving merge sources")
    all_discovered_cids = sorted(
        set(accumulated_child_to_parent.keys()) | set(accumulated_child_to_parent.values())
        | set(seed_cids)
    )
    merge_source_map = LineageEngine.resolve_merge_sources(all_discovered_cids)

    # Phase 3: build ancestors dict per seed
    update_job_progress(_JOB_PREFIX, job_id, status="running", progress="building ancestor graph")

    # Build per-seed ancestors by traversing child_to_parent
    seed_ancestors: Dict[str, set] = {}
    for seed in seed_cids:
        visited: set = set()
        current = seed
        depth = 0
        while current in accumulated_child_to_parent and depth < MAX_SPLIT_DEPTH:
            depth += 1
            parent = accumulated_child_to_parent[current]
            if parent in visited:
                break
            visited.add(parent)
            current = parent
        seed_ancestors[seed] = visited

    # Expand ancestors with merge sources
    merge_source_cids_all: set = set()
    if merge_source_map:
        for seed in seed_cids:
            self_and_ancestors = seed_ancestors[seed] | {seed}
            for cid in list(self_and_ancestors):
                for source_cid in merge_source_map.get(cid, []):
                    if source_cid == cid or source_cid in self_and_ancestors:
                        continue
                    seed_ancestors[seed].add(source_cid)
                    merge_source_cids_all.add(source_cid)

        # Resolve split ancestors for merge source CIDs
        seen = set(seed_cids) | set(accumulated_child_to_parent.keys()) | set(accumulated_child_to_parent.values())
        new_merge_cids = list(merge_source_cids_all - seen)
        if new_merge_cids:
            merge_split_result = LineageEngine.resolve_split_ancestors(new_merge_cids)
            merge_child_to_parent = merge_split_result["child_to_parent"]
            accumulated_cid_to_name.update(merge_split_result["cid_to_name"])

            for seed in seed_cids:
                for merge_cid in list(seed_ancestors[seed] & merge_source_cids_all):
                    current = merge_cid
                    depth = 0
                    while current in merge_child_to_parent and depth < MAX_SPLIT_DEPTH:
                        depth += 1
                        parent = merge_child_to_parent[current]
                        if parent in seed_ancestors[seed]:
                            break
                        seed_ancestors[seed].add(parent)
                        current = parent

    # Phase 4: compute seed roots
    seed_roots: Dict[str, str] = {}
    for seed in seed_cids:
        ancestors_set = seed_ancestors[seed]
        if ancestors_set:
            # Root = ancestor with no further parent in the accumulated graph
            full_child_to_parent = dict(accumulated_child_to_parent)
            root_cid = next(
                (cid for cid in ancestors_set if cid not in full_child_to_parent),
                next(iter(ancestors_set)),
            )
            seed_roots[seed] = accumulated_cid_to_name.get(root_cid, root_cid)
        else:
            seed_roots[seed] = accumulated_cid_to_name.get(seed, seed)

    # Phase 5: serialize to edge-list DataFrame
    rows = []
    for seed in seed_cids:
        for ancestor_cid in seed_ancestors[seed]:
            name = accumulated_cid_to_name.get(ancestor_cid, "")
            edge_type = "merge_source" if ancestor_cid in merge_source_cids_all else "split_from"
            rows.append({
                "seed_cid": seed,
                "ancestor_cid": ancestor_cid,
                "edge_type": edge_type,
                "cid_name": name,
            })
        # Store root info for this seed
        rows.append({
            "seed_cid": seed,
            "ancestor_cid": seed_roots.get(seed, seed),
            "edge_type": "__root__",
            "cid_name": "",
        })

    logger.info(
        "msd lineage backward resolution done: seeds=%s, total_rows=%s",
        len(seed_cids), len(rows),
    )
    return pd.DataFrame(rows, columns=["seed_cid", "ancestor_cid", "edge_type", "cid_name"])


# ---------------------------------------------------------------------------
# Central job registry — job-registry-central
# ---------------------------------------------------------------------------
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="msd-lineage",
    queue_name="msd-analysis",
    worker_fn=_execute_msd_lineage_job,
))
