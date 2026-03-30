# -*- coding: utf-8 -*-
"""Async trace job service using RQ (Redis Queue).

Provides enqueue/status/result functions for long-running trace events queries.
The worker entry point ``execute_trace_events_job`` runs in a separate RQ worker
process — independent of gunicorn — with its own memory space.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from mes_dashboard.core.query_quality_contract import (
    QUALITY_SCOPE_DOMAIN,
    QUALITY_SCOPE_QUERY,
    QUALITY_STATUS_FAILED,
    build_quality_meta,
    merge_quality_metas,
    normalize_quality_meta,
    unpack_event_fetch_result,
)
from mes_dashboard.core.redis_client import get_control_redis_client, get_key, get_redis_client

logger = logging.getLogger("mes_dashboard.trace_job_service")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
TRACE_ASYNC_CID_THRESHOLD = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))
TRACE_JOB_TTL_SECONDS = int(os.getenv("TRACE_JOB_TTL_SECONDS", "3600"))
TRACE_JOB_TIMEOUT_SECONDS = int(os.getenv("TRACE_JOB_TIMEOUT_SECONDS", "1800"))
TRACE_WORKER_QUEUE = os.getenv("TRACE_WORKER_QUEUE", "trace-events")
TRACE_EVENTS_MAX_WORKERS = int(os.getenv("TRACE_EVENTS_MAX_WORKERS", "2"))
TRACE_STREAM_BATCH_SIZE = int(os.getenv("TRACE_STREAM_BATCH_SIZE", "5000"))

# Spool-backed result storage (task 4.1)
_TRACE_EVENTS_SPOOL_NS = "trace_events"
_TRACE_EVENTS_SPOOL_TTL = TRACE_JOB_TTL_SECONDS

# ---------------------------------------------------------------------------
# RQ health check — delegates to shared async_query_job_service
# ---------------------------------------------------------------------------

def is_async_available() -> bool:
    """Return True if RQ is installed, Redis is reachable, and workers exist.

    Delegates to the shared async_query_job_service.is_async_available() to
    avoid duplicate health-check logic and share the 60-second TTL cache.
    """
    from mes_dashboard.services.async_query_job_service import (
        is_async_available as _shared_is_async_available,
    )
    return _shared_is_async_available()


def _check_rq_available() -> bool:
    """Check if RQ is installed (delegates to shared service)."""
    from mes_dashboard.services.async_query_job_service import _check_rq_installed
    return _check_rq_installed()


def _get_rq_queue():
    """Get RQ queue instance. Returns None if unavailable."""
    if not _check_rq_available():
        return None
    conn = get_redis_client()
    if conn is None:
        return None
    from rq import Queue
    return Queue(TRACE_WORKER_QUEUE, connection=conn)


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------
def _meta_key(job_id: str) -> str:
    return get_key(f"trace:job:{job_id}:meta")


def _result_key(job_id: str) -> str:
    return get_key(f"trace:job:{job_id}:result")


def _result_meta_key(job_id: str) -> str:
    return get_key(f"trace:job:{job_id}:result:meta")


def _result_chunk_key(job_id: str, domain: str, chunk_idx: int) -> str:
    return get_key(f"trace:job:{job_id}:result:{domain}:{chunk_idx}")


def _result_aggregation_key(job_id: str) -> str:
    return get_key(f"trace:job:{job_id}:result:aggregation")


# ---------------------------------------------------------------------------
# Public API: enqueue / status / result
# ---------------------------------------------------------------------------
def enqueue_trace_events_job(
    profile: str,
    container_ids: List[str],
    domains: List[str],
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """Enqueue an async trace events job.

    Returns:
        (job_id, None) on success, (None, error_message) on failure.
    """
    queue = _get_rq_queue()
    if queue is None:
        return None, "async job queue unavailable (Redis or RQ not installed)"

    job_id = f"trace-evt-{uuid.uuid4().hex[:12]}"

    # Job meta written to control-plane Redis (not subject to cache eviction)
    ctrl = get_control_redis_client()
    meta = {
        "profile": profile,
        "cid_count": str(len(container_ids)),
        "domains": ",".join(domains),
        "status": "queued",
        "progress": "",
        "created_at": str(time.time()),
        "completed_at": "",
        "error": "",
    }
    ctrl.hset(_meta_key(job_id), mapping=meta)
    ctrl.expire(_meta_key(job_id), TRACE_JOB_TTL_SECONDS)

    try:
        queue.enqueue(
            execute_trace_events_job,
            job_id,
            profile,
            container_ids,
            domains,
            payload,
            job_id=job_id,
            job_timeout=TRACE_JOB_TIMEOUT_SECONDS,
            result_ttl=TRACE_JOB_TTL_SECONDS,
            failure_ttl=TRACE_JOB_TTL_SECONDS,
        )
    except Exception as exc:
        logger.error("Failed to enqueue trace job: %s", exc, exc_info=True)
        ctrl.delete(_meta_key(job_id))
        return None, f"enqueue failed: {exc}"

    logger.info(
        "trace job enqueued job_id=%s profile=%s cid_count=%s domains=%s",
        job_id, profile, len(container_ids), ",".join(domains),
    )
    return job_id, None


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get trace job status from Redis metadata. Returns None if not found."""
    conn = get_control_redis_client()
    if conn is None:
        return None

    meta = conn.hgetall(_meta_key(job_id))
    if not meta:
        return None

    created_at = float(meta.get("created_at", 0))
    elapsed = time.time() - created_at if created_at > 0 else 0

    result: Dict[str, Any] = {
        "job_id": job_id,
        "status": meta.get("status", "unknown"),
        "profile": meta.get("profile"),
        "cid_count": int(meta.get("cid_count", 0)),
        "domains": meta.get("domains", "").split(",") if meta.get("domains") else [],
        "progress": meta.get("progress", ""),
        "created_at": created_at,
        "elapsed_seconds": round(elapsed, 1),
        "error": meta.get("error") or None,
    }

    # Stage-aware progress fields (task 4.2)
    stage = meta.get("stage")
    if stage:
        result["stage"] = stage
    completed_stages_raw = meta.get("completed_stages")
    if completed_stages_raw:
        stages = [s.strip() for s in completed_stages_raw.split(",") if s.strip()]
        if stages:
            result["completed_stages"] = stages

    # Canonical query_id / trace_query_id for spool-backed results
    query_id = meta.get("query_id")
    if query_id:
        result["query_id"] = query_id
        result["trace_query_id"] = query_id  # alias for MSD consumers

    return result


def get_job_result(
    job_id: str,
    domain: Optional[str] = None,
    offset: int = 0,
    limit: int = 0,
) -> Optional[Dict[str, Any]]:
    """Get completed job result.

    Prefers spool-backed storage when query_id is present in result manifest.
    Falls back to chunked Redis storage, then legacy single-key storage.
    """
    conn = get_redis_client()
    if conn is None:
        return None

    # Try manifest (new chunked / spool-backed storage)
    raw_meta = conn.get(_result_meta_key(job_id))
    if raw_meta is not None:
        meta = json.loads(raw_meta)
        if meta.get("query_id"):
            return _get_spool_result(conn, job_id, meta, domain, offset, limit)
        return _get_chunked_result(conn, job_id, raw_meta, domain, offset, limit)

    # Fall back to legacy single-key storage
    raw = conn.get(_result_key(job_id))
    if raw is None:
        return None

    result = json.loads(raw)

    if domain and "results" in result:
        domain_data = result["results"].get(domain)
        if domain_data is None:
            return result
        rows = domain_data.get("data", [])
        if offset > 0:
            rows = rows[offset:]
        if limit > 0:
            rows = rows[:limit]
        result["results"] = {
            domain: {"data": rows, "count": len(rows), "total": domain_data.get("count", 0)},
        }

    return result


def _get_spool_result(
    conn,
    job_id: str,
    meta: Dict[str, Any],
    domain: Optional[str] = None,
    offset: int = 0,
    limit: int = 0,
) -> Dict[str, Any]:
    """Reconstruct trace events result from per-domain spool stages."""
    import pandas as pd
    from mes_dashboard.core.query_spool_store import load_spooled_df

    query_id = meta["query_id"]
    domain_info = meta.get("domains", {})
    domain_quality_meta_raw = meta.get("domain_quality_meta", {})

    results: Dict[str, Any] = {}
    result_domain_quality_meta: Dict[str, Dict[str, Any]] = {}
    target_domains = [domain] if domain else list(domain_info.keys())

    for d in target_domains:
        info = domain_info.get(d)
        if info is None:
            continue
        total = info.get("total", 0)

        rows: List[Dict[str, Any]] = []
        try:
            spool_id = _trace_domain_spool_id(query_id, d)
            df = load_spooled_df(_TRACE_EVENTS_SPOOL_NS, spool_id)
            if df is not None and not df.empty:
                if offset > 0:
                    df = df.iloc[offset:]
                if limit > 0:
                    df = df.iloc[:limit]
                rows = df.to_dict("records")
        except Exception as exc:
            logger.warning("spool read failed domain=%s query_id=%s: %s", d, query_id, exc)

        raw_domain_meta = None
        if isinstance(domain_quality_meta_raw, dict):
            raw_domain_meta = domain_quality_meta_raw.get(d)
        if raw_domain_meta is None and isinstance(info, dict):
            raw_domain_meta = info.get("quality_meta")
        domain_meta = normalize_quality_meta(raw_domain_meta, default_scope=QUALITY_SCOPE_DOMAIN)
        if not domain_meta.get("domain"):
            domain_meta["domain"] = d
        result_domain_quality_meta[d] = domain_meta

        results[d] = {
            "data": rows,
            "count": len(rows),
            "total": total,
            "quality_meta": domain_meta,
        }

    aggregation = None
    raw_agg = conn.get(_result_aggregation_key(job_id))
    if raw_agg is not None:
        aggregation = json.loads(raw_agg)

    quality_meta = normalize_quality_meta(
        meta.get("quality_meta"), default_scope=QUALITY_SCOPE_QUERY,
    )
    if not meta.get("quality_meta"):
        quality_meta = merge_quality_metas(
            result_domain_quality_meta.values(), scope=QUALITY_SCOPE_QUERY,
        )

    result: Dict[str, Any] = {
        "stage": "events",
        "results": results,
        "aggregation": aggregation,
        "quality_meta": quality_meta,
        "domain_quality_meta": result_domain_quality_meta,
    }
    if meta.get("failed_domains"):
        result["error"] = "one or more domains failed"
        result["code"] = "EVENTS_PARTIAL_FAILURE"
        result["failed_domains"] = meta["failed_domains"]

    return result


def _get_chunked_result(
    conn,
    job_id: str,
    raw_meta: str,
    domain: Optional[str] = None,
    offset: int = 0,
    limit: int = 0,
) -> Dict[str, Any]:
    """Reconstruct result from chunked Redis keys."""
    meta = json.loads(raw_meta)
    domain_info = meta.get("domains", {})
    domain_quality_meta_raw = meta.get("domain_quality_meta", {})

    results: Dict[str, Any] = {}
    result_domain_quality_meta: Dict[str, Dict[str, Any]] = {}
    target_domains = [domain] if domain else list(domain_info.keys())

    for d in target_domains:
        info = domain_info.get(d)
        if info is None:
            continue
        num_chunks = info.get("chunks", 0)
        total = info.get("total", 0)

        rows: List[Dict[str, Any]] = []
        for i in range(num_chunks):
            raw_chunk = conn.get(_result_chunk_key(job_id, d, i))
            if raw_chunk is not None:
                rows.extend(json.loads(raw_chunk))

        if offset > 0:
            rows = rows[offset:]
        if limit > 0:
            rows = rows[:limit]

        raw_domain_meta = None
        if isinstance(domain_quality_meta_raw, dict):
            raw_domain_meta = domain_quality_meta_raw.get(d)
        if raw_domain_meta is None:
            raw_domain_meta = info.get("quality_meta") if isinstance(info, dict) else None
        domain_meta = normalize_quality_meta(
            raw_domain_meta,
            default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if not domain_meta.get("domain"):
            domain_meta["domain"] = d
        result_domain_quality_meta[d] = domain_meta

        results[d] = {
            "data": rows,
            "count": len(rows),
            "total": total,
            "quality_meta": domain_meta,
        }

    aggregation = None
    raw_agg = conn.get(_result_aggregation_key(job_id))
    if raw_agg is not None:
        aggregation = json.loads(raw_agg)

    quality_meta = normalize_quality_meta(
        meta.get("quality_meta"),
        default_scope=QUALITY_SCOPE_QUERY,
    )
    if not meta.get("quality_meta"):
        quality_meta = merge_quality_metas(
            result_domain_quality_meta.values(),
            scope=QUALITY_SCOPE_QUERY,
        )

    result: Dict[str, Any] = {
        "stage": "events",
        "results": results,
        "aggregation": aggregation,
        "quality_meta": quality_meta,
        "domain_quality_meta": result_domain_quality_meta,
    }

    if meta.get("failed_domains"):
        result["error"] = "one or more domains failed"
        result["code"] = "EVENTS_PARTIAL_FAILURE"
        result["failed_domains"] = meta["failed_domains"]

    return result


# ---------------------------------------------------------------------------
# NDJSON streaming generator
# ---------------------------------------------------------------------------
def stream_job_result_ndjson(job_id: str):
    """Generator yielding NDJSON lines for a completed job's chunked result.

    Each line is a JSON object followed by ``\\n``.  The protocol:

    1. ``{"type":"meta", ...}``
    2. For each domain:
       - ``{"type":"domain_start", "domain":"...", "total":N, "quality_meta":{...}}``
       - ``{"type":"records", "domain":"...", "batch":i, "count":N, "data":[...]}``
       - ``{"type":"domain_end", "domain":"...", "count":N}``
    3. ``{"type":"aggregation", "data":{...}}`` (if present)
    4. ``{"type":"quality_meta", "quality_meta":{...}, "domain_quality_meta":{...}}``
    5. ``{"type":"complete", "total_records":N}``
    """
    conn = get_redis_client()
    if conn is None:
        yield _ndjson_line({"type": "error", "message": "Redis unavailable"})
        return

    raw_meta = conn.get(_result_meta_key(job_id))
    if raw_meta is None:
        # Fall back: legacy single-key result → emit as single NDJSON blob
        raw = conn.get(_result_key(job_id))
        if raw is None:
            yield _ndjson_line({"type": "error", "message": "result not found"})
            return
        result = json.loads(raw)
        yield _ndjson_line({"type": "full_result", "data": result})
        return

    meta = json.loads(raw_meta)

    # Prefer spool-backed streaming when query_id is set
    if meta.get("query_id"):
        yield from _stream_spool_result_ndjson(conn, job_id, meta)
        return

    domain_info = meta.get("domains", {})
    domain_quality_meta = meta.get("domain_quality_meta", {})

    yield _ndjson_line({
        "type": "meta",
        "job_id": job_id,
        "profile": meta.get("profile"),
        "domains": list(domain_info.keys()),
    })

    total_records = 0
    for domain_name, info in domain_info.items():
        num_chunks = info.get("chunks", 0)
        domain_total = info.get("total", 0)
        raw_domain_meta = None
        if isinstance(domain_quality_meta, dict):
            raw_domain_meta = domain_quality_meta.get(domain_name)
        if raw_domain_meta is None and isinstance(info, dict):
            raw_domain_meta = info.get("quality_meta")
        normalized_domain_meta = normalize_quality_meta(
            raw_domain_meta,
            default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if not normalized_domain_meta.get("domain"):
            normalized_domain_meta["domain"] = domain_name

        yield _ndjson_line({
            "type": "domain_start",
            "domain": domain_name,
            "total": domain_total,
            "quality_meta": normalized_domain_meta,
        })

        domain_count = 0
        for i in range(num_chunks):
            raw_chunk = conn.get(_result_chunk_key(job_id, domain_name, i))
            if raw_chunk is None:
                continue
            rows = json.loads(raw_chunk)
            domain_count += len(rows)
            yield _ndjson_line({
                "type": "records",
                "domain": domain_name,
                "batch": i,
                "count": len(rows),
                "data": rows,
            })

        yield _ndjson_line({
            "type": "domain_end",
            "domain": domain_name,
            "count": domain_count,
        })
        total_records += domain_count

    raw_agg = conn.get(_result_aggregation_key(job_id))
    if raw_agg is not None:
        yield _ndjson_line({
            "type": "aggregation",
            "data": json.loads(raw_agg),
        })

    if meta.get("failed_domains"):
        yield _ndjson_line({
            "type": "warning",
            "code": "EVENTS_PARTIAL_FAILURE",
            "failed_domains": meta["failed_domains"],
        })

    yield _ndjson_line({
        "type": "quality_meta",
        "quality_meta": normalize_quality_meta(
            meta.get("quality_meta"),
            default_scope=QUALITY_SCOPE_QUERY,
        ),
        "domain_quality_meta": (
            domain_quality_meta if isinstance(domain_quality_meta, dict) else {}
        ),
    })

    yield _ndjson_line({
        "type": "complete",
        "total_records": total_records,
    })


def _ndjson_line(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Chunked result storage
# ---------------------------------------------------------------------------
def _store_chunked_result(
    conn,
    job_id: str,
    profile: str,
    results: Dict[str, Dict[str, Any]],
    aggregation: Optional[Dict[str, Any]],
    failed_domains: List[str],
    quality_meta: Optional[Dict[str, Any]] = None,
    domain_quality_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """Store job result as chunked Redis keys for streaming retrieval."""
    domain_info: Dict[str, Dict[str, Any]] = {}
    normalized_domain_quality_meta: Dict[str, Dict[str, Any]] = {}

    for domain_name, domain_data in results.items():
        rows = domain_data.get("data", [])
        total = len(rows)
        chunks = [
            rows[i:i + TRACE_STREAM_BATCH_SIZE]
            for i in range(0, max(len(rows), 1), TRACE_STREAM_BATCH_SIZE)
        ] if rows else []

        for idx, chunk in enumerate(chunks):
            conn.setex(
                _result_chunk_key(job_id, domain_name, idx),
                TRACE_JOB_TTL_SECONDS,
                json.dumps(chunk, default=str, ensure_ascii=False),
            )

        raw_domain_meta = None
        if isinstance(domain_quality_meta, dict):
            raw_domain_meta = domain_quality_meta.get(domain_name)
        if raw_domain_meta is None:
            raw_domain_meta = domain_data.get("quality_meta")
        normalized_domain_meta = normalize_quality_meta(
            raw_domain_meta,
            default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if not normalized_domain_meta.get("domain"):
            normalized_domain_meta["domain"] = domain_name
        normalized_domain_quality_meta[domain_name] = normalized_domain_meta

        domain_info[domain_name] = {
            "chunks": len(chunks),
            "total": total,
            "quality_meta": normalized_domain_meta,
        }

    if aggregation is not None:
        conn.setex(
            _result_aggregation_key(job_id),
            TRACE_JOB_TTL_SECONDS,
            json.dumps(aggregation, default=str, ensure_ascii=False),
        )

    normalized_quality_meta = normalize_quality_meta(
        quality_meta,
        default_scope=QUALITY_SCOPE_QUERY,
    )
    if quality_meta is None:
        normalized_quality_meta = merge_quality_metas(
            normalized_domain_quality_meta.values(),
            scope=QUALITY_SCOPE_QUERY,
        )

    result_meta = {
        "profile": profile,
        "domains": domain_info,
        "failed_domains": sorted(failed_domains) if failed_domains else [],
        "quality_meta": normalized_quality_meta,
        "domain_quality_meta": normalized_domain_quality_meta,
    }
    conn.setex(
        _result_meta_key(job_id),
        TRACE_JOB_TTL_SECONDS,
        json.dumps(result_meta, default=str, ensure_ascii=False),
    )


def _store_result_manifest(
    conn,
    job_id: str,
    profile: str,
    query_id: str,
    results: Dict[str, Dict[str, Any]],
    aggregation: Optional[Dict[str, Any]],
    failed_domains: List[str],
    quality_meta: Optional[Dict[str, Any]] = None,
    domain_quality_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """Store lightweight result manifest in Redis (no row body data).

    Row data is in Parquet spool; this manifest holds only quality metadata,
    domain totals, and aggregation pointer for job status/progress display.
    """
    domain_info: Dict[str, Dict[str, Any]] = {}
    normalized_domain_quality_meta: Dict[str, Dict[str, Any]] = {}

    for domain_name, domain_data in results.items():
        total = len(domain_data.get("data", []))
        raw_domain_meta = None
        if isinstance(domain_quality_meta, dict):
            raw_domain_meta = domain_quality_meta.get(domain_name)
        if raw_domain_meta is None:
            raw_domain_meta = domain_data.get("quality_meta")
        normalized_domain_meta = normalize_quality_meta(
            raw_domain_meta, default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if not normalized_domain_meta.get("domain"):
            normalized_domain_meta["domain"] = domain_name
        normalized_domain_quality_meta[domain_name] = normalized_domain_meta
        domain_info[domain_name] = {
            "total": total,
            "quality_meta": normalized_domain_meta,
        }

    if aggregation is not None:
        conn.setex(
            _result_aggregation_key(job_id),
            TRACE_JOB_TTL_SECONDS,
            json.dumps(aggregation, default=str, ensure_ascii=False),
        )

    normalized_quality_meta = normalize_quality_meta(
        quality_meta, default_scope=QUALITY_SCOPE_QUERY,
    )
    if quality_meta is None:
        normalized_quality_meta = merge_quality_metas(
            normalized_domain_quality_meta.values(), scope=QUALITY_SCOPE_QUERY,
        )

    result_meta = {
        "profile": profile,
        "query_id": query_id,
        "domains": domain_info,
        "failed_domains": sorted(failed_domains) if failed_domains else [],
        "quality_meta": normalized_quality_meta,
        "domain_quality_meta": normalized_domain_quality_meta,
    }
    conn.setex(
        _result_meta_key(job_id),
        TRACE_JOB_TTL_SECONDS,
        json.dumps(result_meta, default=str, ensure_ascii=False),
    )


def _stream_spool_result_ndjson(conn, job_id: str, meta: Dict[str, Any]):
    """Stream spool-backed trace events result as NDJSON lines."""
    from mes_dashboard.core.query_spool_store import load_spooled_df

    query_id = meta["query_id"]
    domain_info = meta.get("domains", {})
    domain_quality_meta_raw = meta.get("domain_quality_meta", {})

    yield _ndjson_line({
        "type": "meta",
        "job_id": job_id,
        "profile": meta.get("profile"),
        "domains": list(domain_info.keys()),
    })

    total_records = 0
    for domain_name, info in domain_info.items():
        domain_total = info.get("total", 0)
        raw_domain_meta = None
        if isinstance(domain_quality_meta_raw, dict):
            raw_domain_meta = domain_quality_meta_raw.get(domain_name)
        if raw_domain_meta is None and isinstance(info, dict):
            raw_domain_meta = info.get("quality_meta")
        normalized_domain_meta = normalize_quality_meta(
            raw_domain_meta, default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if not normalized_domain_meta.get("domain"):
            normalized_domain_meta["domain"] = domain_name

        yield _ndjson_line({
            "type": "domain_start",
            "domain": domain_name,
            "total": domain_total,
            "quality_meta": normalized_domain_meta,
        })

        domain_count = 0
        try:
            spool_id = _trace_domain_spool_id(query_id, domain_name)
            df = load_spooled_df(_TRACE_EVENTS_SPOOL_NS, spool_id)
            if df is not None and not df.empty:
                batch_idx = 0
                for batch_start in range(0, len(df), TRACE_STREAM_BATCH_SIZE):
                    batch_df = df.iloc[batch_start:batch_start + TRACE_STREAM_BATCH_SIZE]
                    rows = batch_df.to_dict("records")
                    domain_count += len(rows)
                    yield _ndjson_line({
                        "type": "records",
                        "domain": domain_name,
                        "batch": batch_idx,
                        "count": len(rows),
                        "data": rows,
                    })
                    batch_idx += 1
        except Exception as exc:
            logger.warning(
                "spool stream read failed domain=%s query_id=%s: %s",
                domain_name, query_id, exc,
            )

        yield _ndjson_line({
            "type": "domain_end",
            "domain": domain_name,
            "count": domain_count,
        })
        total_records += domain_count

    raw_agg = conn.get(_result_aggregation_key(job_id))
    if raw_agg is not None:
        yield _ndjson_line({"type": "aggregation", "data": json.loads(raw_agg)})

    if meta.get("failed_domains"):
        yield _ndjson_line({
            "type": "warning",
            "code": "EVENTS_PARTIAL_FAILURE",
            "failed_domains": meta["failed_domains"],
        })

    quality_meta_raw = meta.get("quality_meta")
    yield _ndjson_line({
        "type": "quality_meta",
        "quality_meta": normalize_quality_meta(
            quality_meta_raw, default_scope=QUALITY_SCOPE_QUERY,
        ),
        "domain_quality_meta": (
            domain_quality_meta_raw if isinstance(domain_quality_meta_raw, dict) else {}
        ),
    })

    yield _ndjson_line({"type": "complete", "total_records": total_records})


# ---------------------------------------------------------------------------
# Worker entry point (runs in RQ worker process)
# ---------------------------------------------------------------------------
def _update_meta(job_id: str, **fields) -> None:
    """Update job metadata fields in control-plane Redis."""
    conn = get_control_redis_client()
    if conn is None:
        return
    key = _meta_key(job_id)
    conn.hset(key, mapping={k: str(v) for k, v in fields.items()})


def execute_trace_events_job(
    job_id: str,
    profile: str,
    container_ids: List[str],
    domains: List[str],
    payload: Dict[str, Any],
) -> None:
    """RQ worker entry point: execute trace events and store result in Redis.

    This function runs in a dedicated RQ worker process — outside gunicorn —
    so it does not compete for gunicorn worker threads or the DB connection pool.
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.event_fetcher import EventFetcher

    logger.info(
        "trace job started job_id=%s profile=%s cid_count=%s domains=%s",
        job_id, profile, len(container_ids), ",".join(domains),
    )

    _update_meta(job_id, status="started", progress="fetching events")

    try:
        results: Dict[str, Dict[str, Any]] = {}
        raw_domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        failed_domains: List[str] = []
        domain_quality_meta: Dict[str, Dict[str, Any]] = {}

        is_msd = (profile == "mid_section_defect")

        with ThreadPoolExecutor(
            max_workers=min(len(domains), TRACE_EVENTS_MAX_WORKERS),
        ) as executor:
            futures = {
                executor.submit(EventFetcher.fetch_events, container_ids, domain): domain
                for domain in domains
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    events_payload = future.result()
                    events_by_cid, quality_meta = unpack_event_fetch_result(
                        events_payload,
                        domain=domain,
                    )
                    rows = _flatten_domain_records(events_by_cid)
                    results[domain] = {
                        "data": rows,
                        "count": len(rows),
                        "quality_meta": quality_meta,
                    }
                    domain_quality_meta[domain] = quality_meta
                    if is_msd:
                        raw_domain_results[domain] = events_by_cid
                except Exception as exc:
                    logger.error(
                        "trace job domain failed job_id=%s domain=%s: %s",
                        job_id, domain, exc, exc_info=True,
                    )
                    failed_domains.append(domain)
                    failed_meta = build_quality_meta(
                        status=QUALITY_STATUS_FAILED,
                        scope=QUALITY_SCOPE_DOMAIN,
                        domain=domain,
                        reasons=["domain_fetch_failed"],
                    )
                    domain_quality_meta[domain] = failed_meta
                    results[domain] = {
                        "data": [],
                        "count": 0,
                        "quality_meta": failed_meta,
                    }

        _update_meta(job_id, progress="building response")

        aggregation = None
        if is_msd:
            params = payload.get("params") or {}
            trace_query_id = make_trace_query_id(
                profile=profile,
                container_ids=container_ids,
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                station=params.get("station"),
                direction=params.get("direction"),
            )

            # Write MSD analysis spool for DuckDB-backed analysis/export
            try:
                _write_msd_events_spool(
                    job_id=job_id,
                    trace_query_id=trace_query_id,
                    raw_domain_results=raw_domain_results,
                )
            except Exception as _spool_exc:
                logger.warning(
                    "trace job MSD events spool write failed job_id=%s: %s",
                    job_id, _spool_exc,
                )

            aggregation, agg_error = _build_job_msd_aggregation(
                payload,
                raw_domain_results,
                domain_quality_meta=domain_quality_meta,
            )
            del raw_domain_results
            if agg_error is not None:
                raise RuntimeError(agg_error)
        else:
            trace_query_id = make_general_trace_events_query_id(
                profile=profile,
                container_ids=container_ids,
                domains=domains,
            )
            del raw_domain_results

        # Write per-domain result spool for get_job_result / streaming (all profiles)
        try:
            _write_trace_events_spool(trace_query_id, results)
        except Exception as _spool_exc:
            logger.warning(
                "trace job result spool write failed job_id=%s: %s",
                job_id, _spool_exc,
            )

        quality_meta = merge_quality_metas(
            domain_quality_meta.values(),
            scope=QUALITY_SCOPE_QUERY,
        )

        # Store lightweight result manifest (no row body data — rows in spool)
        conn = get_redis_client()
        if conn is not None:
            _store_result_manifest(
                conn,
                job_id,
                profile,
                trace_query_id,
                results,
                aggregation,
                failed_domains,
                quality_meta=quality_meta,
                domain_quality_meta=domain_quality_meta,
            )

        _update_meta(
            job_id,
            status="finished",
            progress="complete",
            completed_at=time.time(),
            query_id=trace_query_id,
        )

        logger.info(
            "trace job completed job_id=%s profile=%s domains=%s",
            job_id, profile, ",".join(domains),
        )

        if len(container_ids) > 10000:
            gc.collect()

    except Exception as exc:
        logger.error(
            "trace job failed job_id=%s: %s", job_id, exc, exc_info=True,
        )
        _update_meta(
            job_id,
            status="failed",
            error=str(exc),
            completed_at=time.time(),
        )
        raise


# ---------------------------------------------------------------------------
# Helpers (duplicated from trace_routes to avoid Flask dependency in worker)
# ---------------------------------------------------------------------------
def _flatten_domain_records(
    events_by_cid: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for records in events_by_cid.values():
        if not isinstance(records, list):
            continue
        for row in records:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_msd_events_spool(
    job_id: str,
    trace_query_id: str,
    raw_domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]],
) -> None:
    """Write flattened MSD events to parquet spool for DuckDB runtime.

    Task 6.1: records stage spool metadata so that /analysis/detail and /export
    can read from DuckDB instead of re-running Oracle.
    """
    import pandas as pd
    import tempfile
    from pathlib import Path
    from mes_dashboard.services.msd_duckdb_runtime import SPOOL_NAMESPACE, _STAGE_EVENTS
    from mes_dashboard.core.query_spool_store import register_stage_spool_file

    rows: List[Dict[str, Any]] = []
    for events_by_cid in raw_domain_results.values():
        for records in events_by_cid.values():
            if isinstance(records, list):
                rows.extend(r for r in records if isinstance(r, dict))

    if not rows:
        logger.debug("_write_msd_events_spool: no events to spool for trace_query_id=%s", trace_query_id)
        return

    df = pd.DataFrame(rows)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_parquet(tmp_path, engine="pyarrow", index=False)

    ok = register_stage_spool_file(
        SPOOL_NAMESPACE,
        trace_query_id,
        _STAGE_EVENTS,
        tmp_path,
        row_count=len(df),
    )
    if ok:
        logger.info(
            "_write_msd_events_spool: registered events spool trace_query_id=%s rows=%d",
            trace_query_id, len(df),
        )
    else:
        logger.warning(
            "_write_msd_events_spool: spool registration failed trace_query_id=%s",
            trace_query_id,
        )
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _build_job_msd_aggregation(
    payload: Dict[str, Any],
    domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]],
    domain_quality_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build MSD aggregation inside worker process (no Flask context)."""
    from mes_dashboard.services.mid_section_defect_service import (
        build_trace_aggregation_from_events,
        parse_loss_reasons_param,
    )

    params = payload.get("params")
    if not isinstance(params, dict):
        return None, "params is required for mid_section_defect profile"

    mode = str(params.get("mode") or "date_range").strip()

    start_date = None
    end_date = None
    if mode != "container":
        date_range = params.get("date_range")
        if isinstance(date_range, list) and len(date_range) == 2:
            start_date = str(date_range[0] or "").strip()
            end_date = str(date_range[1] or "").strip()
        if not start_date or not end_date:
            start_date = str(params.get("start_date") or "").strip()
            end_date = str(params.get("end_date") or "").strip()
        if not start_date or not end_date:
            return None, "start_date/end_date is required in params"

    raw_loss_reasons = params.get("loss_reasons")
    loss_reasons = parse_loss_reasons_param(raw_loss_reasons)

    lineage = payload.get("lineage") or {}
    lineage_ancestors = lineage.get("ancestors") if isinstance(lineage, dict) else None
    lineage_roots = lineage.get("seed_roots") if isinstance(lineage, dict) else None

    seed_container_ids = payload.get("seed_container_ids", [])
    if not seed_container_ids and isinstance(lineage_ancestors, dict):
        seed_container_ids = list(lineage_ancestors.keys())
    seed_container_ids = [
        s.strip() for s in seed_container_ids
        if isinstance(s, str) and s.strip()
    ]

    upstream_events = domain_results.get("upstream_history", {})
    materials_events = domain_results.get("materials", {})
    downstream_events = domain_results.get("downstream_rejects", {})
    station = str(params.get("station") or "測試").strip()
    direction = str(params.get("direction") or "backward").strip()

    aggregation = build_trace_aggregation_from_events(
        start_date,
        end_date,
        loss_reasons=loss_reasons,
        seed_container_ids=seed_container_ids,
        lineage_ancestors=lineage_ancestors,
        lineage_roots=lineage_roots,
        upstream_events_by_cid=upstream_events,
        materials_events_by_cid=materials_events,
        downstream_events_by_cid=downstream_events,
        station=station,
        direction=direction,
        mode=mode,
        upstream_quality_meta=(domain_quality_meta or {}).get("upstream_history"),
        materials_quality_meta=(domain_quality_meta or {}).get("materials"),
        downstream_quality_meta=(domain_quality_meta or {}).get("downstream_rejects"),
    )
    if aggregation is None:
        return None, "aggregation service unavailable"
    if "error" in aggregation:
        return None, str(aggregation["error"])
    return aggregation, None


# ---------------------------------------------------------------------------
# Spool helpers for trace events result storage (task 4.1)
# ---------------------------------------------------------------------------
def _trace_domain_spool_id(query_id: str, domain: str) -> str:
    """Return the spool query_id for a specific domain within a trace events job."""
    domain_safe = domain.replace(":", ".").replace("/", "_")
    return f"{query_id}.{domain_safe}"


def _write_trace_events_spool(
    query_id: str,
    results: Dict[str, Dict[str, Any]],
) -> None:
    """Write per-domain event DataFrames to Parquet spool.

    Called for ALL profiles so that get_job_result and streaming can read from
    spool instead of Redis chunk keys.
    """
    import pandas as pd
    from mes_dashboard.core.query_spool_store import store_spooled_df

    for domain_name, domain_data in results.items():
        rows = domain_data.get("data", [])
        if not rows:
            continue
        try:
            df = pd.DataFrame(rows)
            spool_id = _trace_domain_spool_id(query_id, domain_name)
            store_spooled_df(
                _TRACE_EVENTS_SPOOL_NS, spool_id, df,
                ttl_seconds=_TRACE_EVENTS_SPOOL_TTL,
            )
            logger.debug(
                "_write_trace_events_spool: domain=%s rows=%d query_id=%s",
                domain_name, len(df), query_id,
            )
        except Exception as exc:
            logger.warning(
                "_write_trace_events_spool: domain=%s failed: %s", domain_name, exc,
            )


def make_general_trace_events_query_id(
    profile: str,
    container_ids: List[str],
    domains: List[str],
) -> str:
    """Return the canonical spool query_id for a non-MSD trace events job.

    Deterministic: same profile + container_ids + domains → same id, enabling
    result-spool reuse without re-running Oracle.
    """
    key: Dict[str, Any] = {
        "_v": _TRACE_QUERY_ID_SCHEMA_VERSION,
        "profile": profile,
        "container_ids": sorted(container_ids or []),
        "domains": sorted(domains or []),
    }
    canonical = json.dumps(key, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"trc-{digest}"


# ---------------------------------------------------------------------------
# Canonical trace_query_id / dataset_id (task 2.4)
# ---------------------------------------------------------------------------
# MSD staged trace must expose a stable ``trace_query_id`` so that:
#   - /analysis/detail and /export can resolve the matching spool
#   - spool can be reused without re-running Oracle
#
# The trace_query_id is derived from the primary query parameters (not a
# random UUID) so that the same query always maps to the same spool key.
_TRACE_QUERY_ID_SCHEMA_VERSION = 1


def make_trace_query_id(
    profile: str,
    container_ids: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    station: Optional[str] = None,
    direction: Optional[str] = None,
    **extra_params,
) -> str:
    """Return the canonical trace_query_id for an MSD staged trace query.

    The id is derived from the primary query parameters so that any repeat
    invocation with the same inputs returns the same id and can reuse an
    existing spool.

    ``extra_params`` are included in the hash when non-empty to support
    future MSD variants without breaking the existing identity contract.
    """
    key: Dict[str, Any] = {
        "_v": _TRACE_QUERY_ID_SCHEMA_VERSION,
        "profile": profile,
        "container_ids": sorted(container_ids or []),
    }
    if start_date:
        key["start_date"] = start_date
    if end_date:
        key["end_date"] = end_date
    if station:
        key["station"] = station
    if direction:
        key["direction"] = direction
    if extra_params:
        key["extra"] = {k: v for k, v in sorted(extra_params.items())}

    canonical = json.dumps(key, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"msd-{digest}"
