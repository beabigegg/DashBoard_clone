# -*- coding: utf-8 -*-
"""Staged trace API routes.

Provides three stage endpoints for progressive trace execution:
- seed-resolve
- lineage
- events
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import error_response
from mes_dashboard.services.event_fetcher import EventFetcher
from mes_dashboard.services.lineage_engine import LineageEngine
from mes_dashboard.services.mid_section_defect_service import (
    build_trace_aggregation_from_events,
    parse_loss_reasons_param,
    resolve_trace_seed_lots,
)
from mes_dashboard.services.query_tool_service import resolve_lots

logger = logging.getLogger("mes_dashboard.trace_routes")

trace_bp = Blueprint("trace", __name__, url_prefix="/api/trace")

TRACE_STAGE_TIMEOUT_SECONDS = 10.0
TRACE_CACHE_TTL_SECONDS = 300

PROFILE_QUERY_TOOL = "query_tool"
PROFILE_MID_SECTION_DEFECT = "mid_section_defect"
SUPPORTED_PROFILES = {PROFILE_QUERY_TOOL, PROFILE_MID_SECTION_DEFECT}

QUERY_TOOL_RESOLVE_TYPES = {"lot_id", "serial_number", "work_order"}
SUPPORTED_EVENT_DOMAINS = {
    "history",
    "materials",
    "rejects",
    "holds",
    "jobs",
    "upstream_history",
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
    return f"trace:seed:{profile}:{_hash_payload(params)}"


def _lineage_cache_key(container_ids: List[str]) -> str:
    return f"trace:lineage:{_short_hash(sorted(container_ids))}"


def _events_cache_key(profile: str, domains: List[str], container_ids: List[str]) -> str:
    domains_hash = _short_hash(sorted(domains))
    cid_hash = _short_hash(sorted(container_ids))
    return f"trace:evt:{profile}:{domains_hash}:{cid_hash}"


def _error(code: str, message: str, status_code: int = 400):
    return error_response(code, message, status_code=status_code)


def _timeout(stage: str):
    return _error(f"{stage.upper().replace('-', '_')}_TIMEOUT", f"{stage} stage exceeded timeout budget", 504)


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


def _seed_resolve_query_tool(params: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[tuple[str, str, int]]]:
    resolve_type = str(params.get("resolve_type") or params.get("input_type") or "").strip()
    if resolve_type not in QUERY_TOOL_RESOLVE_TYPES:
        return None, ("INVALID_PARAMS", "resolve_type must be lot_id/serial_number/work_order", 400)

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
    start_date, end_date = _extract_date_range(params)
    if not start_date or not end_date:
        return None, ("INVALID_PARAMS", "start_date/end_date (or date_range) is required", 400)

    result = resolve_trace_seed_lots(start_date, end_date)
    if result is None:
        return None, ("SEED_RESOLVE_FAILED", "seed resolve service unavailable", 503)
    if "error" in result:
        return None, ("SEED_RESOLVE_FAILED", str(result["error"]), 400)
    return result, None


def _build_lineage_response(container_ids: List[str], ancestors_raw: Dict[str, Any]) -> Dict[str, Any]:
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

    return {
        "stage": "lineage",
        "ancestors": normalized_ancestors,
        "merges": {},
        "total_nodes": len(all_nodes),
    }


def _flatten_domain_records(events_by_cid: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for records in events_by_cid.values():
        if not isinstance(records, list):
            continue
        for row in records:
            if isinstance(row, dict):
                rows.append(row)
    return rows


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


def _build_msd_aggregation(
    payload: Dict[str, Any],
    domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]],
) -> tuple[Optional[Dict[str, Any]], Optional[tuple[str, str, int]]]:
    params = payload.get("params")
    if not isinstance(params, dict):
        return None, ("INVALID_PARAMS", "params is required for mid_section_defect profile", 400)

    start_date, end_date = _extract_date_range(params)
    if not start_date or not end_date:
        return None, ("INVALID_PARAMS", "start_date/end_date is required in params", 400)

    raw_loss_reasons = params.get("loss_reasons")
    loss_reasons = parse_loss_reasons_param(raw_loss_reasons)

    lineage_ancestors = _parse_lineage_payload(payload)
    seed_container_ids = _normalize_strings(payload.get("seed_container_ids", []))
    if not seed_container_ids and isinstance(lineage_ancestors, dict):
        seed_container_ids = _normalize_strings(list(lineage_ancestors.keys()))

    upstream_events = domain_results.get("upstream_history", {})

    aggregation = build_trace_aggregation_from_events(
        start_date,
        end_date,
        loss_reasons=loss_reasons,
        seed_container_ids=seed_container_ids,
        lineage_ancestors=lineage_ancestors,
        upstream_events_by_cid=upstream_events,
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
        return jsonify(cached)

    request_cache_key = payload.get("cache_key")
    logger.info(
        "trace seed-resolve profile=%s correlation_cache_key=%s",
        profile,
        request_cache_key,
    )

    started = time.monotonic()
    if profile == PROFILE_QUERY_TOOL:
        resolved, route_error = _seed_resolve_query_tool(params)
    else:
        resolved, route_error = _seed_resolve_mid_section_defect(params)

    elapsed = time.monotonic() - started
    if elapsed > TRACE_STAGE_TIMEOUT_SECONDS:
        return _timeout("seed_resolve")

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
    return jsonify(response)


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

    lineage_cache_key = _lineage_cache_key(container_ids)
    cached = cache_get(lineage_cache_key)
    if cached is not None:
        return jsonify(cached)

    logger.info(
        "trace lineage profile=%s count=%s correlation_cache_key=%s",
        profile,
        len(container_ids),
        payload.get("cache_key"),
    )

    started = time.monotonic()
    try:
        ancestors_raw = LineageEngine.resolve_full_genealogy(container_ids)
    except Exception as exc:
        if _is_timeout_exception(exc):
            return _error("LINEAGE_TIMEOUT", "lineage query timed out", 504)
        logger.error("lineage stage failed: %s", exc, exc_info=True)
        return _error("LINEAGE_FAILED", "lineage stage failed", 500)

    elapsed = time.monotonic() - started
    if elapsed > TRACE_STAGE_TIMEOUT_SECONDS:
        return _error("LINEAGE_TIMEOUT", "lineage query timed out", 504)

    response = _build_lineage_response(container_ids, ancestors_raw)
    cache_set(lineage_cache_key, response, ttl=TRACE_CACHE_TTL_SECONDS)
    return jsonify(response)


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

    events_cache_key = _events_cache_key(profile, domains, container_ids)
    cached = cache_get(events_cache_key)
    if cached is not None:
        return jsonify(cached)

    logger.info(
        "trace events profile=%s domains=%s cid_count=%s correlation_cache_key=%s",
        profile,
        ",".join(domains),
        len(container_ids),
        payload.get("cache_key"),
    )

    started = time.monotonic()
    results: Dict[str, Dict[str, Any]] = {}
    raw_domain_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    failed_domains: List[str] = []

    for domain in domains:
        try:
            events_by_cid = EventFetcher.fetch_events(container_ids, domain)
            raw_domain_results[domain] = events_by_cid
            rows = _flatten_domain_records(events_by_cid)
            results[domain] = {"data": rows, "count": len(rows)}
        except Exception as exc:
            logger.error("events stage domain failed domain=%s: %s", domain, exc, exc_info=True)
            failed_domains.append(domain)

    elapsed = time.monotonic() - started
    if elapsed > TRACE_STAGE_TIMEOUT_SECONDS:
        return _error("EVENTS_TIMEOUT", "events stage timed out", 504)

    aggregation = None
    if profile == PROFILE_MID_SECTION_DEFECT:
        aggregation, agg_error = _build_msd_aggregation(payload, raw_domain_results)
        if agg_error is not None:
            code, message, status = agg_error
            return _error(code, message, status)

    response: Dict[str, Any] = {
        "stage": "events",
        "results": results,
        "aggregation": aggregation,
    }

    if failed_domains:
        response["error"] = "one or more domains failed"
        response["code"] = "EVENTS_PARTIAL_FAILURE"
        response["failed_domains"] = sorted(failed_domains)

    cache_set(events_cache_key, response, ttl=TRACE_CACHE_TTL_SECONDS)
    return jsonify(response)
