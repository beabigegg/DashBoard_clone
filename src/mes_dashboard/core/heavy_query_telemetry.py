# -*- coding: utf-8 -*-
"""Process-local telemetry counters for heavy-query guard behavior."""

from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any, Dict, List

_LOCK = Lock()

_COUNTERS = Counter(
    {
        "guard_reject_total": 0,
        "memory_error_total": 0,
        "async_fallback_total": 0,
    }
)
_ROUTE_REJECTS = Counter()
_ROUTE_MEMORY_ERRORS = Counter()
_ROUTE_ASYNC_FALLBACKS = Counter()
_REJECT_REASONS = Counter()
_MEMORY_ERROR_REASONS = Counter()
_ASYNC_FALLBACK_REASONS = Counter()


def _normalize_token(value: str | None, *, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _counter_rows(counter: Counter, key_name: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, count in sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0]))):
        rows.append({key_name: key, "count": int(count)})
    return rows


def record_guard_reject(route: str, reason: str = "overload") -> None:
    route_name = _normalize_token(route, default="unknown_route")
    reason_name = _normalize_token(reason, default="unknown_reason")
    with _LOCK:
        _COUNTERS["guard_reject_total"] += 1
        _ROUTE_REJECTS[route_name] += 1
        _REJECT_REASONS[reason_name] += 1


def record_memory_error(route: str, reason: str = "memory_guard") -> None:
    route_name = _normalize_token(route, default="unknown_route")
    reason_name = _normalize_token(reason, default="unknown_reason")
    with _LOCK:
        _COUNTERS["memory_error_total"] += 1
        _ROUTE_MEMORY_ERRORS[route_name] += 1
        _MEMORY_ERROR_REASONS[reason_name] += 1


def record_async_fallback(route: str, reason: str = "rss_guard") -> None:
    route_name = _normalize_token(route, default="unknown_route")
    reason_name = _normalize_token(reason, default="unknown_reason")
    with _LOCK:
        _COUNTERS["async_fallback_total"] += 1
        _ROUTE_ASYNC_FALLBACKS[route_name] += 1
        _ASYNC_FALLBACK_REASONS[reason_name] += 1


def get_heavy_query_telemetry() -> Dict[str, Any]:
    with _LOCK:
        return {
            "guard_reject_total": int(_COUNTERS["guard_reject_total"]),
            "memory_error_total": int(_COUNTERS["memory_error_total"]),
            "async_fallback_total": int(_COUNTERS["async_fallback_total"]),
            "route_rejects": _counter_rows(_ROUTE_REJECTS, "route"),
            "route_memory_errors": _counter_rows(_ROUTE_MEMORY_ERRORS, "route"),
            "route_async_fallbacks": _counter_rows(_ROUTE_ASYNC_FALLBACKS, "route"),
            "reject_reasons": _counter_rows(_REJECT_REASONS, "reason"),
            "memory_error_reasons": _counter_rows(_MEMORY_ERROR_REASONS, "reason"),
            "async_fallback_reasons": _counter_rows(_ASYNC_FALLBACK_REASONS, "reason"),
        }


def reset_heavy_query_telemetry() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _COUNTERS.update(
            {
                "guard_reject_total": 0,
                "memory_error_total": 0,
                "async_fallback_total": 0,
            }
        )
        _ROUTE_REJECTS.clear()
        _ROUTE_MEMORY_ERRORS.clear()
        _ROUTE_ASYNC_FALLBACKS.clear()
        _REJECT_REASONS.clear()
        _MEMORY_ERROR_REASONS.clear()
        _ASYNC_FALLBACK_REASONS.clear()
