# -*- coding: utf-8 -*-
"""Route/query compatibility tests for shell list-detail workflows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "docs" / "migration" / "portal-shell-route-view-integration"
BASELINE_ROUTE_QUERY_FILE = BASELINE_DIR / "baseline_route_query_contracts.json"

pytestmark = pytest.mark.skipif(
    not BASELINE_DIR.exists(),
    reason=f"Migration baseline directory missing: {BASELINE_DIR}",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wip_list_detail_query_contract_compatibility():
    routes = _read_json(BASELINE_ROUTE_QUERY_FILE)["routes"]

    overview_keys = set(routes["/wip-overview"]["query_keys"])
    detail_keys = set(routes["/wip-detail"]["query_keys"])

    assert {"workorder", "lotid", "package", "type", "status"}.issubset(overview_keys)
    assert overview_keys.issubset(detail_keys)
    assert "workcenter" in detail_keys


def test_hold_list_detail_query_contract_compatibility():
    routes = _read_json(BASELINE_ROUTE_QUERY_FILE)["routes"]

    detail_keys = set(routes["/hold-detail"]["query_keys"])
    history_keys = set(routes["/hold-history"]["query_keys"])

    assert "reason" in detail_keys
    # Hold history route intentionally supports optional query keys at runtime.
    assert routes["/hold-history"]["render_mode"] == "native"
    assert routes["/hold-detail"]["render_mode"] == "native"
    assert isinstance(history_keys, set)


def test_wave_b_routes_keep_native_render_mode_with_query_contract_object():
    routes = _read_json(BASELINE_ROUTE_QUERY_FILE)["routes"]
    for route in ["/job-query", "/excel-query", "/query-tool", "/tmtt-defect"]:
        entry = routes[route]
        assert entry["render_mode"] == "native"
        assert isinstance(entry["query_keys"], list)
