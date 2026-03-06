# -*- coding: utf-8 -*-
"""Reusable partial-failure metadata helpers.

Normalizes the cross-tool semantics used by high-volume query paths:
- has_partial_failure
- failed_chunk_count
- failed_ranges
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional


_TRUTHY = {"1", "true", "yes", "on"}


def normalize_failed_ranges(raw_ranges: Optional[Iterable[Any]]) -> List[Dict[str, str]]:
    """Normalize failed-range list to [{"start": "...", "end": "..."}]."""
    normalized: List[Dict[str, str]] = []
    for item in raw_ranges or []:
        if not isinstance(item, dict):
            continue
        start = str(item.get("start", "")).strip()
        end = str(item.get("end", "")).strip()
        if start and end:
            normalized.append({"start": start, "end": end})
    return normalized


def build_partial_failure_meta(
    failed_count: int = 0,
    failed_ranges: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build normalized partial-failure metadata dict."""
    try:
        normalized_count = max(int(failed_count), 0)
    except Exception:
        normalized_count = 0
    normalized_ranges = normalize_failed_ranges(failed_ranges)
    has_partial = normalized_count > 0 or bool(normalized_ranges)
    return {
        "has_partial_failure": has_partial,
        "failed_chunk_count": normalized_count,
        "failed_ranges": normalized_ranges,
    }


def parse_partial_failure_meta(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse partial-failure metadata from raw storage/progress dict."""
    if not isinstance(raw, dict):
        return {}

    raw_has_partial = str(raw.get("has_partial_failure", "")).strip().lower()
    raw_failed_count = raw.get("failed_chunk_count", raw.get("failed", 0))

    raw_ranges = raw.get("failed_ranges")
    if isinstance(raw_ranges, str):
        try:
            raw_ranges = json.loads(raw_ranges) if raw_ranges else []
        except Exception:
            raw_ranges = []

    parsed = build_partial_failure_meta(
        failed_count=raw_failed_count,
        failed_ranges=raw_ranges if isinstance(raw_ranges, list) else [],
    )
    if raw_has_partial in _TRUTHY:
        parsed["has_partial_failure"] = True

    if not parsed["has_partial_failure"]:
        return {}
    return parsed


def serialize_partial_failure_meta(meta: Dict[str, Any]) -> Dict[str, str]:
    """Serialize normalized meta to Redis hash mapping strings."""
    parsed = parse_partial_failure_meta(meta)
    if not parsed:
        return {
            "has_partial_failure": "False",
            "failed_chunk_count": "0",
            "failed_ranges": "[]",
        }
    return {
        "has_partial_failure": "True",
        "failed_chunk_count": str(parsed.get("failed_chunk_count", 0)),
        "failed_ranges": json.dumps(
            parsed.get("failed_ranges", []),
            ensure_ascii=False,
            default=str,
        ),
    }


def merge_partial_failure_meta(metas: Iterable[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Merge multiple partial-failure metadata dicts."""
    merged_count = 0
    merged_ranges: List[Dict[str, str]] = []
    has_partial = False

    for meta in metas:
        parsed = parse_partial_failure_meta(meta if isinstance(meta, dict) else {})
        if not parsed:
            continue
        has_partial = True
        merged_count += int(parsed.get("failed_chunk_count") or 0)
        merged_ranges.extend(parsed.get("failed_ranges") or [])

    normalized = build_partial_failure_meta(
        failed_count=merged_count,
        failed_ranges=merged_ranges,
    )
    if has_partial:
        normalized["has_partial_failure"] = True
    return normalized if normalized["has_partial_failure"] else {}
