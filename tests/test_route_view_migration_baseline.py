# -*- coding: utf-8 -*-
"""Validation tests for shell route-view migration baseline artifacts."""

from __future__ import annotations

import json
import copy
from pathlib import Path

from mes_dashboard.app import create_app
from mes_dashboard.services.navigation_contract import (
    compute_drawer_visibility,
    validate_route_migration_contract,
    validate_wave_b_rewrite_entry_criteria,
)


ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"
BASELINE_DIR = ROOT / "docs" / "migration" / "portal-shell-route-view-integration"

BASELINE_VISIBILITY_FILE = BASELINE_DIR / "baseline_drawer_visibility.json"
BASELINE_ROUTE_QUERY_FILE = BASELINE_DIR / "baseline_route_query_contracts.json"
BASELINE_INTERACTION_FILE = BASELINE_DIR / "baseline_interaction_evidence.json"
ROUTE_CONTRACT_FILE = BASELINE_DIR / "route_migration_contract.json"
ROUTE_CONTRACT_VALIDATION_FILE = BASELINE_DIR / "route_migration_contract_validation.json"
WAVE_B_REWRITE_ENTRY_FILE = BASELINE_DIR / "wave-b-rewrite-entry-criteria.json"

REQUIRED_ROUTES = {
    "/wip-overview",
    "/wip-detail",
    "/hold-overview",
    "/hold-detail",
    "/hold-history",
    "/resource",
    "/resource-history",
    "/qc-gate",
    "/job-query",
    "/excel-query",
    "/query-tool",
    "/tmtt-defect",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_route_migration_contract_has_no_validation_errors():
    contract = _read_json(ROUTE_CONTRACT_FILE)
    errors = validate_route_migration_contract(contract, required_routes=REQUIRED_ROUTES)
    assert errors == []

    validation_payload = _read_json(ROUTE_CONTRACT_VALIDATION_FILE)
    assert validation_payload["errors"] == []


def test_wave_b_rewrite_entry_criteria_blocks_premature_native_cutover():
    contract = _read_json(ROUTE_CONTRACT_FILE)
    rewrite_entry = _read_json(WAVE_B_REWRITE_ENTRY_FILE)

    # Current baseline has complete evidence for Wave B native routes.
    assert validate_wave_b_rewrite_entry_criteria(contract, rewrite_entry) == []

    # Simulate incomplete criteria while route already in native mode.
    mutated_criteria = copy.deepcopy(rewrite_entry)
    mutated_criteria["pages"]["/job-query"]["evidence"]["parity"] = "pending"
    mutated_criteria["pages"]["/job-query"]["native_cutover_ready"] = False
    mutated_criteria["pages"]["/job-query"]["block_reason"] = "pending parity"

    errors = validate_wave_b_rewrite_entry_criteria(contract, mutated_criteria)
    assert "native cutover blocked for /job-query: rewrite criteria incomplete" in errors


def test_baseline_visibility_matches_current_registry_state():
    page_status = _read_json(PAGE_STATUS_FILE)
    baseline = _read_json(BASELINE_VISIBILITY_FILE)

    assert baseline["admin"] == compute_drawer_visibility(page_status, is_admin=True)
    assert baseline["non_admin"] == compute_drawer_visibility(page_status, is_admin=False)


def test_baseline_route_query_contract_covers_all_target_routes():
    baseline = _read_json(BASELINE_ROUTE_QUERY_FILE)
    routes = baseline["routes"]

    assert set(routes.keys()) == REQUIRED_ROUTES
    for route in REQUIRED_ROUTES:
        assert "query_keys" in routes[route]
        assert "render_mode" in routes[route]
        assert routes[route]["render_mode"] in {"native", "wrapper"}


def test_interaction_evidence_contains_required_sections_for_all_routes():
    payload = _read_json(BASELINE_INTERACTION_FILE)
    routes = payload["routes"]

    assert set(routes.keys()) == REQUIRED_ROUTES
    for route in REQUIRED_ROUTES:
        entry = routes[route]
        assert "table" in entry
        assert "chart" in entry
        assert "filter" in entry
        assert "matrix" in entry


def test_navigation_api_drawer_parity_matches_shell_baseline_for_admin_and_non_admin():
    app = create_app("testing")
    app.config["TESTING"] = True
    baseline = _read_json(BASELINE_VISIBILITY_FILE)

    non_admin_client = app.test_client()
    non_admin_payload = _read_response_json(non_admin_client.get("/api/portal/navigation"))
    assert _route_set(non_admin_payload["drawers"]) == _route_set(baseline["non_admin"])

    admin_client = app.test_client()
    with admin_client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}
    admin_payload = _read_response_json(admin_client.get("/api/portal/navigation"))
    assert _route_set(admin_payload["drawers"]) == _route_set(baseline["admin"])


def _read_response_json(response) -> dict:
    return json.loads(response.data.decode("utf-8"))


def _route_set(drawers: list[dict]) -> set[str]:
    return {
        page["route"]
        for drawer in drawers
        for page in drawer.get("pages", [])
    }
