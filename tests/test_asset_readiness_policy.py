# -*- coding: utf-8 -*-
"""Tests for modernization asset-readiness and fallback-retirement policy."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mes_dashboard.app import create_app


def test_asset_readiness_enforcement_blocks_startup_when_missing_assets(monkeypatch):
    monkeypatch.setenv("MODERNIZATION_ENFORCE_ASSET_READINESS", "true")

    with patch(
        "mes_dashboard.app.get_missing_in_scope_assets",
        return_value=["/wip-overview:wip-overview.html"],
    ):
        with pytest.raises(RuntimeError, match="In-scope asset readiness check failed"):
            create_app("testing")


def test_in_scope_fallback_retirement_returns_503_when_dist_asset_missing(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "false")
    monkeypatch.setenv("MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    with patch("mes_dashboard.routes.hold_overview_routes.os.path.exists", return_value=False):
        response = client.get("/hold-overview")

    assert response.status_code == 503
    assert "系統發生錯誤" in response.data.decode("utf-8")


@pytest.mark.parametrize(
    ("route", "exists_patch"),
    [
        ("/hold-overview", "mes_dashboard.routes.hold_overview_routes.os.path.exists"),
        ("/hold-history", "mes_dashboard.routes.hold_history_routes.os.path.exists"),
        ("/hold-detail?reason=YieldLimit", "mes_dashboard.routes.hold_routes.os.path.exists"),
    ],
)
def test_hold_blueprints_share_retired_fallback_template(monkeypatch, route, exists_patch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "false")
    monkeypatch.setenv("MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    with patch(exists_patch, return_value=False):
        response = client.get(route)

    assert response.status_code == 503
    assert "系統發生錯誤" in response.data.decode("utf-8")


def test_promoted_deferred_route_enforces_asset_readiness_when_retirement_enabled(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "false")
    monkeypatch.setenv("MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}

    with patch("mes_dashboard.app.os.path.exists", return_value=False):
        response = client.get("/tables")

    # Promoted deferred routes now enforce asset readiness (503 when missing).
    assert response.status_code == 503


def test_template_backed_promoted_routes_do_not_require_html_assets():
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "migration"
        / "full-modernization-architecture-blueprint"
        / "asset_readiness_manifest.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = payload.get("in_scope_required_assets", {})

    assert required.get("/excel-query") == ["excel-query.js"]
    assert required.get("/query-tool") == ["query-tool.js"]
