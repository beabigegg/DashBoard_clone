# -*- coding: utf-8 -*-
"""Shared guardrails for LOT/WAFER/工單 container resolution."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _normalize_wildcard_token(value: str) -> str:
    return str(value or "").replace("*", "%")


def _is_pattern_token(value: str) -> bool:
    token = _normalize_wildcard_token(value)
    return "%" in token or "_" in token


def _literal_prefix_before_wildcard(value: str) -> str:
    token = _normalize_wildcard_token(value)
    for idx, ch in enumerate(token):
        if ch in ("%", "_"):
            return token[:idx]
    return token


def normalize_input_values(values: Iterable[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for raw in values or []:
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def validate_resolution_request(input_type: str, values: Iterable[Any]) -> Optional[str]:
    """Validate resolver request without hard-capping raw input count."""
    tokens = normalize_input_values(values)
    if not tokens:
        return "請輸入至少一個查詢條件"

    # Compatibility switch. Default 0 means "no count cap".
    max_values = max(_env_int("CONTAINER_RESOLVE_INPUT_MAX_VALUES", 0), 0)
    if max_values and len(tokens) > max_values:
        return f"輸入數量超過上限 ({max_values} 筆)"

    # Wildcard safety: avoid full-table scans like "%" or "_".
    min_prefix_len = max(_env_int("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", 2), 0)
    if min_prefix_len > 0:
        invalid_patterns: List[str] = []
        for token in tokens:
            if not _is_pattern_token(token):
                continue
            if len(_literal_prefix_before_wildcard(token).strip()) < min_prefix_len:
                invalid_patterns.append(token)
        if invalid_patterns:
            sample = ", ".join(invalid_patterns[:3])
            suffix = "..." if len(invalid_patterns) > 3 else ""
            return (
                f"{input_type} 萬用字元條件過於寬鬆（需至少 {min_prefix_len} 碼前綴）: "
                f"{sample}{suffix}"
            )

    return None


def extract_container_ids(rows: Iterable[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    seen = set()
    for row in rows or []:
        cid = str(
            row.get("container_id")
            or row.get("CONTAINERID")
            or ""
        ).strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    return ids


def assess_resolution_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Assess expansion result against guardrails."""
    expansion_info = result.get("expansion_info") or {}
    max_expand_per_token = max(
        _env_int("CONTAINER_RESOLVE_MAX_EXPANSION_PER_TOKEN", 2000),
        1,
    )
    offenders: List[Dict[str, Any]] = []
    for token, count in expansion_info.items():
        try:
            c = int(count)
        except (TypeError, ValueError):
            continue
        if c > max_expand_per_token:
            offenders.append({"token": str(token), "count": c})

    unique_ids = extract_container_ids(result.get("data") or [])
    max_container_ids = max(
        _env_int("CONTAINER_RESOLVE_MAX_CONTAINER_IDS", 30000),
        1,
    )
    return {
        "max_expansion_per_token": max_expand_per_token,
        "expansion_offenders": offenders,
        "max_container_ids": max_container_ids,
        "resolved_container_ids": len(unique_ids),
        "over_container_limit": len(unique_ids) > max_container_ids,
    }


def validate_resolution_result(
    result: Dict[str, Any],
    *,
    strict: bool = True,
) -> Optional[str]:
    """Validate expansion result guardrails.

    strict=True: exceed guardrail -> return error message.
    strict=False: exceed guardrail -> allow caller to continue (split/decompose path).
    """
    assessment = assess_resolution_result(result)
    offenders = assessment.get("expansion_offenders") or []
    if offenders and strict:
        first = offenders[0]
        token = str(first.get("token") or "")
        count = int(first.get("count") or 0)
        return (
            f"單一條件展開過大 ({count} 筆，限制 {assessment['max_expansion_per_token']})，"
            f"請縮小範圍: {token}"
        )

    if bool(assessment.get("over_container_limit")) and strict:
        return (
            f"解析結果過大（{assessment['resolved_container_ids']} 筆 CONTAINERID，限制 {assessment['max_container_ids']}）"
            "，請縮小查詢條件"
        )
    return None
