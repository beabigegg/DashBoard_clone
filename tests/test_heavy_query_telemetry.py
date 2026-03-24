# -*- coding: utf-8 -*-
"""Tests for heavy_query_telemetry counters."""

from mes_dashboard.core.heavy_query_telemetry import (
    get_heavy_query_telemetry,
    record_async_fallback,
    record_guard_reject,
    record_memory_error,
    reset_heavy_query_telemetry,
)


def setup_function():
    reset_heavy_query_telemetry()


def test_records_guard_memory_and_fallback_counters():
    record_guard_reject("reject_history.query", reason="slow_query_active_threshold")
    record_guard_reject("reject_history.query", reason="slow_query_active_threshold")
    record_memory_error("material_trace.query", reason="rss_guard")
    record_async_fallback("trace.events", reason="rss_guard")

    telemetry = get_heavy_query_telemetry()
    assert telemetry["guard_reject_total"] == 2
    assert telemetry["memory_error_total"] == 1
    assert telemetry["async_fallback_total"] == 1


def test_returns_route_and_reason_breakdowns():
    record_guard_reject("yield_alert.query", reason="system_memory_pressure")
    record_guard_reject("yield_alert.query", reason="system_memory_pressure")
    record_memory_error("query_tool.lot_history", reason="rss_guard")

    telemetry = get_heavy_query_telemetry()
    assert telemetry["route_rejects"][0]["route"] == "yield_alert.query"
    assert telemetry["route_rejects"][0]["count"] == 2
    assert telemetry["reject_reasons"][0]["reason"] == "system_memory_pressure"
    assert telemetry["reject_reasons"][0]["count"] == 2
    assert telemetry["route_memory_errors"][0]["route"] == "query_tool.lot_history"
    assert telemetry["route_memory_errors"][0]["count"] == 1
