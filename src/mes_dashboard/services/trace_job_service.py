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
    result["query_id"] = query_id
    result["trace_query_id"] = query_id
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
        total = domain_data.get("count", len(domain_data.get("data", [])))
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
        "query_id": query_id,
        "trace_query_id": query_id,
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
        import shutil
        import tempfile
        from pathlib import Path as _Path

        results: Dict[str, Dict[str, Any]] = {}
        failed_domains: List[str] = []
        domain_quality_meta: Dict[str, Dict[str, Any]] = {}

        is_msd = (profile == "mid_section_defect")
        aggregation = None

        if is_msd:
            # Streaming MSD path: Oracle → per-domain parquet → merged events spool
            _msd_params = payload.get("params") or {}
            _seed_container_ids = [
                cid.strip()
                for cid in (payload.get("seed_container_ids") or container_ids)
                if isinstance(cid, str) and cid.strip()
            ]
            _direction = str(_msd_params.get("direction") or "backward").strip() or "backward"
            _lineage_payload = _resolve_msd_lineage_payload(payload)
            # If lineage spool expired, re-resolve synchronously so ancestors are available
            # for event expansion and attribution JOIN.
            if not _lineage_payload and _seed_container_ids:
                try:
                    from mes_dashboard.services.lineage_engine import LineageEngine
                    from mes_dashboard.services.trace_lineage_job_service import (
                        _build_backward_response,
                        _build_forward_response,
                    )
                    if _direction == "backward":
                        _reresolved = LineageEngine.resolve_full_genealogy(_seed_container_ids)
                        _lineage_payload = _build_backward_response(_seed_container_ids, _reresolved)
                    else:
                        _reresolved = LineageEngine.resolve_forward_tree(_seed_container_ids)
                        _lineage_payload = _build_forward_response(_reresolved)
                    logger.info(
                        "trace job MSD lineage re-resolved job_id=%s ancestor_count=%s",
                        job_id,
                        len(_lineage_payload.get("ancestors") or {}),
                    )
                except Exception as _relin_exc:
                    logger.warning(
                        "trace job MSD lineage re-resolve failed job_id=%s: %s",
                        job_id, _relin_exc,
                    )
            _expanded_container_ids = _expand_msd_container_ids(
                _seed_container_ids,
                _lineage_payload,
                _direction,
            )
            trace_query_id = make_trace_query_id(
                profile=profile,
                container_ids=_seed_container_ids,
                start_date=_msd_params.get("start_date"),
                end_date=_msd_params.get("end_date"),
                station=_msd_params.get("station"),
                direction=_direction,
            )

            # Compute detection spool hash (same key used in _fetch_station_detection_data)
            try:
                from mes_dashboard.services.batch_query_engine import compute_query_hash as _cqh
                from mes_dashboard.services.mid_section_defect_service import (
                    _normalize_station as _msd_norm_st,
                    _canon_station_key as _msd_canon_st,
                )
                _det_start = _msd_params.get("start_date") or ""
                _det_end = _msd_params.get("end_date") or ""
                if not _det_start or not _det_end:
                    # Frontend sends date_range: [start, end] rather than start_date/end_date
                    _dr = _msd_params.get("date_range")
                    if isinstance(_dr, list) and len(_dr) == 2:
                        _det_start = str(_dr[0] or "").strip()
                        _det_end = str(_dr[1] or "").strip()
                _det_station_key = _msd_canon_st(_msd_norm_st(_msd_params.get("station") or ""))
                _msd_detection_hash: Optional[str] = _cqh({
                    "station": _det_station_key,
                    "start_date": _det_start,
                    "end_date": _det_end,
                })
            except Exception as _hash_exc:
                logger.warning("trace job MSD: could not compute detection_hash: %s", _hash_exc)
                _msd_detection_hash = None

            _tmp_dir = tempfile.mkdtemp()
            _domain_paths: Dict[str, Any] = {}
            aggregation = None
            agg_error: Optional[str] = None
            try:
                for domain in domains:
                    _dest = _Path(_tmp_dir) / f"{domain}.parquet"
                    try:
                        _row_count, _qm = EventFetcher.fetch_events_to_parquet(
                            _expanded_container_ids, domain, _dest
                        )
                        results[domain] = {
                            "data": [],
                            "count": _row_count,
                            "quality_meta": _qm,
                        }
                        domain_quality_meta[domain] = _qm
                        _domain_paths[domain] = _dest
                    except Exception as exc:
                        logger.error(
                            "trace job domain failed job_id=%s domain=%s: %s",
                            job_id, domain, exc, exc_info=True,
                        )
                        failed_domains.append(domain)
                        _fm = build_quality_meta(
                            status=QUALITY_STATUS_FAILED,
                            scope=QUALITY_SCOPE_DOMAIN,
                            domain=domain,
                            reasons=["domain_fetch_failed"],
                        )
                        domain_quality_meta[domain] = _fm
                        results[domain] = {"data": [], "count": 0, "quality_meta": _fm}

                try:
                    _write_msd_events_spool_from_paths(trace_query_id, _domain_paths)
                except Exception as _spool_exc:
                    logger.warning(
                        "trace job MSD events spool write failed job_id=%s: %s",
                        job_id, _spool_exc,
                    )

                # Write lineage spool so DuckDB attribution JOIN can work
                try:
                    _lineage_ancestors = _lineage_payload.get("ancestors") if isinstance(_lineage_payload, dict) else None
                    if isinstance(_lineage_ancestors, dict) and _lineage_ancestors:
                        from mes_dashboard.services.mid_section_defect_service import _write_msd_lineage_stage_spool
                        _lineage_cid_to_name = (_lineage_payload.get("cid_to_name") or _lineage_payload.get("names")) if isinstance(_lineage_payload, dict) else None
                        _lineage_seed_roots = _lineage_payload.get("seed_roots") if isinstance(_lineage_payload, dict) else None
                        _write_msd_lineage_stage_spool(trace_query_id, _lineage_ancestors, _lineage_cid_to_name, _lineage_seed_roots)
                        logger.info(
                            "trace job MSD lineage spool written job_id=%s ancestor_count=%s",
                            job_id, len(_lineage_ancestors),
                        )
                except Exception as _lin_exc:
                    logger.warning(
                        "trace job MSD lineage spool write failed job_id=%s: %s",
                        job_id, _lin_exc,
                    )

                # Write forward lineage spool (SEED_ID, DESCENDANT_ID) for DuckDB
                # forward attribution re-keying (AC-4) and forward summary (AC-5/AC-6).
                # Children_map is available from the lineage payload for forward queries.
                if _direction != "backward":
                    try:
                        _fwd_children_map = (
                            _lineage_payload.get("children_map") or {}
                            if isinstance(_lineage_payload, dict) else {}
                        )
                        from mes_dashboard.services.mid_section_defect_service import (
                            _write_msd_forward_lineage_spool,
                        )
                        _write_msd_forward_lineage_spool(
                            trace_query_id,
                            _seed_container_ids,
                            _fwd_children_map,
                        )
                        logger.info(
                            "trace job MSD forward lineage spool written job_id=%s "
                            "seed_count=%d children_map_size=%d",
                            job_id,
                            len(_seed_container_ids),
                            len(_fwd_children_map),
                        )
                    except Exception as _fwd_lin_exc:
                        logger.warning(
                            "trace job MSD forward lineage spool write failed job_id=%s: %s",
                            job_id, _fwd_lin_exc,
                        )

                # Write detection spool for container mode so DuckDB attribution works.
                # Date-range mode gets detection from _fetch_station_detection_data (called
                # inside _build_trace_aggregation_container_mode via compat job); container
                # mode must write it here so MsdDuckdbRuntime.get_summary() can find it.
                _msd_mode = str(_msd_params.get("mode") or "date_range").strip()
                if _msd_mode == "container" and _seed_container_ids:
                    try:
                        from mes_dashboard.services.mid_section_defect_service import (
                            _fetch_detection_by_container_ids,
                            _write_msd_detection_stage_spool,
                        )
                        _det_station = _msd_params.get("station") or "測試"
                        # Use _expanded_container_ids (seeds + all lineage ancestors) so that
                        # containers related via SPLITFROMID / COMBINEDASSYLOTS that passed
                        # through the detection station are included in the spool.
                        logger.info(
                            "trace job MSD container detection: seed_count=%d expanded_count=%d station=%s",
                            len(_seed_container_ids), len(_expanded_container_ids), _det_station,
                        )
                        _det_df = _fetch_detection_by_container_ids(_expanded_container_ids, _det_station)
                        if _det_df is not None and not _det_df.empty:
                            _write_msd_detection_stage_spool(trace_query_id, _det_df)
                            logger.info(
                                "trace job MSD container detection spool written job_id=%s rows=%d",
                                job_id, len(_det_df),
                            )
                    except Exception as _det_exc:
                        logger.warning(
                            "trace job MSD container detection spool failed job_id=%s: %s",
                            job_id, _det_exc,
                        )

                _update_meta(job_id, progress="building response")
            finally:
                shutil.rmtree(_tmp_dir, ignore_errors=True)

            # Build aggregation after tmp dir cleanup — uses spool files only
            _payload_for_aggregation = dict(payload or {})
            _payload_for_aggregation["seed_container_ids"] = _seed_container_ids
            if _lineage_payload:
                _payload_for_aggregation["lineage"] = {
                    "ancestors": _lineage_payload.get("ancestors") or {},
                    "children_map": _lineage_payload.get("children_map") or {},
                    "seed_roots": _lineage_payload.get("seed_roots") or {},
                }
            aggregation, agg_error = _build_job_msd_aggregation(
                _payload_for_aggregation,
                {},
                domain_quality_meta=domain_quality_meta,
                trace_query_id=trace_query_id,
                detection_hash=_msd_detection_hash,
            )

            if agg_error is not None:
                raise RuntimeError(agg_error)

            # Date-range FORWARD: the forward aggregation uses the in-memory path
            # (get_summary(forward) returns None) and never reaches the backward D4
            # detection-stage write inside _build_job_msd_aggregation.  Now that the
            # aggregation has run (and _fetch_station_detection_data has populated the
            # msd_detect spool), register that detection spool as a trace-scoped stage
            # spool so /analysis/detail (forward) can rebuild per-lot downstream impact
            # by trace_query_id.  (Backward writes its own in the D4 path.)
            if _msd_mode != "container" and _direction != "backward" and _msd_detection_hash:
                try:
                    from pathlib import Path as _FwdP
                    import pandas as _fwd_pd
                    from mes_dashboard.core.query_spool_store import (
                        get_spool_file_path as _fwd_gsfp,
                        get_stage_spool_path as _fwd_gssp,
                    )
                    from mes_dashboard.services.msd_duckdb_runtime import (
                        SPOOL_NAMESPACE as _FWD_NS,
                        _STAGE_DETECTION as _FWD_SD,
                    )
                    from mes_dashboard.services.mid_section_defect_service import (
                        _write_msd_detection_stage_spool,
                    )
                    if not _fwd_gssp(_FWD_NS, trace_query_id, _FWD_SD):
                        _fwd_src = _fwd_gsfp("msd_detect", _msd_detection_hash)
                        if _fwd_src and _FwdP(_fwd_src).exists():
                            _write_msd_detection_stage_spool(
                                trace_query_id, _fwd_pd.read_parquet(str(_fwd_src))
                            )
                            logger.info(
                                "trace job MSD forward detection stage spool written job_id=%s",
                                job_id,
                            )
                except Exception as _fwd_det_exc:
                    logger.warning(
                        "trace job MSD forward detection stage spool failed job_id=%s: %s",
                        job_id, _fwd_det_exc,
                    )

        else:
            # Non-MSD path: original in-memory fetch (unchanged)
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

            trace_query_id = make_general_trace_events_query_id(
                profile=profile,
                container_ids=container_ids,
                domains=domains,
            )

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


def _resolve_msd_lineage_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    lineage = payload.get("lineage") or {}
    if isinstance(lineage, dict) and (
        isinstance(lineage.get("ancestors"), dict) or isinstance(lineage.get("children_map"), dict)
    ):
        return lineage

    lineage_query_id = str(payload.get("lineage_query_id") or "").strip()
    if lineage_query_id:
        try:
            from mes_dashboard.services.trace_lineage_job_service import load_trace_lineage_result

            stored = load_trace_lineage_result(lineage_query_id)
            if isinstance(stored, dict):
                return stored
        except Exception as exc:
            logger.warning(
                "trace job MSD: failed to load lineage spool query_id=%s: %s",
                lineage_query_id,
                exc,
            )
    return {}


def _expand_msd_container_ids(
    seed_container_ids: List[str],
    lineage_payload: Dict[str, Any],
    direction: str,
) -> List[str]:
    seen = set()
    merged: List[str] = []
    for seed in seed_container_ids or []:
        value = str(seed or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)

    if direction == "forward":
        children_map = lineage_payload.get("children_map") if isinstance(lineage_payload, dict) else {}
        queue = list(merged)
        while queue:
            current = queue.pop(0)
            children = children_map.get(current) if isinstance(children_map, dict) else None
            if not isinstance(children, list):
                continue
            for child in children:
                child_id = str(child or "").strip()
                if not child_id or child_id in seen:
                    continue
                seen.add(child_id)
                merged.append(child_id)
                queue.append(child_id)
        return merged

    ancestors = lineage_payload.get("ancestors") if isinstance(lineage_payload, dict) else {}
    if isinstance(ancestors, dict):
        for values in ancestors.values():
            if not isinstance(values, list):
                continue
            for ancestor in values:
                ancestor_id = str(ancestor or "").strip()
                if not ancestor_id or ancestor_id in seen:
                    continue
                seen.add(ancestor_id)
                merged.append(ancestor_id)
    return merged


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
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
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
    ns_dir = (QUERY_SPOOL_DIR / SPOOL_NAMESPACE).resolve()
    ns_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False, dir=ns_dir) as tmp:
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


def _write_msd_events_spool_from_paths(
    trace_query_id: str,
    domain_parquet_paths: Dict[str, Any],
) -> None:
    """Streaming merge of per-domain parquet files into a single MSD events spool.

    Iterates each domain's parquet via ``pq.ParquetFile.iter_batches()`` and
    writes all records to a single consolidated events spool file, then
    registers it via ``register_stage_spool_file()``.  This is the streaming
    replacement for ``_write_msd_events_spool()`` — no full DataFrame is
    assembled in memory.
    """
    import tempfile
    from pathlib import Path as _Path
    import pyarrow as pa
    import pyarrow.parquet as pq
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
    from mes_dashboard.services.msd_duckdb_runtime import SPOOL_NAMESPACE, _STAGE_EVENTS
    from mes_dashboard.core.query_spool_store import register_stage_spool_file

    ns_dir = (QUERY_SPOOL_DIR / SPOOL_NAMESPACE).resolve()
    ns_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False, dir=ns_dir) as _tmp:
        tmp_path = _Path(_tmp.name)

    # First pass: collect schemas from all available domain parquets so we can
    # build a unified schema before opening the ParquetWriter.  Different
    # domains (e.g. upstream_history vs. materials) have completely different
    # column sets; pandas used to union them automatically via DataFrame(rows),
    # so we replicate that with pa.unify_schemas().
    domain_paths: Dict[str, _Path] = {}
    per_domain_schemas: List[pa.Schema] = []
    for domain, src_path in domain_parquet_paths.items():
        sp = _Path(src_path)
        if not sp.exists():
            logger.debug(
                "_write_msd_events_spool_from_paths: skip missing parquet domain=%s path=%s",
                domain, sp,
            )
            continue
        try:
            pf_schema = pq.read_schema(sp)
            per_domain_schemas.append(pf_schema)
            domain_paths[domain] = sp
        except Exception as exc:
            logger.warning(
                "_write_msd_events_spool_from_paths: cannot read schema domain=%s: %s",
                domain, exc,
            )

    if not per_domain_schemas:
        return

    unified_schema: pa.Schema = pa.unify_schemas(
        per_domain_schemas, promote_options="permissive"
    )

    writer = None
    total_rows = 0

    try:
        for domain, sp in domain_paths.items():
            try:
                pf = pq.ParquetFile(sp)
                for batch in pf.iter_batches():
                    if batch.num_rows == 0:
                        continue
                    table = pa.Table.from_batches([batch])
                    # Align to unified schema: add null columns for any fields
                    # this domain doesn't have, then reorder + cast.
                    for field in unified_schema:
                        if field.name not in table.schema.names:
                            null_col = pa.array(
                                [None] * len(table), type=field.type
                            )
                            table = table.append_column(field, null_col)
                    table = table.select(unified_schema.names).cast(
                        unified_schema, safe=False
                    )
                    if writer is None:
                        writer = pq.ParquetWriter(tmp_path, unified_schema)
                    writer.write_table(table)
                    total_rows += batch.num_rows
            except Exception as exc:
                logger.warning(
                    "_write_msd_events_spool_from_paths: failed to read domain parquet domain=%s: %s",
                    domain, exc,
                )
    finally:
        if writer is not None:
            writer.close()

    if total_rows == 0:
        logger.debug(
            "_write_msd_events_spool_from_paths: no events to spool trace_query_id=%s",
            trace_query_id,
        )
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    ok = register_stage_spool_file(
        SPOOL_NAMESPACE,
        trace_query_id,
        _STAGE_EVENTS,
        tmp_path,
        row_count=total_rows,
    )
    if ok:
        logger.info(
            "_write_msd_events_spool_from_paths: registered events spool trace_query_id=%s rows=%d",
            trace_query_id, total_rows,
        )
    else:
        logger.warning(
            "_write_msd_events_spool_from_paths: spool registration failed trace_query_id=%s",
            trace_query_id,
        )
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _build_job_msd_aggregation(
    payload: Dict[str, Any],
    domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]],
    domain_quality_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    trace_query_id: Optional[str] = None,
    detection_hash: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build MSD aggregation inside worker process (no Flask context).

    When *trace_query_id* and *detection_hash* are both provided and the
    corresponding spool files are available, aggregation is computed via
    DuckDB using the canonical detection spool path.  Falls back to the
    in-memory ``build_trace_aggregation_from_events`` path otherwise.
    """
    params = payload.get("params")
    normalized_loss_reasons = None
    direction = "backward"
    _station_order_fallback: int = 999
    _pj_types: Optional[List[str]] = None
    _packages: Optional[List[str]] = None
    if isinstance(params, dict):
        from mes_dashboard.services.mid_section_defect_service import parse_loss_reasons_param
        from mes_dashboard.services.mid_section_defect_service import _normalize_station
        from mes_dashboard.config.workcenter_groups import get_group_order

        normalized_loss_reasons = parse_loss_reasons_param(params.get("loss_reasons"))
        direction = str(params.get("direction") or "backward").strip() or "backward"
        _raw_station = params.get("station") or "測試"
        _stations = _normalize_station(_raw_station)
        _station_order_fallback = min(get_group_order(s) for s in _stations)
        _raw_pj = params.get("pj_types") or []
        _raw_pkg = params.get("packages") or []
        _pj_types = [str(v).strip() for v in _raw_pj if str(v).strip()] if isinstance(_raw_pj, list) else None
        _packages = [str(v).strip() for v in _raw_pkg if str(v).strip()] if isinstance(_raw_pkg, list) else None
        if not _pj_types:
            _pj_types = None
        if not _packages:
            _packages = None

    if trace_query_id:
        try:
            from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

            runtime = MsdDuckdbRuntime(trace_query_id)
            if runtime.is_available():
                summary = runtime.get_summary(
                    direction=direction,
                    loss_reasons=normalized_loss_reasons,
                    station_order_fallback=_station_order_fallback,
                    pj_types=_pj_types,
                    packages=_packages,
                )
                if summary is not None:
                    if domain_quality_meta:
                        summary["domain_quality_meta"] = domain_quality_meta
                    return summary, None
        except Exception as _runtime_exc:
            logger.warning(
                "_build_job_msd_aggregation: existing stage runtime failed trace_query_id=%s: %s",
                trace_query_id, _runtime_exc,
            )

    # DuckDB spool hit path (D4): prefer detection-spool-backed aggregation
    if trace_query_id and detection_hash:
        try:
            from pathlib import Path as _AggPath
            from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime
            from mes_dashboard.core.query_spool_store import get_spool_file_path
            from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS as _WCG

            _upstream_groups = (
                [g for g, cfg in _WCG.items() if cfg["order"] < _station_order_fallback]
                if _station_order_fallback < 999 else None
            )

            runtime = MsdDuckdbRuntime(trace_query_id)
            if runtime.is_available():
                detection_path = get_spool_file_path("msd_detect", detection_hash)
                if detection_path and _AggPath(detection_path).exists():
                    summary = runtime.get_summary_with_detection(
                        str(detection_path),
                        loss_reasons=normalized_loss_reasons,
                        upstream_station_groups=_upstream_groups,
                        pj_types=_pj_types,
                        packages=_packages,
                    )
                    if summary is not None:
                        if domain_quality_meta:
                            summary["domain_quality_meta"] = domain_quality_meta
                        # Persist the FULL detection rows as stage spool under
                        # msd-events namespace so get_detail() can access them after
                        # the short msd_detect TTL expires.  Do NOT pre-filter by
                        # pj_types/packages: trace_query_id is package-independent, so
                        # this stage must hold the full population; get_detail() applies
                        # the Type/Package mask at read time.
                        try:
                            import tempfile as _tmpmod
                            import pandas as _pd
                            from mes_dashboard.services.msd_duckdb_runtime import (
                                SPOOL_NAMESPACE as _MSD_NS,
                                _STAGE_DETECTION,
                            )
                            from mes_dashboard.core.query_spool_store import (
                                QUERY_SPOOL_DIR as _QUERY_SPOOL_DIR,
                                register_stage_spool_file as _reg_stage,
                            )
                            _det_df = _pd.read_parquet(str(detection_path))
                            _ns_dir = (_QUERY_SPOOL_DIR / _MSD_NS).resolve()
                            _ns_dir.mkdir(parents=True, exist_ok=True)
                            with _tmpmod.NamedTemporaryFile(suffix=".parquet", delete=False, dir=_ns_dir) as _tf:
                                _det_copy = _AggPath(_tf.name)
                            _det_df.to_parquet(_det_copy, engine="pyarrow", index=False)
                            _reg_stage(_MSD_NS, trace_query_id, _STAGE_DETECTION, _det_copy, len(_det_df))
                            logger.info(
                                "_build_job_msd_aggregation: detection stage registered trace_query_id=%s rows=%d",
                                trace_query_id, len(_det_df),
                            )
                        except Exception as _copy_exc:
                            logger.warning(
                                "_build_job_msd_aggregation: detection stage save failed: %s", _copy_exc
                            )
                        return summary, None
        except Exception as _ddb_exc:
            logger.warning(
                "_build_job_msd_aggregation: DuckDB path failed trace_query_id=%s: %s",
                trace_query_id, _ddb_exc,
            )

    from mes_dashboard.services.mid_section_defect_service import (
        build_trace_aggregation_from_events,
    )

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
    station = params.get("station") or "測試"

    aggregation = build_trace_aggregation_from_events(
        start_date,
        end_date,
        loss_reasons=normalized_loss_reasons,
        pj_types=_pj_types,
        packages=_packages,
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
_TRACE_QUERY_ID_SCHEMA_VERSION = 2  # bumped: SEED_ID column added to forward lineage spool


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
