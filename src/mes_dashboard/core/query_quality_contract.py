# -*- coding: utf-8 -*-
"""Shared query-quality metadata contract helpers.

This module standardizes how high-volume query paths report result
completeness (complete / partial / truncated / failed) and provides
adapters for legacy payload shapes.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


QUALITY_STATUS_COMPLETE = "complete"
QUALITY_STATUS_TRUNCATED = "truncated"
QUALITY_STATUS_PARTIAL = "partial"
QUALITY_STATUS_FAILED = "failed"

QUALITY_SCOPE_DOMAIN = "domain"
QUALITY_SCOPE_QUERY = "query"
QUALITY_SCOPE_EXPORT = "export"

_VALID_STATUSES = {
    QUALITY_STATUS_COMPLETE,
    QUALITY_STATUS_TRUNCATED,
    QUALITY_STATUS_PARTIAL,
    QUALITY_STATUS_FAILED,
}

_VALID_SCOPES = {
    QUALITY_SCOPE_DOMAIN,
    QUALITY_SCOPE_QUERY,
    QUALITY_SCOPE_EXPORT,
}

_STATUS_PRIORITY = {
    QUALITY_STATUS_COMPLETE: 0,
    QUALITY_STATUS_TRUNCATED: 1,
    QUALITY_STATUS_PARTIAL: 2,
    QUALITY_STATUS_FAILED: 3,
}


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _dedupe_str_list(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in values:
        text = _as_str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def build_quality_meta(
    *,
    status: str = QUALITY_STATUS_COMPLETE,
    scope: str = QUALITY_SCOPE_QUERY,
    reasons: Optional[Iterable[Any]] = None,
    domain: Optional[str] = None,
    observed_rows: Optional[int] = None,
    max_rows: Optional[int] = None,
    failed_domains: Optional[Iterable[Any]] = None,
    truncated_domains: Optional[Iterable[Any]] = None,
    failed_ranges: Optional[List[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a normalized quality metadata payload."""
    normalized_status = _as_str(status).lower()
    if normalized_status not in _VALID_STATUSES:
        normalized_status = QUALITY_STATUS_COMPLETE

    normalized_scope = _as_str(scope).lower()
    if normalized_scope not in _VALID_SCOPES:
        normalized_scope = QUALITY_SCOPE_QUERY

    meta: Dict[str, Any] = {
        "status": normalized_status,
        "scope": normalized_scope,
        "reasons": _dedupe_str_list(reasons or []),
    }

    domain_name = _as_str(domain)
    if domain_name:
        meta["domain"] = domain_name

    observed = _as_int(observed_rows)
    if observed is not None:
        meta["observed_rows"] = observed

    limit = _as_int(max_rows)
    if limit is not None:
        meta["max_rows"] = limit

    failed = _dedupe_str_list(failed_domains or [])
    if failed:
        meta["failed_domains"] = failed

    truncated = _dedupe_str_list(truncated_domains or [])
    if truncated:
        meta["truncated_domains"] = truncated

    normalized_ranges: List[Dict[str, str]] = []
    for item in failed_ranges or []:
        if not isinstance(item, dict):
            continue
        start = _as_str(item.get("start"))
        end = _as_str(item.get("end"))
        if start and end:
            normalized_ranges.append({"start": start, "end": end})
    if normalized_ranges:
        meta["failed_ranges"] = normalized_ranges

    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in {"status", "scope", "reasons"}:
                continue
            if value is not None:
                meta[key] = value

    return meta


def normalize_quality_meta(
    meta: Optional[Dict[str, Any]],
    *,
    default_scope: str = QUALITY_SCOPE_QUERY,
    default_status: str = QUALITY_STATUS_COMPLETE,
) -> Dict[str, Any]:
    """Normalize potentially missing/partial quality metadata."""
    if not isinstance(meta, dict):
        return build_quality_meta(status=default_status, scope=default_scope)

    return build_quality_meta(
        status=_as_str(meta.get("status") or default_status),
        scope=_as_str(meta.get("scope") or default_scope),
        reasons=meta.get("reasons") or [],
        domain=meta.get("domain"),
        observed_rows=meta.get("observed_rows"),
        max_rows=meta.get("max_rows"),
        failed_domains=meta.get("failed_domains") or [],
        truncated_domains=meta.get("truncated_domains") or [],
        failed_ranges=meta.get("failed_ranges") or [],
        extra={
            k: v
            for k, v in meta.items()
            if k
            not in {
                "status",
                "scope",
                "reasons",
                "domain",
                "observed_rows",
                "max_rows",
                "failed_domains",
                "truncated_domains",
                "failed_ranges",
            }
        },
    )


def merge_quality_metas(
    metas: Iterable[Optional[Dict[str, Any]]],
    *,
    scope: str = QUALITY_SCOPE_QUERY,
) -> Dict[str, Any]:
    """Merge multiple quality metadata dicts into one summary."""
    normalized = [
        normalize_quality_meta(meta, default_scope=scope)
        for meta in metas
        if meta is not None
    ]
    if not normalized:
        return build_quality_meta(status=QUALITY_STATUS_COMPLETE, scope=scope)

    merged_status = QUALITY_STATUS_COMPLETE
    reasons: List[str] = []
    failed_domains: List[str] = []
    truncated_domains: List[str] = []
    failed_ranges: List[Dict[str, str]] = []

    for meta in normalized:
        status = _as_str(meta.get("status")).lower() or QUALITY_STATUS_COMPLETE
        if _STATUS_PRIORITY.get(status, -1) > _STATUS_PRIORITY.get(merged_status, -1):
            merged_status = status
        reasons.extend(meta.get("reasons") or [])

        domain = _as_str(meta.get("domain"))
        if status == QUALITY_STATUS_FAILED and domain:
            failed_domains.append(domain)
        if status == QUALITY_STATUS_TRUNCATED and domain:
            truncated_domains.append(domain)

        failed_domains.extend(meta.get("failed_domains") or [])
        truncated_domains.extend(meta.get("truncated_domains") or [])
        for item in meta.get("failed_ranges") or []:
            if isinstance(item, dict):
                failed_ranges.append(item)

    reasons = _dedupe_str_list(reasons)
    failed_domains = _dedupe_str_list(failed_domains)
    truncated_domains = _dedupe_str_list(truncated_domains)

    # Query-level semantics: any failed domain means partial.
    if failed_domains and scope == QUALITY_SCOPE_QUERY:
        merged_status = QUALITY_STATUS_PARTIAL
        if "domain_failure" not in reasons:
            reasons.append("domain_failure")

    return build_quality_meta(
        status=merged_status,
        scope=scope,
        reasons=reasons,
        failed_domains=failed_domains,
        truncated_domains=truncated_domains,
        failed_ranges=failed_ranges,
    )


def sanitize_records_by_cid(payload: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Keep only valid `cid -> list[dict]` records."""
    if not isinstance(payload, dict):
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, records in payload.items():
        cid = _as_str(key)
        if not cid:
            continue
        if not isinstance(records, list):
            continue
        rows = [row for row in records if isinstance(row, dict)]
        out[cid] = rows
    return out


def build_event_fetch_result(
    records_by_cid: Dict[str, List[Dict[str, Any]]],
    quality_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the normalized EventFetcher payload shape."""
    return {
        "records_by_cid": sanitize_records_by_cid(records_by_cid),
        "quality_meta": normalize_quality_meta(
            quality_meta,
            default_scope=QUALITY_SCOPE_DOMAIN,
        ),
    }


def adapt_legacy_event_map(
    payload: Dict[str, Any],
    *,
    domain: Optional[str] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Adapt legacy EventFetcher map payload (`__meta__` mixed with rows)."""
    records_payload = {k: v for k, v in payload.items() if k != "__meta__"}
    records_by_cid = sanitize_records_by_cid(records_payload)

    raw_meta = payload.get("__meta__") if isinstance(payload, dict) else None
    if not isinstance(raw_meta, dict):
        quality_meta = build_quality_meta(
            status=QUALITY_STATUS_COMPLETE,
            scope=QUALITY_SCOPE_DOMAIN,
            domain=domain,
        )
        return records_by_cid, quality_meta

    truncated = str(raw_meta.get("truncated", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    reasons: List[str] = []
    status = QUALITY_STATUS_COMPLETE
    if truncated:
        status = QUALITY_STATUS_TRUNCATED
        reasons.append("max_total_rows_exceeded")

    quality_meta = build_quality_meta(
        status=status,
        scope=QUALITY_SCOPE_DOMAIN,
        domain=domain,
        reasons=reasons,
        observed_rows=raw_meta.get("total_rows_fetched"),
        max_rows=raw_meta.get("max_total_rows"),
    )
    return records_by_cid, quality_meta


def unpack_event_fetch_result(
    payload: Any,
    *,
    domain: Optional[str] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Unpack EventFetcher payload with backward compatibility.

    Supports:
    - New shape: {"records_by_cid": {...}, "quality_meta": {...}}
    - Legacy shape: {"CID-1": [...], "__meta__": {...}}
    - Legacy/no-meta shape: {"CID-1": [...]} (treated as complete)
    """
    if isinstance(payload, dict) and "records_by_cid" in payload:
        records_by_cid = sanitize_records_by_cid(payload.get("records_by_cid"))
        quality_meta = normalize_quality_meta(
            payload.get("quality_meta"),
            default_scope=QUALITY_SCOPE_DOMAIN,
        )
        if domain and not _as_str(quality_meta.get("domain")):
            quality_meta["domain"] = _as_str(domain)
        return records_by_cid, quality_meta

    if isinstance(payload, dict):
        return adapt_legacy_event_map(payload, domain=domain)

    return {}, build_quality_meta(
        status=QUALITY_STATUS_COMPLETE,
        scope=QUALITY_SCOPE_DOMAIN,
        domain=domain,
    )

