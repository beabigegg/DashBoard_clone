# -*- coding: utf-8 -*-
"""Staged trace API routes.

Provides three stage endpoints for progressive trace execution:
- seed-resolve
- lineage
- events
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, request

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.interactive_memory_guard import process_rss_mb
from mes_dashboard.core.query_quality_contract import (
    QUALITY_SCOPE_DOMAIN,
    QUALITY_SCOPE_QUERY,
    QUALITY_STATUS_FAILED,
    build_quality_meta,
    merge_quality_metas,
    normalize_quality_meta,
    unpack_event_fetch_result,
)
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.redis_client import try_acquire_lock, release_lock
from mes_dashboard.core.response import error_response, success_response
from mes_dashboard.services.event_fetcher import EventFetcher
from mes_dashboard.services.lineage_engine import LineageEngine
from mes_dashboard.services.mid_section_defect_service import (
    build_trace_aggregation_from_events,
    parse_loss_reasons_param,
    resolve_trace_seed_lots,
)
from mes_dashboard.services.query_tool_service import resolve_lots
from mes_dashboard.services.trace_job_service import (
    TRACE_ASYNC_CID_THRESHOLD,
    enqueue_trace_events_job,
    get_job_result,
    get_job_status,
    is_async_available,
    stream_job_result_ndjson,
)

logger = logging.getLogger("mes_dashboard.trace_routes")

trace_bp = Blueprint("trace", __name__, url_prefix="/api/trace")

TRACE_SLOW_THRESHOLD_SECONDS = float(os.getenv('TRACE_SLOW_THRESHOLD_SECONDS', '15'))
TRACE_EVENTS_MAX_WORKERS = int(os.getenv('TRACE_EVENTS_MAX_WORKERS', '2'))
TRACE_EVENTS_CID_LIMIT = int(os.getenv('TRACE_EVENTS_CID_LIMIT', '50000'))
TRACE_CACHE_TTL_SECONDS = 300

# RSS guard: reject sync event processing when RSS exceeds this MB threshold
TRACE_SYNC_RSS_REJECT_MB = float(os.getenv("TRACE_SYNC_RSS_REJECT_MB", "1100"))

# Stampede lock for events endpoint sync path
EVENTS_LOCK_TTL_SECONDS = 240
EVENTS_LOCK_WAIT_TIMEOUT_SECONDS = 180
EVENTS_LOCK_POLL_INTERVAL_SECONDS = 0.5

PROFILE_QUERY_TOOL = "query_tool"
PROFILE_QUERY_TOOL_REVERSE = "query_tool_reverse"
PROFILE_MID_SECTION_DEFECT = "mid_section_defect"
SUPPORTED_PROFILES = {
    PROFILE_QUERY_TOOL,
    PROFILE_QUERY_TOOL_REVERSE,
    PROFILE_MID_SECTION_DEFECT,
}

QUERY_TOOL_RESOLVE_TYPES_BY_PROFILE = {
    PROFILE_QUERY_TOOL: {"wafer_lot", "lot_id", "work_order"},
    PROFILE_QUERY_TOOL_REVERSE: {"serial_number", "gd_work_order", "gd_lot_id"},
}
SUPPORTED_EVENT_DOMAINS = {
    "history",
    "materials",
    "rejects",
    "holds",
    "jobs",
    "upstream_history",
    "downstream_rejects",
}

_TRACE_SEED_RATE_LIMIT = configured_rate_limit(
    bucket="trace-seed",
    max_attempts_env="TRACE_SEED_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="TRACE_SEED_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)

_TRACE_LINEAGE_RATE_LIMIT = configured_rate_limit(
    bucket="trace-lineage",
    max_attempts_env="TRACE_LINEAGE_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="TRACE_LINEAGE_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)

_TRACE_EVENTS_RATE_LIMIT = configured_rate_limit(
    bucket="trace-events",
    max_attempts_env="TRACE_EVENTS_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="TRACE_EVENTS_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=15,
    default_window_seconds=60,
)

_TRACE_JOB_RATE_LIMIT = configured_rate_limit(
    bucket="trace-job-status",
    max_attempts_env="TRACE_JOB_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="TRACE_JOB_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)


def _json_body() -> Optional[Dict[str, Any]]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return None


def _normalize_strings(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _short_hash(parts: List[str]) -> str:
    digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _hash_payload(payload: Any) -> str:
    dumped = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.md5(dumped.encode("utf-8")).hexdigest()[:12]


def _seed_cache_key(profile: str, params: Dict[str, Any]) -> str:
    if profile == PROFILE_MID_SECTION_DEFECT:
        # loss_reasons does not affect seed resolution; exclude it so that
        # changing the reason filter hits the cache instead of re-querying Oracle.
        filtered = {k: v for k, v in params.items() if k != "loss_reasons"}
        return f"trace:seed:{profile}:{_hash_payload(filtered)}"
    return f"trace:seed:{profile}:{_hash_payload(params)}"


def _lineage_cache_key(profile: str, container_ids: List[str]) -> str:
    return f"trace:lineage:{profile}:{_short_hash(sorted(container_ids))}"


def _events_cache_key(profile: str, domains: List[str], container_ids: List[str]) -> str:
    domains_hash = _short_hash(sorted(domains))
    cid_hash = _short_hash(sorted(container_ids))
    return f"trace:evt:{profile}:{domains_hash}:{cid_hash}"


def _error(code: str, message: str, status_code: int = 400):
    return error_response(code, message, status_code=status_code)


def _is_timeout_exception(exc: Exception) -> bool:
    text = str(exc).lower()
    timeout_fragments = (
        "timeout",
        "timed out",
        "ora-01013",
        "dpi-1067",
        "cancelled",
    )
    return any(fragment in text for fragment in timeout_fragments)


def _validate_profile(profile: Any) -> Optional[str]:
    if not isinstance(profile, str):
        return None
    value = profile.strip()
    if value in SUPPORTED_PROFILES:
        return value
    return None


def _extract_date_range(params: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    date_range = params.get("date_range")
    if isinstance(date_range, list) and len(date_range) == 2:
        start_date = str(date_range[0] or "").strip()
        end_date = str(date_range[1] or "").strip()
        if start_date and end_date:
            return start_date, end_date

    start_date = str(params.get("start_date") or "").strip()
    end_date = str(params.get("end_date") or "").strip()
    if start_date and end_date:
        return start_date, end_date
    return None, None


def _seed_resolve_query_tool(
    profile: str,
    params: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[tuple[str, str, int]]]:
    resolve_type = str(params.get("resolve_type") or params.get("input_type") or "").strip()
    allowed_types = QUERY_TOOL_RESOLVE_TYPES_BY_PROFILE.get(profile, set())
    if resolve_type not in allowed_types:
        return None, (
            "INVALID_PARAMS",
            f"resolve_type must be one of: {','.join(sorted(allowed_types))}",
            400,
        )

    values = _normalize_strings(params.get("values", []))
    if not values:
        return None, ("INVALID_PARAMS", "values must contain at least one query value", 400)

    resolved = resolve_lots(resolve_type, values)
    if not isinstance(resolved, dict):
        return None, ("SEED_RESOLVE_FAILED", "seed resolve returned unexpected payload", 500)
    if "error" in resolved:
        return None, ("SEED_RESOLVE_FAILED", str(resolved.get("error") or "seed resolve failed"), 400)

    seeds = []
    seen = set()
    for row in resolved.get("data", []):
        if not isinstance(row, dict):
            continue
        container_id = str(row.get("container_id") or row.get("CONTAINERID") or "").strip()
        if not container_id or container_id in seen:
            continue
        seen.add(container_id)
        lot_id = str(
            row.get("lot_id")
            or row.get("CONTAINERNAME")
            or row.get("input_value")
            or container_id
        ).strip()
        seeds.append({
            "container_id": container_id,
            "container_name": lot_id,
            "lot_id": lot_id,
        })

    return {"seeds": seeds, "seed_count": len(seeds)}, None


def _seed_resolve_mid_section_defect(
    params: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[tuple[str, str, int]]]:
    mode = str(params.get("mode") or "date_range").strip()

    if mode == "container":
        resolve_type = str(params.get("resolve_type") or "").strip()
        if resolve_type not in {"lot_id", "work_order", "wafer_lot", "serial_number", "gd_work_order", "gd_lot_id"}:
            return None, (
                "INVALID_PARAMS",
                "resolve_type must be one of: lot_id, work_order, wafer_lot, serial_number, gd_work_order, gd_lot_id",
                400,
            )
        values = _normalize_strings(params.get("values", []))
        if not values:
            return None, ("INVALID_PARAMS", "values must contain at least one query value", 400)

        resolved = resolve_lots(resolve_type, values)
        if not isinstance(resolved, dict):
            return None, ("SEED_RESOLVE_FAILED", "seed resolve returned unexpected payload", 500)
        if "error" in resolved:
            return None, ("SEED_RESOLVE_FAILED", str(resolved.get("error") or "seed resolve failed"), 400)

        seeds = []
        seen: set = set()
        not_found: List[str] = []
        resolved_values: set = set()
        for row in resolved.get("data", []):
            if not isinstance(row, dict):
                continue
            container_id = str(row.get("container_id") or row.get("CONTAINERID") or "").strip()
            if not container_id or container_id in seen:
                continue
            seen.add(container_id)
            lot_id = str(
                row.get("lot_id")
                or row.get("CONTAINERNAME")
                or row.get("input_value")
                or container_id
            ).strip()
            seeds.append({
                "container_id": container_id,
                "container_name": lot_id,
                "lot_id": lot_id,
            })
            input_val = str(row.get("input_value") or "").strip()
            if input_val:
                resolved_values.add(input_val)

        for val in values:
            if val not in resolved_values and not any(
                s.get("lot_id", "") == val or s.get("container_name", "") == val
                for s in seeds
            ):
                not_found.append(val)

        return {
            "seeds": seeds,
            "seed_count": len(seeds),
            "not_found": not_found,
        }, None

    # date_range mode (default)
    start_date, end_date = _extract_date_range(params)
    if not start_date or not end_date:
        return None, ("INVALID_PARAMS", "start_date/end_date (or date_range) is required", 400)

    station = str(params.get("station") or "測試").strip()
    result = resolve_trace_seed_lots(start_date, end_date, station=station)
    if result is None:
        return None, ("SEED_RESOLVE_FAILED", "seed resolve service unavailable", 503)
    if "error" in result:
        return None, ("SEED_RESOLVE_FAILED", str(result["error"]), 400)
    return result, None


def _build_lineage_response(
    container_ids: List[str],
    ancestors_raw: Dict[str, Any],
    cid_to_name: Optional[Dict[str, str]] = None,
    parent_map: Optional[Dict[str, List[str]]] = None,
    merge_edges: Optional[Dict[str, List[str]]] = None,
    typed_nodes: Optional[Dict[str, Dict[str, Any]]] = None,
    typed_edges: Optional[List[Dict[str, Any]]] = None,
    seed_roots: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    normalized_ancestors: Dict[str, List[str]] = {}
    all_nodes = set(container_ids)
    for seed in container_ids:
        raw_values = ancestors_raw.get(seed, set())
        values = raw_values if isinstance(raw_values, (set, list, tuple)) else []
        normalized_list = sorted({
            str(item).strip()
            for item in values
            if isinstance(item, str) and str(item).strip()
        })
        normalized_ancestors[seed] = normalized_list
        all_nodes.update(normalized_list)

    # Count unique ancestor CIDs excluding seeds themselves
    seed_set = set(container_ids)
    ancestor_only = all_nodes - seed_set
    total_ancestor_count = len(ancestor_only)

    response: Dict[str, Any] = {
        "stage": "lineage",
        "ancestors": normalized_ancestors,
        "merges": {},
        "total_nodes": len(all_nodes),
        "total_ancestor_count": total_ancestor_count,
    }
    if seed_roots:
        response["seed_roots"] = seed_roots
    if cid_to_name:
        response["names"] = {
            cid: name for cid, name in cid_to_name.items()
            if cid in all_nodes and name
        }
    if parent_map:
        response["parent_map"] = {
            child: parents for child, parents in parent_map.items()
            if child in all_nodes
        }
    if merge_edges:
        response["merge_edges"] = {
            child: sources for child, sources in merge_edges.items()
            if child in all_nodes
        }
    if typed_nodes:
        response["nodes"] = {
            cid: node for cid, node in typed_nodes.items()
            if cid in all_nodes or cid in container_ids
        }
    if typed_edges:
        normalized_edges = []
        for edge in typed_edges:
            if not isinstance(edge, dict):
                continue
            from_cid = str(edge.get("from_cid") or "").strip()
            to_cid = str(edge.get("to_cid") or "").strip()
            if not from_cid or not to_cid:
                continue
            if from_cid in all_nodes or to_cid in all_nodes:
                normalized_edges.append(edge)
                all_nodes.add(from_cid)
                all_nodes.add(to_cid)
        response["edges"] = normalized_edges
        response["total_nodes"] = len(all_nodes)
    return response


def _flatten_domain_records(events_by_cid: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for records in events_by_cid.values():
        if not isinstance(records, list):
            continue
        for row in records:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _ensure_events_quality_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    results = payload.get("results")
    domain_quality_meta: Dict[str, Dict[str, Any]] = {}
    if isinstance(results, dict):
        for domain, domain_result in results.items():
            if not isinstance(domain_result, dict):
                continue
            domain_meta = normalize_quality_meta(
                domain_result.get("quality_meta"),
                default_scope=QUALITY_SCOPE_DOMAIN,
            )
            if not domain_meta.get("domain"):
                domain_meta["domain"] = domain
            domain_result["quality_meta"] = domain_meta
            domain_quality_meta[domain] = domain_meta

    raw_domain_meta = payload.get("domain_quality_meta")
    if isinstance(raw_domain_meta, dict):
        for domain, meta in raw_domain_meta.items():
            if domain in domain_quality_meta:
                continue
            normalized = normalize_quality_meta(meta, default_scope=QUALITY_SCOPE_DOMAIN)
            if not normalized.get("domain"):
                normalized["domain"] = domain
            domain_quality_meta[domain] = normalized

    if payload.get("quality_meta"):
        quality_meta = normalize_quality_meta(
            payload.get("quality_meta"),
            default_scope=QUALITY_SCOPE_QUERY,
        )
    else:
        quality_meta = merge_quality_metas(
            domain_quality_meta.values(),
            scope=QUALITY_SCOPE_QUERY,
        )

    payload["quality_meta"] = quality_meta
    payload["domain_quality_meta"] = domain_quality_meta
    return payload


def _parse_lineage_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lineage = payload.get("lineage")
    if isinstance(lineage, dict):
        ancestors = lineage.get("ancestors")
        if isinstance(ancestors, dict):
            return ancestors
    direct_ancestors = payload.get("ancestors")
    if isinstance(direct_ancestors, dict):
        return direct_ancestors
    return None


def _parse_lineage_roots(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract seed_roots mapping from lineage payload."""
    lineage = payload.get("lineage")
    if isinstance(lineage, dict):
        roots = lineage.get("seed_roots")
        if isinstance(roots, dict):
            return roots
    direct_roots = payload.get("seed_roots")
    if isinstance(direct_roots, dict):
        return direct_roots
    return None


def _build_msd_aggregation(
    payload: Dict[str, Any],
    domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]],
    domain_quality_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[tuple[str, str, int]]]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return None, ("INVALID_PARAMS", "params is required for mid_section_defect profile", 400)

    mode = str(params.get("mode") or "date_range").strip()

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    if mode != "container":
        start_date, end_date = _extract_date_range(params)
        if not start_date or not end_date:
            return None, ("INVALID_PARAMS", "start_date/end_date is required in params", 400)

    raw_loss_reasons = params.get("loss_reasons")
    loss_reasons = parse_loss_reasons_param(raw_loss_reasons)

    lineage_ancestors = _parse_lineage_payload(payload)
    lineage_roots = _parse_lineage_roots(payload)
    seed_container_ids = _normalize_strings(payload.get("seed_container_ids", []))
    if not seed_container_ids and isinstance(lineage_ancestors, dict):
        seed_container_ids = _normalize_strings(list(lineage_ancestors.keys()))

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
        return None, ("EVENTS_AGGREGATION_FAILED", "aggregation service unavailable", 503)
    if "error" in aggregation:
        return None, ("EVENTS_AGGREGATION_FAILED", str(aggregation["error"]), 400)
    return aggregation, None


@trace_bp.route("/seed-resolve", methods=["POST"])
@_TRACE_SEED_RATE_LIMIT
def seed_resolve():
    payload = _json_body()
    if payload is None:
        return _error("INVALID_PARAMS", "request body must be JSON object", 400)

    profile = _validate_profile(payload.get("profile"))
    if profile is None:
        return _error("INVALID_PROFILE", "unsupported profile", 400)

    params = payload.get("params")
    if not isinstance(params, dict):
        return _error("INVALID_PARAMS", "params must be an object", 400)

    seed_cache_key = _seed_cache_key(profile, params)
    cached = cache_get(seed_cache_key)
    if cached is not None:
        return success_response(cached)

    request_cache_key = payload.get("cache_key")
    logger.info(
        "trace seed-resolve profile=%s correlation_cache_key=%s",
        profile,
        request_cache_key,
    )

    started = time.monotonic()
    if profile in {PROFILE_QUERY_TOOL, PROFILE_QUERY_TOOL_REVERSE}:
        resolved, route_error = _seed_resolve_query_tool(profile, params)
    else:
        resolved, route_error = _seed_resolve_mid_section_defect(params)

    elapsed = time.monotonic() - started
    if elapsed > TRACE_SLOW_THRESHOLD_SECONDS:
        logger.warning("trace seed-resolve slow elapsed=%.2fs", elapsed)

    if route_error is not None:
        code, message, status = route_error
        return _error(code, message, status)

    response = {
        "stage": "seed-resolve",
        "seeds": resolved.get("seeds", []),
        "seed_count": int(resolved.get("seed_count", 0)),
        "cache_key": seed_cache_key,
    }
    cache_set(seed_cache_key, response, ttl=TRACE_CACHE_TTL_SECONDS)
    return success_response(response)


@trace_bp.route("/lineage", methods=["POST"])
@_TRACE_LINEAGE_RATE_LIMIT
def lineage():
    payload = _json_body()
    if payload is None:
        return _error("INVALID_PARAMS", "request body must be JSON object", 400)

    profile = _validate_profile(payload.get("profile"))
    if profile is None:
        return _error("INVALID_PROFILE", "unsupported profile", 400)

    container_ids = _normalize_strings(payload.get("container_ids", []))
    if not container_ids:
        return _error("INVALID_PARAMS", "container_ids must contain at least one id", 400)

    lineage_cache_key = _lineage_cache_key(profile, container_ids)
    cached = cache_get(lineage_cache_key)
    if cached is not None:
        return success_response(cached)

    logger.info(
        "trace lineage profile=%s count=%s correlation_cache_key=%s",
        profile,
        len(container_ids),
        payload.get("cache_key"),
    )

    # Determine lineage direction: backward profiles use reverse genealogy,
    # forward profiles (and mid_section_defect with direction=backward) use genealogy
    direction = "forward"
    if profile == PROFILE_QUERY_TOOL_REVERSE:
        direction = "backward"
    elif profile == PROFILE_MID_SECTION_DEFECT:
        params = payload.get("params") or {}
        direction = str(params.get("direction") or "backward").strip()

    started = time.monotonic()
    try:
        if direction == "backward":
            reverse_graph = LineageEngine.resolve_full_genealogy(container_ids)
            response = _build_lineage_response(
                container_ids,
                reverse_graph.get("ancestors", {}),
                cid_to_name=reverse_graph.get("cid_to_name"),
                parent_map=reverse_graph.get("parent_map"),
                merge_edges=reverse_graph.get("merge_edges"),
                typed_nodes=reverse_graph.get("nodes"),
                typed_edges=reverse_graph.get("edges"),
                seed_roots=reverse_graph.get("seed_roots"),
            )
            response["roots"] = list(container_ids)
        else:
            forward_tree = LineageEngine.resolve_forward_tree(container_ids)
            cid_to_name = forward_tree.get("cid_to_name") or {}
            response = {
                "stage": "lineage",
                "roots": forward_tree.get("roots", []),
                "children_map": forward_tree.get("children_map", {}),
                "leaf_serials": forward_tree.get("leaf_serials", {}),
                "names": {cid: name for cid, name in cid_to_name.items() if name},
                "total_nodes": forward_tree.get("total_nodes", 0),
                "nodes": forward_tree.get("nodes", {}),
                "edges": forward_tree.get("edges", []),
            }
    except Exception as exc:
        if _is_timeout_exception(exc):
            return _error("LINEAGE_TIMEOUT", "lineage query timed out", 504)
        logger.error("lineage stage failed: %s", exc, exc_info=True)
        return _error("LINEAGE_FAILED", "lineage stage failed", 500)

    elapsed = time.monotonic() - started
    if elapsed > TRACE_SLOW_THRESHOLD_SECONDS:
        logger.warning("trace lineage slow elapsed=%.2fs", elapsed)

    cache_set(lineage_cache_key, response, ttl=TRACE_CACHE_TTL_SECONDS)
    return success_response(response)


@trace_bp.route("/events", methods=["POST"])
@_TRACE_EVENTS_RATE_LIMIT
def events():
    payload = _json_body()
    if payload is None:
        return _error("INVALID_PARAMS", "request body must be JSON object", 400)

    profile = _validate_profile(payload.get("profile"))
    if profile is None:
        return _error("INVALID_PROFILE", "unsupported profile", 400)

    container_ids = _normalize_strings(payload.get("container_ids", []))
    if not container_ids:
        return _error("INVALID_PARAMS", "container_ids must contain at least one id", 400)

    domains = _normalize_strings(payload.get("domains", []))
    if not domains:
        return _error("INVALID_PARAMS", "domains must contain at least one domain", 400)
    invalid_domains = sorted(set(domains) - SUPPORTED_EVENT_DOMAINS)
    if invalid_domains:
        return _error(
            "INVALID_PARAMS",
            f"unsupported domains: {','.join(invalid_domains)}",
            400,
        )

    # Admission control: non-MSD profiles have a hard CID limit to prevent OOM.
    # MSD (reject tracing) needs all CIDs for accurate aggregation statistics.
    is_msd = (profile == PROFILE_MID_SECTION_DEFECT)
    cid_count = len(container_ids)

    # Route large queries to async job queue when available.
    # Falls through to sync path if RQ is not installed or Redis is down.
    if cid_count > TRACE_ASYNC_CID_THRESHOLD and is_async_available():
        job_id, err = enqueue_trace_events_job(profile, container_ids, domains, payload)
        if job_id is not None:
            logger.info(
                "trace events routed to async job_id=%s profile=%s cid_count=%s",
                job_id, profile, cid_count,
            )
            return success_response({
                "stage": "events",
                "async": True,
                "job_id": job_id,
                "status_url": f"/api/trace/job/{job_id}",
                "stream_url": f"/api/trace/job/{job_id}/stream",
            }, status_code=202)
        logger.warning("trace async enqueue failed cid_count=%s: %s", cid_count, err)

    if not is_msd and cid_count > TRACE_EVENTS_CID_LIMIT:
        logger.warning(
            "trace events CID limit exceeded profile=%s cid_count=%s limit=%s",
            profile, cid_count, TRACE_EVENTS_CID_LIMIT,
        )
        return _error(
            "CID_LIMIT_EXCEEDED",
            f"container_ids count ({cid_count}) exceeds limit ({TRACE_EVENTS_CID_LIMIT})",
            413,
        )

    if is_msd and cid_count > TRACE_EVENTS_CID_LIMIT:
        logger.warning(
            "trace events MSD large query proceeding cid_count=%s limit=%s",
            cid_count, TRACE_EVENTS_CID_LIMIT,
        )

    # For MSD profile, skip the events-level cache so that aggregation is
    # always recomputed with the current loss_reasons.  EventFetcher still
    # provides per-domain Redis caching, so raw Oracle queries are avoided.

    events_cache_key = _events_cache_key(profile, domains, container_ids)
    if not is_msd:
        cached = cache_get(events_cache_key)
        if cached is not None:
            return success_response(_ensure_events_quality_meta(cached))

    # --- MD2: RSS guard before sync execution ---
    rss_now = process_rss_mb()
    if rss_now is not None and rss_now > TRACE_SYNC_RSS_REJECT_MB:
        logger.warning(
            "trace events sync rejected due to RSS guard rss_mb=%.1f limit_mb=%.0f cid_count=%s",
            rss_now, TRACE_SYNC_RSS_REJECT_MB, cid_count,
        )
        return error_response(
            "SERVICE_UNAVAILABLE",
            "伺服器記憶體負載過高，請稍後再試",
            status_code=503,
            headers={"Retry-After": "30"},
        )

    logger.info(
        "trace events profile=%s domains=%s cid_count=%s correlation_cache_key=%s",
        profile,
        ",".join(domains),
        len(container_ids),
        payload.get("cache_key"),
    )

    # --- MD4: Stampede lock for sync path ---
    cid_hash = hashlib.md5("|".join(sorted(container_ids)).encode("utf-8")).hexdigest()
    lock_key = f"trace:events:{cid_hash}"
    lock_acquired = try_acquire_lock(lock_key, ttl_seconds=EVENTS_LOCK_TTL_SECONDS)

    if not lock_acquired:
        # Another worker is processing the same CID set — poll cache for result
        wait_start = time.monotonic()
        while (time.monotonic() - wait_start) < EVENTS_LOCK_WAIT_TIMEOUT_SECONDS:
            cached = cache_get(events_cache_key)
            if cached is not None:
                return success_response(_ensure_events_quality_meta(cached))
            time.sleep(EVENTS_LOCK_POLL_INTERVAL_SECONDS)

        logger.warning(
            "trace events stampede lock wait timeout; proceeding with fail-open execution "
            "cid_hash=%s cid_count=%s",
            cid_hash[:12], cid_count,
        )

    try:
        # Double-check cache after acquiring lock
        if lock_acquired:
            cached = cache_get(events_cache_key)
            if cached is not None:
                return success_response(_ensure_events_quality_meta(cached))

        started = time.monotonic()
        results: Dict[str, Dict[str, Any]] = {}
        raw_domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        failed_domains: List[str] = []
        domain_quality_meta: Dict[str, Dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=min(len(domains), TRACE_EVENTS_MAX_WORKERS)) as executor:
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
                    # Non-MSD: events_by_cid goes out of scope here, no double retention
                except Exception as exc:
                    logger.error("events stage domain failed domain=%s: %s", domain, exc, exc_info=True)
                    failed_domains.append(domain)
                    failed_meta = build_quality_meta(
                        status=QUALITY_STATUS_FAILED,
                        scope=QUALITY_SCOPE_DOMAIN,
                        domain=domain,
                        reasons=["domain_fetch_failed"],
                    )
                    results[domain] = {
                        "data": [],
                        "count": 0,
                        "quality_meta": failed_meta,
                    }
                    domain_quality_meta[domain] = failed_meta

        elapsed = time.monotonic() - started
        if elapsed > TRACE_SLOW_THRESHOLD_SECONDS:
            logger.warning("trace events slow elapsed=%.2fs domains=%s", elapsed, ",".join(domains))

        # --- MD2: RSS guard before aggregation computation ---
        aggregation = None
        if profile == PROFILE_MID_SECTION_DEFECT:
            rss_before_agg = process_rss_mb()
            if rss_before_agg is not None and rss_before_agg > TRACE_SYNC_RSS_REJECT_MB:
                del raw_domain_results
                logger.warning(
                    "trace events aggregation rejected due to RSS guard rss_mb=%.1f limit_mb=%.0f",
                    rss_before_agg, TRACE_SYNC_RSS_REJECT_MB,
                )
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "伺服器記憶體負載過高，無法完成聚合計算，請稍後再試",
                    status_code=503,
                    headers={"Retry-After": "30"},
                )

            aggregation, agg_error = _build_msd_aggregation(
                payload,
                raw_domain_results,
                domain_quality_meta=domain_quality_meta,
            )
            del raw_domain_results
            if agg_error is not None:
                code, message, status = agg_error
                return _error(code, message, status)
        else:
            del raw_domain_results

        query_quality_meta = merge_quality_metas(
            domain_quality_meta.values(),
            scope=QUALITY_SCOPE_QUERY,
        )

        response: Dict[str, Any] = {
            "stage": "events",
            "results": results,
            "aggregation": aggregation,
            "quality_meta": query_quality_meta,
            "domain_quality_meta": domain_quality_meta,
        }

        if failed_domains:
            response["error"] = "one or more domains failed"
            response["code"] = "EVENTS_PARTIAL_FAILURE"
            response["failed_domains"] = sorted(failed_domains)

        if not is_msd and len(container_ids) <= 10000:
            cache_set(events_cache_key, response, ttl=TRACE_CACHE_TTL_SECONDS)

        if len(container_ids) > 10000:
            gc.collect()

        return success_response(response)
    finally:
        if lock_acquired:
            release_lock(lock_key)


@trace_bp.route("/job/<job_id>", methods=["GET"])
@_TRACE_JOB_RATE_LIMIT
def job_status(job_id: str):
    """Return the current status of an async trace job."""
    status = get_job_status(job_id)
    if status is None:
        return _error("JOB_NOT_FOUND", "job not found or expired", 404)
    return success_response(status)


@trace_bp.route("/job/<job_id>/result", methods=["GET"])
@_TRACE_JOB_RATE_LIMIT
def job_result(job_id: str):
    """Return the result of a completed async trace job."""
    status = get_job_status(job_id)
    if status is None:
        return _error("JOB_NOT_FOUND", "job not found or expired", 404)

    if status["status"] not in ("finished",):
        return error_response(
            "JOB_NOT_COMPLETE",
            "job has not completed yet",
            status_code=409,
            meta={"job_status": status["status"]},
        )

    domain = request.args.get("domain")
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 0, type=int)

    result = get_job_result(job_id, domain=domain, offset=offset, limit=limit)
    if result is None:
        return _error("JOB_RESULT_EXPIRED", "job result has expired", 404)

    return success_response(result)


@trace_bp.route("/job/<job_id>/stream", methods=["GET"])
@_TRACE_JOB_RATE_LIMIT
def job_stream(job_id: str):
    """Stream completed job result as NDJSON for progressive frontend consumption."""
    status = get_job_status(job_id)
    if status is None:
        return _error("JOB_NOT_FOUND", "job not found or expired", 404)

    if status["status"] != "finished":
        return error_response(
            "JOB_NOT_COMPLETE",
            "job has not completed yet",
            status_code=409,
            meta={"job_status": status["status"]},
        )

    return Response(
        stream_job_result_ndjson(job_id),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
