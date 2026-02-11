# -*- coding: utf-8 -*-
"""Cutover gate enforcement tests for portal no-iframe migration."""

from __future__ import annotations

import json
from pathlib import Path

from mes_dashboard.app import create_app

ROOT = Path(__file__).resolve().parents[1]
BASELINE_VISIBILITY_FILE = ROOT / "docs" / "migration" / "portal-no-iframe" / "baseline_drawer_visibility.json"
BASELINE_API_FILE = ROOT / "docs" / "migration" / "portal-no-iframe" / "baseline_api_payload_contracts.json"
ROLLBACK_RUNBOOK = ROOT / "docs" / "migration" / "portal-no-iframe" / "rollback_rehearsal_runbook.md"
ROLLBACK_STRATEGY = ROOT / "docs" / "migration" / "portal-no-iframe" / "rollback_strategy_shell_and_wrappers.md"
LEGACY_REWRITE_SMOKE_CHECKLIST = ROOT / "docs" / "migration" / "portal-no-iframe" / "legacy_rewrite_smoke_checklists.md"
STRESS_SUITE = ROOT / "tests" / "stress" / "test_frontend_stress.py"


def _login_as_admin(client) -> None:
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}


def _route_set(drawers: list[dict]) -> set[str]:
    return {
        str(page.get("route"))
        for drawer in drawers
        for page in drawer.get("pages", [])
        if page.get("route")
    }


def test_g1_route_availability_gate_p0_routes_are_2xx_or_3xx():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    p0_routes = [
        "/",
        "/portal-shell",
        "/api/portal/navigation",
        "/wip-overview",
        "/resource",
        "/qc-gate",
    ]

    statuses = [client.get(route).status_code for route in p0_routes]
    assert all(200 <= status < 400 for status in statuses), statuses


def test_g2_drawer_parity_gate_matches_baseline_for_admin_and_non_admin():
    baseline = json.loads(BASELINE_VISIBILITY_FILE.read_text(encoding="utf-8"))

    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    non_admin_payload = json.loads(non_admin_client.get("/api/portal/navigation").data.decode("utf-8"))

    admin_client = app.test_client()
    _login_as_admin(admin_client)
    admin_payload = json.loads(admin_client.get("/api/portal/navigation").data.decode("utf-8"))

    assert _route_set(non_admin_payload["drawers"]) == _route_set(baseline["non_admin"])
    assert _route_set(admin_payload["drawers"]) == _route_set(baseline["admin"])


def test_g3_workflow_smoke_gate_critical_routes_reachable_for_admin():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    smoke_routes = [
        "/",
        "/wip-overview",
        "/wip-detail?workcenter=TMTT&type=PJA3460&status=queue",
        "/hold-detail?reason=YieldLimit",
        "/hold-overview",
        "/hold-history",
        "/resource",
        "/resource-history?start_date=2026-01-01&end_date=2026-01-31",
        "/qc-gate",
        "/job-query",
        "/excel-query",
        "/query-tool",
        "/tmtt-defect",
    ]

    statuses = [client.get(route).status_code for route in smoke_routes]
    assert all(200 <= status < 400 for status in statuses), statuses


def test_g4_client_stability_gate_assertion_present_in_stress_suite():
    content = STRESS_SUITE.read_text(encoding="utf-8")
    assert 'page.on("pageerror"' in content
    assert 'assert len(js_errors) == 0' in content


def test_g5_data_contract_gate_baseline_keys_are_defined_for_registered_apis():
    baseline = json.loads(BASELINE_API_FILE.read_text(encoding="utf-8"))
    app = create_app("testing")
    app.config["TESTING"] = True
    registered_routes = {rule.rule for rule in app.url_map.iter_rules()}

    for api_route, contract in baseline.get("apis", {}).items():
        assert api_route in registered_routes, f"Missing API route in app map: {api_route}"
        required_keys = contract.get("required_keys", [])
        assert required_keys, f"No required_keys defined for {api_route}"
        assert all(isinstance(key, str) and key for key in required_keys)


def test_g7_rollback_readiness_gate_has_15_minute_slo_and_operator_steps():
    rehearsal = ROLLBACK_RUNBOOK.read_text(encoding="utf-8")
    strategy = ROLLBACK_STRATEGY.read_text(encoding="utf-8")

    assert "15" in rehearsal
    assert "PORTAL_SPA_ENABLED=false" in strategy
    assert "/api/portal/navigation" in strategy


def test_legacy_rewrite_smoke_checklist_covers_all_wrapped_pages():
    content = LEGACY_REWRITE_SMOKE_CHECKLIST.read_text(encoding="utf-8")

    assert "tmtt-defect" in content
    assert "job-query" in content
    assert "excel-query" in content
    assert "query-tool" in content
    assert "SMOKE-01" in content
