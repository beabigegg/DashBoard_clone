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
        sess["user"] = {
            "username": "A001",
            "displayName": "Admin",
            "mail": "admin@test.com",
            "is_admin": True,
        }


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


def test_portal_shell_fallback_html_when_nested_dist_html_unreadable(monkeypatch):
    app = create_app("testing")
    app.config["TESTING"] = True

    def fake_exists(path: str) -> bool:
        if path.endswith("/dist/portal-shell.html"):
            return False
        return path.endswith("/dist/src/portal-shell/index.html")

    def fake_open(path: str, *_args, **_kwargs):
        if path.endswith("/dist/src/portal-shell/index.html"):
            raise OSError("simulated read failure")
        return open(path, *_args, **_kwargs)

    monkeypatch.setattr("mes_dashboard.app.os.path.exists", fake_exists)
    monkeypatch.setattr("mes_dashboard.app.open", fake_open, raising=False)

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

    # Navigation structure is now frontend-owned (navigationManifest.js).
    # The API returns a statuses dict; no drawers key is emitted.
    assert "drawers" not in payload
    assert isinstance(payload["statuses"], dict)



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

    # Navigation structure is frontend-owned; the API returns statuses dict.
    # Admin-only drawer routing is handled in navigationManifest.js.
    assert "drawers" not in payload
    assert isinstance(payload["statuses"], dict)
    assert isinstance(payload["admin_links"], dict)
    assert payload["admin_links"]["pages"] == "/admin/pages"



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
    """Drawer order/membership is now owned by navigationManifest.js (frontend).

    The backend status feed returns a stable dict; assert shape not order.
    """
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/portal/navigation")
    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))

    # API emits statuses dict, not a drawers list.
    assert "drawers" not in payload
    statuses = payload["statuses"]
    assert isinstance(statuses, dict)
    # All values are valid status tokens.
    for route, status in statuses.items():
        assert status in {"released", "dev"}, f"{route} has invalid status {status!r}"


def test_navigation_contract_page_metadata_fields_present_and_typed():
    """Top-level field contract for GET /api/portal/navigation after nav-config-to-code.

    drawer/page metadata is now frontend-owned; backend emits the status feed shape.
    """
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    payload = json.loads(client.get("/api/portal/navigation").data.decode("utf-8"))

    # Required top-level keys.
    assert "statuses" in payload
    assert "is_admin" in payload
    assert "admin_user" in payload
    assert "admin_links" in payload
    assert "features" in payload
    assert "diagnostics" in payload

    # drawers key MUST NOT appear in the response.
    assert "drawers" not in payload

    assert isinstance(payload["statuses"], dict)
    assert isinstance(payload["is_admin"], bool)
    assert isinstance(payload["admin_links"], dict)
    assert isinstance(payload["features"], dict)
    assert isinstance(payload["diagnostics"], dict)

    # Each status value must be a valid token.
    for route, status in payload["statuses"].items():
        assert isinstance(route, str) and route.startswith("/")
        assert status in {"released", "dev"}, f"{route}: unexpected status {status!r}"


def test_navigation_duplicate_order_values_still_resolve_deterministically():
    """Ordering is now frontend-owned (navigationManifest.js).

    The backend returns statuses dict; assert the dict round-trips correctly
    when get_navigation_config is patched to return a status map.
    """
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    status_map = {
        "/qc-gate": "released",
        "/resource": "released",
        "/wip-overview": "released",
        "/job-query": "released",
    }

    with patch("mes_dashboard.app.get_navigation_config", return_value=status_map):
        payload = json.loads(client.get("/api/portal/navigation").data.decode("utf-8"))

    assert "drawers" not in payload
    assert payload["statuses"] == status_map


def test_navigation_mixed_release_dev_visibility_admin_vs_non_admin():
    """Status feed exposes all statuses regardless of admin state.

    Visibility filtering (show/hide dev pages) is now a frontend concern.
    Both admin and non-admin get the same statuses dict; the frontend
    applies the visibility rule using navigationManifest.js.
    """
    app = create_app("testing")
    app.config["TESTING"] = True

    status_map = {
        "/wip-overview": "released",
        "/hold-overview": "dev",
    }

    non_admin_client = app.test_client()
    with patch("mes_dashboard.app.get_navigation_config", return_value=status_map):
        non_admin_resp = non_admin_client.get("/api/portal/navigation")
        assert non_admin_resp.status_code == 200
        non_admin_payload = json.loads(non_admin_resp.data.decode("utf-8"))
        assert non_admin_payload["is_admin"] is False
        # Backend returns the full status map; frontend applies visibility.
        assert non_admin_payload["statuses"] == status_map

        admin_client = app.test_client()
        _login_as_admin(admin_client)
        admin_resp = admin_client.get("/api/portal/navigation")
        assert admin_resp.status_code == 200
        admin_payload = json.loads(admin_resp.data.decode("utf-8"))
        assert admin_payload["is_admin"] is True
        assert admin_payload["statuses"] == status_map


def test_portal_navigation_includes_admin_links_by_auth_state():
    app = create_app("testing")
    app.config["TESTING"] = True

    non_admin_client = app.test_client()
    non_admin_payload = json.loads(non_admin_client.get("/api/portal/navigation").data.decode("utf-8"))
    assert non_admin_payload["admin_links"]["pages"] is None
    assert non_admin_payload["admin_links"]["dashboard"] is None
    assert non_admin_payload["admin_links"]["logout"] is None

    admin_client = app.test_client()
    _login_as_admin(admin_client)
    admin_payload = json.loads(admin_client.get("/api/portal/navigation").data.decode("utf-8"))
    assert admin_payload["admin_links"]["pages"] == "/admin/pages"
    assert admin_payload["admin_links"]["dashboard"] == "/admin/dashboard"
    assert admin_payload["admin_links"]["logout"] == "/api/auth/logout"


def test_portal_navigation_emits_diagnostics_for_invalid_navigation_payload():
    """Diagnostics field is present; validation moved to frontend manifest layer.

    The backend status feed returns an empty diagnostics dict.
    Structural validation of drawers/pages is navigationManifest.js concern.
    """
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/portal/navigation")

    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    # diagnostics key must be present (shape contract).
    assert "diagnostics" in payload
    assert isinstance(payload["diagnostics"], dict)
    # No drawers key in status-feed shape.
    assert "drawers" not in payload


def test_portal_navigation_logs_contract_mismatch_route():
    """Contract-mismatch detection moved to frontend navigationManifest.js layer.

    The backend status feed returns an empty diagnostics dict; no
    contract_mismatch_routes key is emitted.
    """
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/api/portal/navigation")

    assert response.status_code == 200
    payload = json.loads(response.data.decode("utf-8"))
    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, dict)
    # contract_mismatch_routes is no longer a backend concern.
    assert "contract_mismatch_routes" not in diagnostics


def test_wave_b_native_routes_are_reachable(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "false")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    for route in ["/job-query", "/query-tool", "/yield-alert-center"]:
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
        "/query-tool": "/portal-shell/query-tool",
        "/mid-section-defect": "/portal-shell/mid-section-defect",
        "/yield-alert-center?start_date=2026-03-01": "/portal-shell/yield-alert-center?start_date=2026-03-01",
    }

    for direct_url, canonical_url in cases.items():
        response = client.get(direct_url, follow_redirects=False)
        assert response.status_code == 302, f"{direct_url} should redirect"
        assert response.location.endswith(canonical_url), (
            f"{direct_url}: expected {canonical_url}, got {response.location}"
        )
