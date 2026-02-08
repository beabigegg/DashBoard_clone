# -*- coding: utf-8 -*-
"""Runtime resilience thresholds and operator recommendation helpers."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        value = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_resilience_thresholds() -> dict[str, Any]:
    """Return effective resilience thresholds from environment config."""
    return {
        "degraded_alert_seconds": _env_int("RESILIENCE_DEGRADED_ALERT_SECONDS", 300),
        "pool_saturation_warning": _env_float("RESILIENCE_POOL_SATURATION_WARNING", 0.90),
        "pool_saturation_critical": _env_float("RESILIENCE_POOL_SATURATION_CRITICAL", 1.0),
        "restart_churn_window_seconds": _env_int("RESILIENCE_RESTART_CHURN_WINDOW_SECONDS", 600),
        "restart_churn_threshold": _env_int("RESILIENCE_RESTART_CHURN_THRESHOLD", 3),
    }


def summarize_restart_history(
    history: list[dict[str, Any]] | None,
    *,
    now: datetime | None = None,
    window_seconds: int | None = None,
    threshold: int | None = None,
) -> dict[str, Any]:
    """Summarize restart churn for recent watchdog-triggered restarts."""
    values = history or []
    thresholds = get_resilience_thresholds()
    active_window = int(
        window_seconds
        if window_seconds is not None
        else thresholds["restart_churn_window_seconds"]
    )
    active_threshold = int(
        threshold
        if threshold is not None
        else thresholds["restart_churn_threshold"]
    )
    now_dt = now or _utc_now()

    in_window_count = 0
    last_completed = None
    for item in values:
        completed_at = _parse_iso(item.get("completed_at"))
        if completed_at is None:
            continue
        last_completed = max(last_completed, completed_at) if last_completed else completed_at
        age = (now_dt - completed_at).total_seconds()
        if age <= active_window:
            in_window_count += 1

    return {
        "window_seconds": active_window,
        "threshold": active_threshold,
        "count": in_window_count,
        "exceeded": in_window_count >= active_threshold,
        "last_completed_at": last_completed.isoformat() if last_completed else None,
    }


def build_recovery_recommendation(
    *,
    degraded_reason: str | None,
    pool_saturation: float | None,
    circuit_state: str | None,
    restart_churn_exceeded: bool,
    cooldown_active: bool = False,
) -> dict[str, Any]:
    """Build machine-readable operator recommendation for degraded conditions."""
    if degraded_reason is None:
        return {
            "action": "none",
            "reason": "healthy",
        }

    if degraded_reason == "database_unreachable":
        return {
            "action": "check_database_connectivity",
            "reason": "database_unreachable",
        }

    if degraded_reason == "redis_unavailable":
        return {
            "action": "continue_degraded_mode",
            "reason": "redis_unavailable",
        }

    if circuit_state == "OPEN":
        return {
            "action": "wait_for_circuit_half_open",
            "reason": "circuit_breaker_open",
        }

    if degraded_reason == "db_pool_saturated":
        if restart_churn_exceeded:
            return {
                "action": "throttle_and_investigate_queries",
                "reason": "restart_churn_exceeded",
            }
        if cooldown_active:
            return {
                "action": "wait_for_restart_cooldown",
                "reason": "restart_cooldown_active",
            }
        if pool_saturation is not None and pool_saturation >= 1.0:
            return {
                "action": "consider_controlled_worker_restart",
                "reason": "db_pool_saturated",
            }

    return {
        "action": "observe_and_retry",
        "reason": degraded_reason,
    }
