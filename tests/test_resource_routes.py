# -*- coding: utf-8 -*-
"""Tests for resource route helpers and safeguards."""

from __future__ import annotations


def test_clean_nan_values_handles_deep_nesting_without_recursion_error():
    from mes_dashboard.routes.resource_routes import _clean_nan_values

    payload = current = {}
    for _ in range(2500):
        nxt = {}
        current["next"] = nxt
        current = nxt
    current["value"] = float("nan")

    cleaned = _clean_nan_values(payload)
    cursor = cleaned
    for _ in range(2500):
        cursor = cursor["next"]
    assert cursor["value"] is None


def test_clean_nan_values_breaks_cycles_safely():
    from mes_dashboard.routes.resource_routes import _clean_nan_values

    payload = {"name": "root"}
    payload["self"] = payload

    cleaned = _clean_nan_values(payload)
    assert cleaned["name"] == "root"
    assert cleaned["self"] is None
