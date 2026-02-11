# -*- coding: utf-8 -*-
"""Tests for portal shell routes and navigation API."""

from __future__ import annotations

import json

from mes_dashboard.app import create_app


def _login_as_admin(client) -> None:
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}


def test_portal_shell_fallback_html_served_when_dist_missing(monkeypatch):
    app = create_app("testing")
    app.config["TESTING"] = True

    # Force fallback path by simulating missing dist file.
    monkeypatch.setattr("os.path.exists", lambda *_args, **_kwargs: False)

    client = app.test_client()
    response = client.get("/portal-shell")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "/static/dist/portal-shell.js" in html
    assert "/static/dist/portal-shell.css" in html
    assert "/static/dist/tailwind.css" in html


def test_portal_shell_uses_nested_dist_html_when_top_level_missing(monkeypatch):
    app = create_app("testing")
    app.config["TESTING"] = True

    def fake_exists(path: str) -> bool:
        if path.endswith("/dist/portal-shell.html"):
            return False
        return path.endswith("/dist/src/portal-shell/index.html")

    monkeypatch.setattr("os.path.exists", fake_exists)

    client = app.test_client()
    response = client.get("/portal-shell")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "/static/dist/portal-shell.js" in html
    assert "/static/dist/portal-shell.css" in html
    assert "/static/dist/tailwind.css" in html


def test_portal_navigation_non_admin_visibility_matches_release_only():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/portal/navigation")
    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["is_admin"] is False
    assert payload["admin_user"] is None

    all_routes = {
        page["route"]
        for drawer in payload["drawers"]
        for page in drawer["pages"]
    }

    # Non-admin baseline from current config.
    assert "/wip-overview" in all_routes
    assert "/resource" in all_routes
    assert "/qc-gate" in all_routes
    assert "/resource-history" in all_routes
    assert "/job-query" in all_routes
    assert "/admin/pages" not in all_routes
    assert "/excel-query" not in all_routes


def test_portal_navigation_admin_includes_admin_drawer_routes():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    response = client.get("/api/portal/navigation")
    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["is_admin"] is True
    assert payload["admin_user"]["displayName"] == "Admin"

    all_routes = {
        page["route"]
        for drawer in payload["drawers"]
        for page in drawer["pages"]
    }
    assert "/admin/pages" in all_routes
    assert "/admin/performance" in all_routes
    assert "/excel-query" in all_routes


def test_wrapper_telemetry_endpoint_removed_after_wrapper_decommission():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.post(
        "/api/portal/wrapper-telemetry",
        json={
            "route": "/job-query",
            "event_type": "wrapper_loaded",
        },
    )
    assert response.status_code == 404


def test_navigation_drawer_and_page_order_deterministic_non_admin():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/portal/navigation")
    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))

    drawer_ids = [drawer["id"] for drawer in payload["drawers"]]
    assert drawer_ids == ["reports", "drawer-2", "drawer"]

    reports_routes = [page["route"] for page in payload["drawers"][0]["pages"]]
    assert reports_routes == ["/wip-overview", "/resource", "/qc-gate"]


def test_navigation_mixed_release_dev_visibility_admin_vs_non_admin():
    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    non_admin_resp = non_admin_client.get("/api/portal/navigation")
    assert non_admin_resp.status_code == 200
    non_admin_payload = json.loads(non_admin_resp.data.decode("utf-8"))
    non_admin_routes = {
        page["route"]
        for drawer in non_admin_payload["drawers"]
        for page in drawer["pages"]
    }
    assert "/hold-overview" not in non_admin_routes
    assert "/hold-history" not in non_admin_routes

    admin_client = app.test_client()
    _login_as_admin(admin_client)
    admin_resp = admin_client.get("/api/portal/navigation")
    assert admin_resp.status_code == 200
    admin_payload = json.loads(admin_resp.data.decode("utf-8"))
    admin_routes = {
        page["route"]
        for drawer in admin_payload["drawers"]
        for page in drawer["pages"]
    }
    assert "/hold-overview" in admin_routes
    assert "/hold-history" in admin_routes


def test_legacy_wrapper_routes_are_reachable():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    for route in ["/job-query", "/excel-query", "/query-tool", "/tmtt-defect"]:
        response = client.get(route)
        assert response.status_code == 200, f"{route} should be reachable"
