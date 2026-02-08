# -*- coding: utf-8 -*-
"""Unit tests for worker recovery policy guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mes_dashboard.core.worker_recovery_policy import (
    decide_restart_request,
    evaluate_worker_recovery_state,
)


def test_policy_enters_blocked_state_when_attempts_exceed_threshold(monkeypatch):
    monkeypatch.setenv("WORKER_RESTART_RETRY_BUDGET", "2")
    monkeypatch.setenv("WORKER_RESTART_CHURN_THRESHOLD", "2")
    monkeypatch.setenv("WORKER_RESTART_WINDOW_SECONDS", "120")
    monkeypatch.setenv("WORKER_RESTART_COOLDOWN", "10")

    now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
    history = [
        {"requested_at": (now - timedelta(seconds=30)).isoformat()},
        {"requested_at": (now - timedelta(seconds=60)).isoformat()},
    ]

    state = evaluate_worker_recovery_state(history, now=now)
    assert state["blocked"] is True
    assert state["state"] == "blocked"
    assert state["allowed"] is False


def test_policy_reports_cooldown_when_recent_request_exists(monkeypatch):
    monkeypatch.setenv("WORKER_RESTART_RETRY_BUDGET", "5")
    monkeypatch.setenv("WORKER_RESTART_CHURN_THRESHOLD", "5")
    monkeypatch.setenv("WORKER_RESTART_WINDOW_SECONDS", "300")
    monkeypatch.setenv("WORKER_RESTART_COOLDOWN", "60")

    now = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)
    last_requested = (now - timedelta(seconds=20)).isoformat()
    state = evaluate_worker_recovery_state([], last_requested_at=last_requested, now=now)
    assert state["cooldown"] is True
    assert state["state"] == "cooldown"
    assert state["cooldown_remaining_seconds"] > 0


def test_manual_override_decision_requires_acknowledgement():
    blocked_state = {
        "blocked": True,
        "cooldown": False,
    }
    denied = decide_restart_request(blocked_state, source="manual")
    assert denied["allowed"] is False
    assert denied["requires_acknowledgement"] is True

    allowed = decide_restart_request(
        blocked_state,
        source="manual",
        manual_override=True,
        override_acknowledged=True,
    )
    assert allowed["allowed"] is True
    assert allowed["decision"] == "manual_override"
