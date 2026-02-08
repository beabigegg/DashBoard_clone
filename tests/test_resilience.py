# -*- coding: utf-8 -*-
"""Tests for runtime resilience helper contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mes_dashboard.core.resilience import (
    build_recovery_recommendation,
    get_resilience_thresholds,
    summarize_restart_history,
)


def test_get_resilience_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("RESILIENCE_RESTART_CHURN_WINDOW_SECONDS", "120")
    monkeypatch.setenv("RESILIENCE_RESTART_CHURN_THRESHOLD", "2")
    monkeypatch.setenv("RESILIENCE_POOL_SATURATION_WARNING", "0.8")

    thresholds = get_resilience_thresholds()
    assert thresholds["restart_churn_window_seconds"] == 120
    assert thresholds["restart_churn_threshold"] == 2
    assert thresholds["pool_saturation_warning"] == 0.8


def test_summarize_restart_history_counts_entries_in_window():
    now = datetime(2026, 2, 7, 12, 0, tzinfo=timezone.utc)
    history = [
        {"completed_at": (now - timedelta(seconds=30)).isoformat()},
        {"completed_at": (now - timedelta(seconds=90)).isoformat()},
        {"completed_at": (now - timedelta(seconds=700)).isoformat()},
    ]

    summary = summarize_restart_history(history, now=now, window_seconds=120, threshold=2)
    assert summary["count"] == 2
    assert summary["exceeded"] is True
    assert summary["window_seconds"] == 120
    assert summary["threshold"] == 2


def test_build_recovery_recommendation_for_pool_churn_and_cooldown():
    recommendation = build_recovery_recommendation(
        degraded_reason="db_pool_saturated",
        pool_saturation=1.0,
        circuit_state="CLOSED",
        restart_churn_exceeded=True,
        cooldown_active=False,
    )
    assert recommendation["action"] == "throttle_and_investigate_queries"

    cooldown_recommendation = build_recovery_recommendation(
        degraded_reason="db_pool_saturated",
        pool_saturation=1.0,
        circuit_state="CLOSED",
        restart_churn_exceeded=False,
        cooldown_active=True,
    )
    assert cooldown_recommendation["action"] == "wait_for_restart_cooldown"
