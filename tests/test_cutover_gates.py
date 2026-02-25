# -*- coding: utf-8 -*-
"""Cutover gate enforcement tests for portal shell route-view migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mes_dashboard.app import create_app

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "docs" / "migration" / "portal-shell-route-view-integration"

pytestmark = pytest.mark.skipif(
    not BASELINE_DIR.exists(),
    reason=f"Migration baseline directory missing: {BASELINE_DIR}",
)
BASELINE_VISIBILITY_FILE = BASELINE_DIR / "baseline_drawer_visibility.json"
BASELINE_API_FILE = BASELINE_DIR / "baseline_api_payload_contracts.json"
GATE_REPORT_FILE = BASELINE_DIR / "cutover-gates-report.json"
WAVE_A_EVIDENCE_FILE = BASELINE_DIR / "wave-a-smoke-evidence.json"
WAVE_B_EVIDENCE_FILE = BASELINE_DIR / "wave-b-native-smoke-evidence.json"
WAVE_B_PARITY_FILE = BASELINE_DIR / "wave-b-parity-evidence.json"
VISUAL_SNAPSHOT_FILE = BASELINE_DIR / "visual-regression-snapshots.json"
ROLLBACK_RUNBOOK = BASELINE_DIR / "rollback-rehearsal-shell-route-view.md"
KILL_SWITCH_DOC = BASELINE_DIR / "kill-switch-operations.md"
OBSERVABILITY_REPORT = BASELINE_DIR / "migration-observability-report.md"
STRESS_SUITE = ROOT / "tests" / "stress" / "test_frontend_stress.py"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
    _login_as_admin(client)

    p0_routes = [
        "/",
        "/portal-shell",
        "/api/portal/navigation",
        "/wip-overview",
        "/resource",
        "/qc-gate",
        "/job-query",
        "/excel-query",
        "/query-tool",
    ]

    statuses = [client.get(route).status_code for route in p0_routes]
    assert all(200 <= status < 400 for status in statuses), statuses


def test_g2_drawer_parity_gate_matches_baseline_for_admin_and_non_admin():
    baseline = _read_json(BASELINE_VISIBILITY_FILE)
    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    non_admin_payload = _read_json_response(non_admin_client.get("/api/portal/navigation"))

    admin_client = app.test_client()
    _login_as_admin(admin_client)
    admin_payload = _read_json_response(admin_client.get("/api/portal/navigation"))

    assert _route_set(non_admin_payload["drawers"]) == _route_set(baseline["non_admin"])
    assert _route_set(admin_payload["drawers"]) == _route_set(baseline["admin"])


def test_g3_smoke_evidence_gate_requires_wave_a_and_wave_b_pass():
    wave_a = _read_json(WAVE_A_EVIDENCE_FILE)
    wave_b = _read_json(WAVE_B_EVIDENCE_FILE)

    for payload in (wave_a, wave_b):
        assert payload["execution"]["automated_runs"]
        for run in payload["execution"]["automated_runs"]:
            assert run["status"] == "pass"
        for route, result in payload["pages"].items():
            assert result["status"] == "pass", f"smoke evidence failed: {route}"
            assert result["critical_failures"] == []


def test_g4_no_iframe_gate_blocks_if_shell_uses_iframe():
    stress_source = STRESS_SUITE.read_text(encoding="utf-8")
    assert "Portal should not render iframe after migration" in stress_source
    assert "iframe_count = page.locator('iframe').count()" in stress_source

    report = _read_json(GATE_REPORT_FILE)
    g4 = next(g for g in report["gates"] if g["id"] == "G4")
    assert g4["status"] == "pass"
    assert g4["block_on_fail"] is True


def test_g5_route_query_compatibility_gate_checks_contracts():
    baseline = _read_json(BASELINE_API_FILE)
    app = create_app("testing")
    app.config["TESTING"] = True
    registered_routes = {rule.rule for rule in app.url_map.iter_rules()}

    for api_route, contract in baseline.get("apis", {}).items():
        assert api_route in registered_routes, f"Missing API route in app map: {api_route}"
        required_keys = contract.get("required_keys", [])
        assert required_keys, f"No required_keys defined for {api_route}"
        assert all(isinstance(key, str) and key for key in required_keys)

    report = _read_json(GATE_REPORT_FILE)
    g5 = next(g for g in report["gates"] if g["id"] == "G5")
    assert g5["status"] == "pass"
    assert g5["block_on_fail"] is True


def test_g6_parity_gate_requires_table_chart_filter_interaction_matrix_pass():
    parity = _read_json(WAVE_B_PARITY_FILE)
    for route, checks in parity["pages"].items():
        for dimension in ("table", "chart", "filter", "interaction", "matrix"):
            status = checks[dimension]["status"]
            assert status in {"pass", "n/a"}, f"{route} parity failed on {dimension}: {status}"

    snapshots = _read_json(VISUAL_SNAPSHOT_FILE)
    assert snapshots["critical_diff_policy"]["block_release"] is True
    assert len(snapshots["snapshots"]) >= 4

    report = _read_json(GATE_REPORT_FILE)
    g6 = next(g for g in report["gates"] if g["id"] == "G6")
    assert g6["status"] == "pass"
    assert g6["block_on_fail"] is True


def test_g7_rollback_gate_has_recovery_slo_and_kill_switch_steps():
    rehearsal = ROLLBACK_RUNBOOK.read_text(encoding="utf-8")
    kill_switch = KILL_SWITCH_DOC.read_text(encoding="utf-8")

    assert "15 minutes" in rehearsal
    assert "PORTAL_SPA_ENABLED=false" in rehearsal
    assert "PORTAL_SPA_ENABLED=false" in kill_switch
    assert "/api/portal/navigation" in kill_switch
    assert "/health" in kill_switch

    report = _read_json(GATE_REPORT_FILE)
    g7 = next(g for g in report["gates"] if g["id"] == "G7")
    assert g7["status"] == "pass"
    assert g7["block_on_fail"] is True


def test_release_block_semantics_enforced_by_gate_report():
    report = _read_json(GATE_REPORT_FILE)
    assert report["policy"]["block_on_any_failed_gate"] is True
    assert report["policy"]["block_on_incomplete_smoke_evidence"] is True
    assert report["policy"]["block_on_critical_parity_failure"] is True

    for gate in report["gates"]:
        assert gate["status"] == "pass"
        assert gate["block_on_fail"] is True
    assert report["release_blocked"] is False


def test_observability_report_covers_route_errors_health_and_fallback_usage():
    content = OBSERVABILITY_REPORT.read_text(encoding="utf-8")
    assert "route errors" in content.lower()
    assert "health regressions" in content.lower()
    assert "wrapper fallback usage" in content.lower()


def _read_json_response(response) -> dict:
    return json.loads(response.data.decode("utf-8"))
