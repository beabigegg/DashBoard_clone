# -*- coding: utf-8 -*-
"""Worker restart policy helpers (cooldown, retry budget, churn guard)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mes_dashboard.core.runtime_contract import load_runtime_contract


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def get_worker_recovery_policy_config() -> dict[str, Any]:
    """Return effective worker restart policy config."""
    retry_budget = _env_int("WORKER_RESTART_RETRY_BUDGET", 3)
    churn_threshold = _env_int(
        "WORKER_RESTART_CHURN_THRESHOLD",
        _env_int("RESILIENCE_RESTART_CHURN_THRESHOLD", retry_budget),
    )
    window_seconds = _env_int(
        "WORKER_RESTART_WINDOW_SECONDS",
        _env_int("RESILIENCE_RESTART_CHURN_WINDOW_SECONDS", 600),
    )
    return {
        "cooldown_seconds": max(_env_int("WORKER_RESTART_COOLDOWN", 60), 1),
        "retry_budget": max(retry_budget, 1),
        "window_seconds": max(window_seconds, 30),
        "churn_threshold": max(churn_threshold, 1),
        "guarded_mode_enabled": _env_bool("WORKER_GUARDED_MODE_ENABLED", True),
    }


def load_restart_state(path: str | None = None) -> dict[str, Any]:
    """Load persisted restart state from runtime contract state file."""
    state_path = Path(path or load_runtime_contract()["watchdog_state_file"])
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except (json.JSONDecodeError, IOError):
        return {}


def extract_restart_history(state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Extract bounded restart history from persisted state."""
    payload = dict(state or {})
    raw_history = payload.get("history")
    if not isinstance(raw_history, list):
        return []
    return [item for item in raw_history if isinstance(item, dict)][-50:]


def extract_last_requested_at(state: Mapping[str, Any] | None = None) -> str | None:
    """Extract last requested timestamp from persisted state."""
    payload = dict(state or {})
    last_restart = payload.get("last_restart") or {}
    if not isinstance(last_restart, dict):
        return None
    value = last_restart.get("requested_at")
    return str(value) if value else None


def evaluate_worker_recovery_state(
    history: list[dict[str, Any]] | None,
    *,
    last_requested_at: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate restart policy state for automated/manual recovery decisions."""
    cfg = get_worker_recovery_policy_config()
    now_dt = now or _utc_now()
    window_seconds = int(cfg["window_seconds"])
    cooldown_seconds = int(cfg["cooldown_seconds"])

    recent_attempts = 0
    for item in history or []:
        requested = _parse_iso(item.get("requested_at"))
        completed = _parse_iso(item.get("completed_at"))
        ts = requested or completed
        if ts is None:
            continue
        age = (now_dt - ts).total_seconds()
        if age <= window_seconds:
            recent_attempts += 1

    retry_budget = int(cfg["retry_budget"])
    churn_threshold = int(cfg["churn_threshold"])
    retry_budget_exhausted = recent_attempts >= retry_budget
    churn_exceeded = recent_attempts >= churn_threshold
    guarded_mode = bool(cfg["guarded_mode_enabled"] and (retry_budget_exhausted or churn_exceeded))

    cooldown_active = False
    cooldown_remaining = 0
    last_requested_dt = _parse_iso(last_requested_at)
    if last_requested_dt is not None:
        elapsed = (now_dt - last_requested_dt).total_seconds()
        if elapsed < cooldown_seconds:
            cooldown_active = True
            cooldown_remaining = int(max(cooldown_seconds - elapsed, 0))

    blocked = guarded_mode
    allowed = not blocked and not cooldown_active

    state = "allowed"
    if blocked:
        state = "blocked"
    elif cooldown_active:
        state = "cooldown"

    return {
        "state": state,
        "allowed": allowed,
        "cooldown": cooldown_active,
        "cooldown_remaining_seconds": cooldown_remaining,
        "blocked": blocked,
        "guarded_mode": guarded_mode,
        "retry_budget_exhausted": retry_budget_exhausted,
        "churn_exceeded": churn_exceeded,
        "attempts_in_window": recent_attempts,
        "retry_budget": retry_budget,
        "churn_threshold": churn_threshold,
        "window_seconds": window_seconds,
        "cooldown_seconds": cooldown_seconds,
    }


def decide_restart_request(
    policy_state: Mapping[str, Any],
    *,
    source: str,
    manual_override: bool = False,
    override_acknowledged: bool = False,
) -> dict[str, Any]:
    """Decide whether restart request is allowed under current policy state."""
    state = dict(policy_state or {})
    blocked = bool(state.get("blocked"))
    cooldown = bool(state.get("cooldown"))
    source_value = (source or "manual").strip().lower()

    if source_value not in {"auto", "manual"}:
        source_value = "manual"

    if source_value == "auto":
        if blocked:
            return {
                "allowed": False,
                "decision": "blocked",
                "reason": "guarded_mode_blocked",
                "requires_acknowledgement": False,
            }
        if cooldown:
            return {
                "allowed": False,
                "decision": "blocked",
                "reason": "cooldown_active",
                "requires_acknowledgement": False,
            }
        return {
            "allowed": True,
            "decision": "allowed",
            "reason": "policy_allows_auto_restart",
            "requires_acknowledgement": False,
        }

    if (blocked or cooldown) and not (manual_override and override_acknowledged):
        reason = "manual_override_required" if blocked else "cooldown_override_required"
        return {
            "allowed": False,
            "decision": "blocked",
            "reason": reason,
            "requires_acknowledgement": True,
        }

    if manual_override and override_acknowledged:
        return {
            "allowed": True,
            "decision": "manual_override",
            "reason": "operator_override_acknowledged",
            "requires_acknowledgement": False,
        }

    return {
        "allowed": True,
        "decision": "allowed",
        "reason": "policy_allows_manual_restart",
        "requires_acknowledgement": False,
    }

