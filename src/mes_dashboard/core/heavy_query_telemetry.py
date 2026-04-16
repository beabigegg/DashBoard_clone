# -*- coding: utf-8 -*-
"""Process-local telemetry counters for heavy-query guard behavior.

Tracks guard rejects, memory errors, async fallbacks, and — for the
cache-plane architecture — spool hit/miss rates and result-lifecycle
failures across all heavy-query domains.
"""

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
        "spool_hit_total": 0,
        "spool_miss_total": 0,
        "lifecycle_failure_total": 0,
    }
)
_ROUTE_REJECTS = Counter()
_ROUTE_MEMORY_ERRORS = Counter()
_ROUTE_ASYNC_FALLBACKS = Counter()
_REJECT_REASONS = Counter()
_MEMORY_ERROR_REASONS = Counter()
_ASYNC_FALLBACK_REASONS = Counter()

# Spool hit/miss counters keyed by domain
_DOMAIN_SPOOL_HITS = Counter()
_DOMAIN_SPOOL_MISSES = Counter()
_DOMAIN_LIFECYCLE_FAILURES = Counter()
_LIFECYCLE_FAILURE_REASONS = Counter()

# Lock fail-mode trigger counters: mes.lock.fail_mode_triggered{name=<lock>,mode=<mode>}
_LOCK_FAIL_MODE_TOTAL = 0
_LOCK_FAIL_MODE_BY_NAME_MODE: Counter = Counter()


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


def record_spool_hit(domain: str, query_id: str = "") -> None:
    """Record a spool cache hit for a heavy-query domain."""
    domain_name = _normalize_token(domain, default="unknown_domain")
    with _LOCK:
        _COUNTERS["spool_hit_total"] += 1
        _DOMAIN_SPOOL_HITS[domain_name] += 1


def record_spool_miss(domain: str, query_id: str = "") -> None:
    """Record a spool cache miss for a heavy-query domain."""
    domain_name = _normalize_token(domain, default="unknown_domain")
    with _LOCK:
        _COUNTERS["spool_miss_total"] += 1
        _DOMAIN_SPOOL_MISSES[domain_name] += 1


def record_lock_fail_mode_triggered(lock_name: str, mode: str) -> None:
    """Record that a distributed lock's fail-mode branch was triggered.

    Increments ``mes.lock.fail_mode_triggered{name=<lock>,mode=<mode>}``.
    Called whenever Redis is unavailable or raises during lock acquisition.
    """
    global _LOCK_FAIL_MODE_TOTAL
    key = f"{lock_name}:{mode}"
    with _LOCK:
        _LOCK_FAIL_MODE_TOTAL += 1
        _LOCK_FAIL_MODE_BY_NAME_MODE[key] += 1


def record_lifecycle_failure(domain: str, reason: str = "unknown") -> None:
    """Record a result-lifecycle failure (expired, corrupt, runtime error)."""
    domain_name = _normalize_token(domain, default="unknown_domain")
    reason_name = _normalize_token(reason, default="unknown")
    with _LOCK:
        _COUNTERS["lifecycle_failure_total"] += 1
        _DOMAIN_LIFECYCLE_FAILURES[domain_name] += 1
        _LIFECYCLE_FAILURE_REASONS[reason_name] += 1


def get_heavy_query_telemetry() -> Dict[str, Any]:
    with _LOCK:
        return {
            "guard_reject_total": int(_COUNTERS["guard_reject_total"]),
            "memory_error_total": int(_COUNTERS["memory_error_total"]),
            "async_fallback_total": int(_COUNTERS["async_fallback_total"]),
            "spool_hit_total": int(_COUNTERS["spool_hit_total"]),
            "spool_miss_total": int(_COUNTERS["spool_miss_total"]),
            "lifecycle_failure_total": int(_COUNTERS["lifecycle_failure_total"]),
            "route_rejects": _counter_rows(_ROUTE_REJECTS, "route"),
            "route_memory_errors": _counter_rows(_ROUTE_MEMORY_ERRORS, "route"),
            "route_async_fallbacks": _counter_rows(_ROUTE_ASYNC_FALLBACKS, "route"),
            "reject_reasons": _counter_rows(_REJECT_REASONS, "reason"),
            "memory_error_reasons": _counter_rows(_MEMORY_ERROR_REASONS, "reason"),
            "async_fallback_reasons": _counter_rows(_ASYNC_FALLBACK_REASONS, "reason"),
            "domain_spool_hits": _counter_rows(_DOMAIN_SPOOL_HITS, "domain"),
            "domain_spool_misses": _counter_rows(_DOMAIN_SPOOL_MISSES, "domain"),
            "domain_lifecycle_failures": _counter_rows(_DOMAIN_LIFECYCLE_FAILURES, "domain"),
            "lifecycle_failure_reasons": _counter_rows(_LIFECYCLE_FAILURE_REASONS, "reason"),
            "lock_fail_mode_triggered_total": int(_LOCK_FAIL_MODE_TOTAL),
            "lock_fail_mode_triggered": _counter_rows(_LOCK_FAIL_MODE_BY_NAME_MODE, "lock_mode"),
        }


def reset_heavy_query_telemetry() -> None:
    global _LOCK_FAIL_MODE_TOTAL
    with _LOCK:
        _COUNTERS.clear()
        _COUNTERS.update(
            {
                "guard_reject_total": 0,
                "memory_error_total": 0,
                "async_fallback_total": 0,
                "spool_hit_total": 0,
                "spool_miss_total": 0,
                "lifecycle_failure_total": 0,
            }
        )
        _ROUTE_REJECTS.clear()
        _ROUTE_MEMORY_ERRORS.clear()
        _ROUTE_ASYNC_FALLBACKS.clear()
        _REJECT_REASONS.clear()
        _MEMORY_ERROR_REASONS.clear()
        _ASYNC_FALLBACK_REASONS.clear()
        _DOMAIN_SPOOL_HITS.clear()
        _DOMAIN_SPOOL_MISSES.clear()
        _DOMAIN_LIFECYCLE_FAILURES.clear()
        _LIFECYCLE_FAILURE_REASONS.clear()
        _LOCK_FAIL_MODE_TOTAL = 0
        _LOCK_FAIL_MODE_BY_NAME_MODE.clear()
