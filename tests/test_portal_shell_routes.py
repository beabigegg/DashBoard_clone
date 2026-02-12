# -*- coding: utf-8 -*-
"""Tests for portal shell routes and navigation API."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import ANY, MagicMock, patch

from mes_dashboard.app import create_app


def _login_as_admin(client) -> None:
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}


def test_portal_shell_fallback_html_served_when_dist_missing(monkeypatch):
    app = create_app("testing")
    app.config["TESTING"] = True

    # Force fallback path by simulating missing dist file.
    monkeypatch.setattr("mes_dashboard.app.os.path.exists", lambda *_args, **_kwargs: False)

    client = app.test_client()
    response = client.get("/portal-shell")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "/static/dist/portal-shell.js" in html
    assert "/static/dist/portal-shell.css" in html
    assert "/static/dist/tailwind.css" in html

    response_with_trailing_slash = client.get("/portal-shell/")
    assert response_with_trailing_slash.status_code == 200


def test_portal_shell_uses_nested_dist_html_when_top_level_missing(monkeypatch):
    app = create_app("testing")
    app.config["TESTING"] = True

    def fake_exists(path: str) -> bool:
        if path.endswith("/dist/portal-shell.html"):
            return False
        return path.endswith("/dist/src/portal-shell/index.html")

    monkeypatch.setattr("mes_dashboard.app.os.path.exists", fake_exists)

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

    post_response = client.post(
        "/api/portal/wrapper-telemetry",
        json={
            "route": "/job-query",
            "event_type": "wrapper_load_success",
        },
    )
    assert post_response.status_code == 404

    get_response = client.get("/api/portal/wrapper-telemetry")
    assert get_response.status_code == 404


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
    assert reports_routes == ["/wip-overview", "/hold-overview", "/resource", "/qc-gate"]


def test_navigation_contract_page_metadata_fields_present_and_typed():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    payload = json.loads(client.get("/api/portal/navigation").data.decode("utf-8"))
    assert isinstance(payload["drawers"], list)

    for drawer in payload["drawers"]:
        assert isinstance(drawer["id"], str) and drawer["id"]
        assert isinstance(drawer["name"], str) and drawer["name"]
        assert isinstance(drawer["order"], int)
        assert isinstance(drawer["admin_only"], bool)
        assert isinstance(drawer["pages"], list)

        for page in drawer["pages"]:
            assert isinstance(page["route"], str) and page["route"].startswith("/")
            assert isinstance(page["name"], str) and page["name"]
            assert page["status"] in {"released", "dev"}
            assert isinstance(page["order"], int)


def test_navigation_duplicate_order_values_still_resolve_deterministically():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    config = [
        {
            "id": "reports",
            "name": "Reports",
            "order": 1,
            "admin_only": False,
            "pages": [
                {"route": "/qc-gate", "name": "QC", "status": "released", "order": 1},
                {"route": "/resource", "name": "Resource", "status": "released", "order": 1},
                {"route": "/wip-overview", "name": "WIP", "status": "released", "order": 1},
            ],
        },
        {
            "id": "tools",
            "name": "Tools",
            "order": 1,
            "admin_only": False,
            "pages": [
                {"route": "/job-query", "name": "Job", "status": "released", "order": 1},
            ],
        },
    ]

    with patch("mes_dashboard.app.get_navigation_config", return_value=config):
        payload = json.loads(client.get("/api/portal/navigation").data.decode("utf-8"))

    # Drawer tie breaks by name and page tie breaks by name.
    assert [drawer["id"] for drawer in payload["drawers"]] == ["reports", "tools"]
    assert [page["route"] for page in payload["drawers"][0]["pages"]] == ["/qc-gate", "/resource", "/wip-overview"]


def test_navigation_mixed_release_dev_visibility_admin_vs_non_admin():
    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    mixed_config = [
        {
            "id": "reports",
            "name": "Reports",
            "order": 1,
            "admin_only": False,
            "pages": [
                {"route": "/wip-overview", "name": "WIP", "status": "released", "order": 1},
                {"route": "/hold-overview", "name": "Hold", "status": "dev", "order": 2},
            ],
        }
    ]
    def fake_status(route: str):
        if route == "/hold-overview":
            return "dev"
        if route == "/wip-overview":
            return "released"
        return None

    with (
        patch("mes_dashboard.app.get_navigation_config", return_value=mixed_config),
        patch("mes_dashboard.app.get_page_status", side_effect=fake_status),
    ):
        non_admin_resp = non_admin_client.get("/api/portal/navigation")
        assert non_admin_resp.status_code == 200
        non_admin_payload = json.loads(non_admin_resp.data.decode("utf-8"))
        non_admin_routes = {
            page["route"]
            for drawer in non_admin_payload["drawers"]
            for page in drawer["pages"]
        }
        assert "/wip-overview" in non_admin_routes
        assert "/hold-overview" not in non_admin_routes

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
        assert "/wip-overview" in admin_routes
        assert "/hold-overview" in admin_routes


def test_portal_navigation_includes_admin_links_by_auth_state():
    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    non_admin_payload = json.loads(non_admin_client.get("/api/portal/navigation").data.decode("utf-8"))
    assert non_admin_payload["admin_links"]["login"].startswith("/admin/login?next=")
    assert non_admin_payload["admin_links"]["pages"] is None
    assert non_admin_payload["admin_links"]["logout"] is None

    admin_client = app.test_client()
    _login_as_admin(admin_client)
    admin_payload = json.loads(admin_client.get("/api/portal/navigation").data.decode("utf-8"))
    assert admin_payload["admin_links"]["pages"] == "/admin/pages"
    assert admin_payload["admin_links"]["logout"] == "/admin/logout"


def test_portal_navigation_emits_diagnostics_for_invalid_navigation_payload():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    malformed = [
        {"id": "", "name": "bad-drawer", "pages": []},
        {
            "id": "reports",
            "name": "Reports",
            "order": 1,
            "admin_only": False,
            "pages": [
                {"route": "", "name": "invalid-route"},
                {"route": "missing-leading-slash", "name": "invalid-route-2"},
                "not-a-dict",
            ],
        },
    ]

    with patch("mes_dashboard.app.get_navigation_config", return_value=malformed):
        response = client.get("/api/portal/navigation")

    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    diagnostics = payload["diagnostics"]
    assert diagnostics["invalid_drawers"] >= 1
    assert diagnostics["invalid_pages"] >= 2
    assert payload["drawers"] == []


def test_portal_navigation_logs_contract_mismatch_route():
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    with (
        patch("mes_dashboard.app._load_shell_route_contract_routes", return_value={"/wip-overview"}),
        patch(
            "mes_dashboard.app.get_navigation_config",
            return_value=[
                {
                    "id": "reports",
                    "name": "Reports",
                    "order": 1,
                    "admin_only": False,
                    "pages": [
                        {"route": "/wip-overview", "name": "WIP", "status": "released", "order": 1},
                        {"route": "/resource", "name": "Resource", "status": "released", "order": 2},
                    ],
                }
            ],
        ),
    ):
        response = client.get("/api/portal/navigation")

    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    assert payload["diagnostics"]["contract_mismatch_routes"] == ["/resource"]


def test_wave_b_native_routes_are_reachable(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "false")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    for route in ["/job-query", "/excel-query", "/query-tool", "/tmtt-defect"]:
        response = client.get(route)
        assert response.status_code == 200, f"{route} should be reachable"


def test_direct_entry_in_scope_report_routes_redirect_to_canonical_shell_when_spa_enabled(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    cases = {
        "/wip-overview?status=queue": "/portal-shell/wip-overview?status=queue",
        "/resource-history?granularity=day": "/portal-shell/resource-history?granularity=day",
        "/job-query?start_date=2026-02-01&end_date=2026-02-02": "/portal-shell/job-query?start_date=2026-02-01&end_date=2026-02-02",
        "/tmtt-defect?start_date=2026-02-01&end_date=2026-02-02": "/portal-shell/tmtt-defect?start_date=2026-02-01&end_date=2026-02-02",
        "/hold-detail?reason=YieldLimit": "/portal-shell/hold-detail?reason=YieldLimit",
    }

    for direct_url, canonical_url in cases.items():
        response = client.get(direct_url, follow_redirects=False)
        assert response.status_code == 302, direct_url
        assert response.location.endswith(canonical_url), response.location


def test_direct_entry_redirect_preserves_non_ascii_query_params(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/wip-detail?workcenter=焊接_DB&status=queue", follow_redirects=False)
    assert response.status_code == 302

    parsed = urlparse(response.location)
    assert parsed.path.endswith("/portal-shell/wip-detail")
    query = parse_qs(parsed.query)
    assert query.get("workcenter") == ["焊接_DB"]
    assert query.get("status") == ["queue"]


def test_legacy_shell_contract_fallback_logs_warning(monkeypatch):
    from mes_dashboard import app as app_module

    app_module._SHELL_ROUTE_CONTRACT_MAP = None
    app = create_app("testing")
    app.config["TESTING"] = True

    primary_suffix = "/docs/migration/full-modernization-architecture-blueprint/route_contracts.json"
    legacy_suffix = "/docs/migration/portal-shell-route-view-integration/route_migration_contract.json"
    sample_payload = json.dumps({"routes": [{"route": "/wip-overview", "scope": "in-scope"}]})
    original_exists = Path.exists
    original_read_text = Path.read_text

    def fake_exists(self):
        raw = str(self).replace("\\", "/")
        if raw.endswith(primary_suffix):
            return False
        if raw.endswith(legacy_suffix):
            return True
        return original_exists(self)

    def fake_read_text(self, encoding="utf-8"):
        raw = str(self).replace("\\", "/")
        if raw.endswith(legacy_suffix):
            return sample_payload
        return original_read_text(self, encoding=encoding)

    logger = MagicMock()
    with (
        patch("mes_dashboard.app.logging.getLogger", return_value=logger),
        patch.object(Path, "exists", fake_exists),
        patch.object(Path, "read_text", fake_read_text),
    ):
        contract_map = app_module._load_shell_route_contract_map()

    assert "/wip-overview" in contract_map
    logger.warning.assert_any_call(
        "Using legacy contract file fallback for shell route contracts: %s",
        ANY,
    )
    app_module._SHELL_ROUTE_CONTRACT_MAP = None


def test_promoted_deferred_routes_redirect_to_canonical_shell_when_spa_enabled(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    cases = {
        "/tables?category=wip": "/portal-shell/tables?category=wip",
        "/excel-query": "/portal-shell/excel-query",
        "/query-tool": "/portal-shell/query-tool",
        "/mid-section-defect": "/portal-shell/mid-section-defect",
    }

    for direct_url, canonical_url in cases.items():
        response = client.get(direct_url, follow_redirects=False)
        assert response.status_code == 302, f"{direct_url} should redirect"
        assert response.location.endswith(canonical_url), (
            f"{direct_url}: expected {canonical_url}, got {response.location}"
        )
