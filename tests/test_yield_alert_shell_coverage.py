# -*- coding: utf-8 -*-
"""Shell and standalone coverage tests for Yield Alert Center route."""

from __future__ import annotations

from unittest.mock import patch

from mes_dashboard.app import create_app


def _login_as_admin(client) -> None:
    with client.session_transaction() as sess:
        sess["admin"] = {"displayName": "Admin", "employeeNo": "A001"}


def test_yield_alert_page_redirects_to_shell_when_spa_enabled(monkeypatch):
    monkeypatch.setenv("PORTAL_SPA_ENABLED", "true")
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()
    _login_as_admin(client)

    response = client.get("/yield-alert-center?start_date=2026-03-01", follow_redirects=False)

    assert response.status_code == 302
    assert response.location.endswith("/portal-shell/yield-alert-center?start_date=2026-03-01")
